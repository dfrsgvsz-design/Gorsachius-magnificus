"""
GPU Training Pipeline v6 — SE-ResNet + Dual-Channel Mel + GeM + Distillation

Refactored from V1-V5 lessons learned:
- V3 two-phase Teacher-Student distillation pipeline (+3.67pp proven gain)
- V5 dual-channel mel spectrogram (BirdNET-style, 48kHz, 3s segments)
- V6 GeM pooling (learnable generalization of avg/max pooling)
- All proven regularization: Focal Loss, EMA, CutMix, Mixup, SpecAugment

Baseline: V4 = 61.68% val_acc (217 species, 9633 recordings)
Target:   V6 = 65-70% val_acc (223 species, 19401 recordings)

Two-phase pipeline:
  Phase 1: Train SE-ResNet-50 V6 teacher (200 epochs)
  Phase 2: Distill to SE-ResNet-18 V6 student (150 epochs)
"""

import os
import sys
import json
import time
import warnings
import logging
import numpy as np
from pathlib import Path
from collections import Counter
from datetime import datetime

warnings.filterwarnings('ignore')
os.environ['PYTHONWARNINGS'] = 'ignore'

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler
from torch.amp import autocast, GradScaler
import librosa

from cnn_model_v6 import (
    SEResNet50V6, SEResNet18V6, DistillationLoss,
    cutmix_data, mixup_data, count_parameters,
    compute_dual_channel_mel, DUAL_CHANNEL_CONFIG, TARGET_FRAMES,
)


# ──────────────────── Focal Loss ────────────────────

class FocalLoss(nn.Module):
    def __init__(self, weight=None, gamma=2.0, label_smoothing=0.0, reduction='mean'):
        super().__init__()
        self.gamma = gamma
        self.weight = weight
        self.label_smoothing = label_smoothing
        self.reduction = reduction

    def forward(self, inputs, targets):
        ce_loss = F.cross_entropy(
            inputs, targets, weight=self.weight,
            label_smoothing=self.label_smoothing, reduction='none',
        )
        pt = torch.exp(-ce_loss)
        focal_loss = ((1 - pt) ** self.gamma) * ce_loss
        if self.reduction == 'mean':
            return focal_loss.mean()
        elif self.reduction == 'sum':
            return focal_loss.sum()
        return focal_loss


# ──────────────────── EMA ────────────────────

class EMA:
    def __init__(self, model, decay=0.999, warmup_steps=500):
        self.target_decay = decay
        self.warmup_steps = warmup_steps
        self.step_count = 0
        self.shadow = {}
        self.backup = {}
        for name, param in model.named_parameters():
            if param.requires_grad:
                self.shadow[name] = param.data.clone()

    @property
    def current_decay(self):
        return min(self.target_decay,
                   (1 + self.step_count) / (self.warmup_steps + self.step_count))

    def update(self, model):
        self.step_count += 1
        decay = self.current_decay
        for name, param in model.named_parameters():
            if param.requires_grad:
                self.shadow[name].lerp_(param.data, 1.0 - decay)

    def apply_shadow(self, model):
        for name, param in model.named_parameters():
            if param.requires_grad:
                self.backup[name] = param.data.clone()
                param.data.copy_(self.shadow[name])

    def restore(self, model):
        for name, param in model.named_parameters():
            if param.requires_grad:
                param.data.copy_(self.backup[name])
        self.backup = {}


# ──────────────────── Dataset: Dual-Channel Mel ────────────────────

class BirdDatasetV6(Dataset):
    """Dual-channel mel spectrogram dataset for V6 SE-ResNet."""

    def __init__(self, items, species_to_idx, augment=False, sr=48000):
        self.items = items
        self.s2i = species_to_idx
        self.augment = augment
        self.sr = sr
        self.dur = DUAL_CHANNEL_CONFIG["segment_duration"]

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        item = self.items[idx]
        label = self.s2i.get(item["species_scientific"], 0)

        try:
            y, sr = librosa.load(item["file_path"], sr=self.sr, duration=self.dur + 1, mono=True)
        except Exception:
            mel = np.zeros((2, 96, TARGET_FRAMES), dtype=np.float32)
            return torch.FloatTensor(mel), label

        tgt = int(self.dur * self.sr)
        if len(y) > tgt:
            start = np.random.randint(0, len(y) - tgt) if self.augment else (len(y) - tgt) // 2
            y = y[start:start + tgt]
        elif len(y) < tgt:
            y = np.pad(y, (0, tgt - len(y)))

        # Audio augmentation
        if self.augment:
            if np.random.random() < 0.5:
                y += np.random.randn(len(y)) * np.random.uniform(0.002, 0.012)
            if np.random.random() < 0.3:
                y = np.roll(y, int(len(y) * np.random.uniform(-0.15, 0.15)))
            if np.random.random() < 0.4:
                y *= np.random.uniform(0.7, 1.3)

        # Compute dual-channel mel
        mel = compute_dual_channel_mel(y, sr=self.sr)

        # SpecAugment on each channel
        if self.augment and np.random.random() < 0.7:
            mel = mel.copy()
            for ch in range(2):
                n_mels, n_frames = mel.shape[1], mel.shape[2]
                for _ in range(np.random.randint(2, 4)):
                    f = np.random.randint(1, 20)
                    f0 = np.random.randint(0, max(1, n_mels - f))
                    mel[ch, f0:f0+f, :] = 0
                for _ in range(np.random.randint(2, 4)):
                    t = np.random.randint(1, 40)
                    t0 = np.random.randint(0, max(1, n_frames - t))
                    mel[ch, :, t0:t0+t] = 0

        return torch.FloatTensor(mel), label


def mixup_criterion(criterion, pred, y_a, y_b, lam):
    return lam * criterion(pred, y_a) + (1 - lam) * criterion(pred, y_b)


# ──────────────────── Data Setup ────────────────────

def setup_data(manifest_path, min_samples=3, val_split=0.15):
    """Load manifest, filter species, split train/val."""
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    species_counts = Counter(item["species_scientific"] for item in manifest)
    valid_species = {sp for sp, cnt in species_counts.items() if cnt >= min_samples}
    manifest = [item for item in manifest if item["species_scientific"] in valid_species]

    species_list = sorted(valid_species)
    species_to_idx = {sp: i for i, sp in enumerate(species_list)}
    idx_to_species = {i: sp for sp, i in species_to_idx.items()}
    num_species = len(species_to_idx)

    np.random.seed(42)
    np.random.shuffle(manifest)
    val_size = int(len(manifest) * val_split)
    train_items = manifest[val_size:]
    val_items = manifest[:val_size]

    return train_items, val_items, species_to_idx, idx_to_species, num_species


def compute_class_weights(train_items, species_to_idx, num_species):
    """Compute class weights and weighted sampler."""
    train_labels = [species_to_idx.get(item["species_scientific"], 0) for item in train_items]
    class_counts = Counter(train_labels)
    class_weights = torch.FloatTensor([
        1.0 / max(class_counts.get(i, 1), 1) for i in range(num_species)
    ])
    class_weights = class_weights / class_weights.sum() * num_species

    sample_weights = [1.0 / max(class_counts.get(lbl, 1), 1) for lbl in train_labels]
    sampler = WeightedRandomSampler(sample_weights, len(sample_weights), replacement=True)
    return class_weights, sampler


# ──────────────────── Evaluation ────────────────────

def evaluate(model, val_loader, device, scaler, num_species):
    """Evaluate model on validation set."""
    model.eval()
    val_loss = 0.0
    val_correct = 0
    val_top5_correct = 0
    val_total = 0

    with torch.no_grad():
        for batch_x, batch_y in val_loader:
            batch_x = batch_x.to(device, non_blocking=True)
            batch_y = batch_y.to(device, non_blocking=True)

            if scaler:
                with autocast("cuda"):
                    outputs = model(batch_x)
                    loss = F.cross_entropy(outputs, batch_y)
            else:
                outputs = model(batch_x)
                loss = F.cross_entropy(outputs, batch_y)

            val_loss += loss.item() * batch_x.size(0)
            _, predicted = outputs.max(1)
            val_total += batch_y.size(0)
            val_correct += predicted.eq(batch_y).sum().item()

            if num_species >= 5:
                _, top5_pred = outputs.topk(5, dim=1)
                for i in range(batch_y.size(0)):
                    if batch_y[i] in top5_pred[i]:
                        val_top5_correct += 1

    val_loss /= max(val_total, 1)
    val_acc = val_correct / max(val_total, 1)
    val_top5 = val_top5_correct / max(val_total, 1) if num_species >= 5 else val_acc
    return val_loss, val_acc, val_top5


# ══════════════════════════════════════════════════════════
#  PHASE 1: Train SE-ResNet-50 V6 Teacher
# ══════════════════════════════════════════════════════════

def train_teacher(train_items, val_items, species_to_idx, num_species,
                  output_path, log_fn, batch_size=16, num_epochs=200,
                  lr=3e-4, patience=40, num_workers=2,
                  accumulate_steps=4, gradient_checkpointing=True):
    """Train SE-ResNet-50 V6 teacher with dual-channel mel input."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log_fn(f"Device: {device} ({torch.cuda.get_device_name(0)})")

    train_dataset = BirdDatasetV6(train_items, species_to_idx, augment=True)
    val_dataset = BirdDatasetV6(val_items, species_to_idx, augment=False)

    class_weights, sampler = compute_class_weights(train_items, species_to_idx, num_species)

    train_loader = DataLoader(
        train_dataset, batch_size=batch_size,
        sampler=sampler, num_workers=num_workers,
        pin_memory=True, persistent_workers=num_workers > 0,
    )
    val_loader = DataLoader(
        val_dataset, batch_size=batch_size,
        shuffle=False, num_workers=num_workers,
        pin_memory=True, persistent_workers=num_workers > 0,
    )

    model = SEResNet50V6(num_species=num_species, in_channels=2, drop_path_rate=0.1,
                          gradient_checkpointing=gradient_checkpointing).to(device)
    log_fn(f"Teacher: SE-ResNet-50 V6, {count_parameters(model):,} params, GeM pooling, dual-channel")
    log_fn(f"  Gradient checkpointing: {gradient_checkpointing}, Accumulate: {accumulate_steps} (eff_batch={batch_size*accumulate_steps})")

    criterion = FocalLoss(
        weight=class_weights.to(device), gamma=2.0, label_smoothing=0.05,
    )
    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-3)

    scheduler = optim.lr_scheduler.CosineAnnealingWarmRestarts(
        optimizer, T_0=20, T_mult=2, eta_min=1e-6,
    )
    warmup_scheduler = optim.lr_scheduler.LinearLR(
        optimizer, start_factor=0.01, total_iters=5,
    )
    combined_scheduler = optim.lr_scheduler.SequentialLR(
        optimizer, [warmup_scheduler, scheduler], milestones=[5],
    )

    ema = EMA(model, decay=0.999, warmup_steps=500)
    scaler = GradScaler("cuda") if device.type == "cuda" else None

    best_val_acc = 0.0
    best_top5 = 0.0
    patience_counter = 0
    total_data_points = 0
    history = {"train_loss": [], "val_loss": [], "train_acc": [],
               "val_acc": [], "val_top5": [], "lr": []}

    progress_path = output_path / "progress.json"
    start_time = time.time()

    log_fn(f"{'='*70}")
    log_fn(f"Phase 1: Train Teacher SE-ResNet-50 V6 (Dual-Channel + GeM)")
    log_fn(f"  Epochs: {num_epochs}, Batch: {batch_size}x{accumulate_steps}={batch_size*accumulate_steps}, LR: {lr}")
    log_fn(f"  Input: (B, 2, 96, {TARGET_FRAMES}) @ 48kHz, 3s segments")
    log_fn(f"  Samples/epoch: {len(train_items)}")
    log_fn(f"  Target data points: {len(train_items) * num_epochs:,}")
    log_fn(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_fn(f"{'='*70}")

    for epoch in range(num_epochs):
        epoch_start = time.time()
        model.train()
        train_loss = 0.0
        train_correct = 0
        train_total = 0
        optimizer.zero_grad(set_to_none=True)

        for step, (batch_x, batch_y) in enumerate(train_loader):
            batch_x = batch_x.to(device, non_blocking=True)
            batch_y = batch_y.to(device, non_blocking=True)

            aug_choice = np.random.random()
            use_cutmix = aug_choice < 0.3
            use_mixup = 0.3 <= aug_choice < 0.6

            if use_cutmix:
                batch_x, y_b, y_a, lam = cutmix_data(batch_x, batch_y, alpha=1.0)
            elif use_mixup:
                batch_x, y_a, y_b, lam = mixup_data(batch_x, batch_y, alpha=0.3)

            if scaler:
                with autocast("cuda"):
                    outputs = model(batch_x)
                    if use_cutmix or use_mixup:
                        loss = mixup_criterion(criterion, outputs, y_a, y_b, lam)
                    else:
                        loss = criterion(outputs, batch_y)
                    loss = loss / accumulate_steps
                scaler.scale(loss).backward()
                if (step + 1) % accumulate_steps == 0 or (step + 1) == len(train_loader):
                    scaler.unscale_(optimizer)
                    nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    scaler.step(optimizer)
                    scaler.update()
                    optimizer.zero_grad(set_to_none=True)
                    ema.update(model)
            else:
                outputs = model(batch_x)
                if use_cutmix or use_mixup:
                    loss = mixup_criterion(criterion, outputs, y_a, y_b, lam)
                else:
                    loss = criterion(outputs, batch_y)
                loss = loss / accumulate_steps
                loss.backward()
                if (step + 1) % accumulate_steps == 0 or (step + 1) == len(train_loader):
                    nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    optimizer.step()
                    optimizer.zero_grad(set_to_none=True)
                    ema.update(model)

            train_loss += loss.item() * accumulate_steps * batch_x.size(0)
            _, predicted = outputs.max(1)
            train_total += batch_y.size(0)
            train_correct += predicted.eq(batch_y).sum().item()
            total_data_points += batch_x.size(0)

        combined_scheduler.step()
        train_loss /= max(train_total, 1)
        train_acc = train_correct / max(train_total, 1)

        # Validate with EMA weights
        ema.apply_shadow(model)
        val_loss, val_acc, val_top5 = evaluate(model, val_loader, device, scaler, num_species)
        ema.restore(model)

        current_lr = optimizer.param_groups[0]["lr"]
        epoch_time = time.time() - epoch_start

        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["train_acc"].append(train_acc)
        history["val_acc"].append(val_acc)
        history["val_top5"].append(val_top5)
        history["lr"].append(current_lr)

        improved = ""
        if val_acc > best_val_acc + 0.001:
            best_val_acc = val_acc
            best_top5 = val_top5
            patience_counter = 0
            improved = " ★ BEST"

            ema.apply_shadow(model)
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "val_acc": val_acc,
                "val_top5": val_top5,
                "num_species": num_species,
                "model_type": "teacher",
                "version": "v6-teacher",
            }, output_path / "best_teacher_v6.pth")
            ema.restore(model)
        else:
            patience_counter += 1

        log_fn(f"T Ep [{epoch+1:3d}/{num_epochs}] "
               f"L: {train_loss:.3f}/{val_loss:.3f} "
               f"Acc: {train_acc:.3f}/{val_acc:.3f} "
               f"T5: {val_top5:.3f} "
               f"LR: {current_lr:.2e} "
               f"pts:{total_data_points:,} "
               f"({epoch_time:.1f}s){improved}")

        elapsed = time.time() - start_time
        with open(progress_path, 'w') as pf:
            json.dump({
                "phase": "v6-teacher",
                "status": "running",
                "epoch": epoch + 1,
                "total_epochs": num_epochs,
                "total_data_points": total_data_points,
                "train_acc": round(train_acc, 4),
                "val_acc": round(val_acc, 4),
                "val_top5": round(val_top5, 4),
                "best_val_acc": round(best_val_acc, 4),
                "best_top5": round(best_top5, 4),
                "patience_counter": patience_counter,
                "elapsed_minutes": round(elapsed / 60, 1),
                "timestamp": datetime.now().isoformat(),
            }, pf, indent=2)

        with open(output_path / "teacher_v6_history.json", "w") as hf:
            json.dump(history, hf)

        if patience_counter >= patience:
            log_fn(f"\nTeacher early stop at epoch {epoch+1} (patience={patience})")
            break

    # Save final teacher with EMA
    ema.apply_shadow(model)
    torch.save({
        "epoch": epoch + 1,
        "model_state_dict": model.state_dict(),
        "num_species": num_species,
        "model_type": "teacher",
        "version": "v6-teacher-final",
    }, output_path / "final_teacher_v6.pth")
    ema.restore(model)

    total_time = time.time() - start_time
    log_fn(f"\n{'='*70}")
    log_fn(f"Phase 1 Complete: Teacher SE-ResNet-50 V6")
    log_fn(f"  Best Val Acc: {best_val_acc:.4f}")
    log_fn(f"  Best Top-5:   {best_top5:.4f}")
    log_fn(f"  Data points:  {total_data_points:,}")
    log_fn(f"  Time:         {total_time/60:.1f} min")
    log_fn(f"{'='*70}\n")

    return total_data_points, best_val_acc, best_top5


# ══════════════════════════════════════════════════════════
#  PHASE 2: Knowledge Distillation → SE-ResNet-18 V6 Student
# ══════════════════════════════════════════════════════════

def train_student(train_items, val_items, species_to_idx, num_species,
                  output_path, log_fn, teacher_path,
                  batch_size=16, num_epochs=150, lr=3e-4,
                  patience=35, num_workers=2,
                  kd_temperature=4.0, kd_alpha=0.7,
                  total_data_points_offset=0,
                  accumulate_steps=4, gradient_checkpointing=True):
    """Train SE-ResNet-18 V6 student via knowledge distillation from teacher."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Load teacher (no grad checkpointing needed — inference only)
    teacher = SEResNet50V6(num_species=num_species, in_channels=2).to(device)
    ckpt = torch.load(teacher_path, map_location=device, weights_only=False)
    teacher.load_state_dict(ckpt["model_state_dict"])
    teacher.eval()
    for p in teacher.parameters():
        p.requires_grad = False
    log_fn(f"Teacher loaded: val_acc={ckpt.get('val_acc', '?'):.4f}")

    train_dataset = BirdDatasetV6(train_items, species_to_idx, augment=True)
    val_dataset = BirdDatasetV6(val_items, species_to_idx, augment=False)

    class_weights, sampler = compute_class_weights(train_items, species_to_idx, num_species)

    train_loader = DataLoader(
        train_dataset, batch_size=batch_size,
        sampler=sampler, num_workers=num_workers,
        pin_memory=True, persistent_workers=num_workers > 0,
    )
    val_loader = DataLoader(
        val_dataset, batch_size=batch_size,
        shuffle=False, num_workers=num_workers,
        pin_memory=True, persistent_workers=num_workers > 0,
    )

    student = SEResNet18V6(num_species=num_species, in_channels=2, drop_path_rate=0.05,
                             gradient_checkpointing=gradient_checkpointing).to(device)
    log_fn(f"Student: SE-ResNet-18 V6, {count_parameters(student):,} params, GeM pooling, dual-channel")
    log_fn(f"  Gradient checkpointing: {gradient_checkpointing}, Accumulate: {accumulate_steps} (eff_batch={batch_size*accumulate_steps})")

    hard_loss_fn = FocalLoss(
        weight=class_weights.to(device), gamma=2.0, label_smoothing=0.05,
    )
    kd_loss_fn = DistillationLoss(
        temperature=kd_temperature, alpha=kd_alpha, hard_loss_fn=hard_loss_fn,
    )

    optimizer = optim.AdamW(student.parameters(), lr=lr, weight_decay=1e-3)
    scheduler = optim.lr_scheduler.CosineAnnealingWarmRestarts(
        optimizer, T_0=20, T_mult=2, eta_min=1e-6,
    )
    warmup_scheduler = optim.lr_scheduler.LinearLR(
        optimizer, start_factor=0.01, total_iters=5,
    )
    combined_scheduler = optim.lr_scheduler.SequentialLR(
        optimizer, [warmup_scheduler, scheduler], milestones=[5],
    )

    ema = EMA(student, decay=0.999, warmup_steps=500)
    scaler = GradScaler("cuda") if device.type == "cuda" else None

    best_val_acc = 0.0
    best_top5 = 0.0
    patience_counter = 0
    total_data_points = total_data_points_offset
    history = {"train_loss": [], "val_loss": [], "train_acc": [],
               "val_acc": [], "val_top5": [], "lr": []}

    progress_path = output_path / "progress.json"
    start_time = time.time()

    log_fn(f"{'='*70}")
    log_fn(f"Phase 2: Knowledge Distillation \u2192 SE-ResNet-18 V6")
    log_fn(f"  Epochs: {num_epochs}, Batch: {batch_size}x{accumulate_steps}={batch_size*accumulate_steps}, T={kd_temperature}, \u03b1={kd_alpha}")
    log_fn(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_fn(f"{'='*70}")

    for epoch in range(num_epochs):
        epoch_start = time.time()
        student.train()
        train_loss = 0.0
        train_correct = 0
        train_total = 0
        optimizer.zero_grad(set_to_none=True)

        for step, (batch_x, batch_y) in enumerate(train_loader):
            batch_x = batch_x.to(device, non_blocking=True)
            batch_y = batch_y.to(device, non_blocking=True)

            aug_choice = np.random.random()
            use_cutmix = aug_choice < 0.25
            use_mixup = 0.25 <= aug_choice < 0.5

            if use_cutmix:
                batch_x, y_b, y_a, lam = cutmix_data(batch_x, batch_y, alpha=1.0)
            elif use_mixup:
                batch_x, y_a, y_b, lam = mixup_data(batch_x, batch_y, alpha=0.3)

            if scaler:
                with autocast("cuda"):
                    student_logits = student(batch_x)
                    with torch.no_grad():
                        teacher_logits = teacher(batch_x)

                    if use_cutmix or use_mixup:
                        loss_a = kd_loss_fn(student_logits, teacher_logits, y_a)
                        loss_b = kd_loss_fn(student_logits, teacher_logits, y_b)
                        loss = lam * loss_a + (1 - lam) * loss_b
                    else:
                        loss = kd_loss_fn(student_logits, teacher_logits, batch_y)
                    loss = loss / accumulate_steps

                scaler.scale(loss).backward()
                if (step + 1) % accumulate_steps == 0 or (step + 1) == len(train_loader):
                    scaler.unscale_(optimizer)
                    nn.utils.clip_grad_norm_(student.parameters(), 1.0)
                    scaler.step(optimizer)
                    scaler.update()
                    optimizer.zero_grad(set_to_none=True)
                    ema.update(student)
            else:
                student_logits = student(batch_x)
                with torch.no_grad():
                    teacher_logits = teacher(batch_x)

                if use_cutmix or use_mixup:
                    loss_a = kd_loss_fn(student_logits, teacher_logits, y_a)
                    loss_b = kd_loss_fn(student_logits, teacher_logits, y_b)
                    loss = lam * loss_a + (1 - lam) * loss_b
                else:
                    loss = kd_loss_fn(student_logits, teacher_logits, batch_y)
                loss = loss / accumulate_steps

                loss.backward()
                if (step + 1) % accumulate_steps == 0 or (step + 1) == len(train_loader):
                    nn.utils.clip_grad_norm_(student.parameters(), 1.0)
                    optimizer.step()
                    optimizer.zero_grad(set_to_none=True)
                    ema.update(student)

            train_loss += loss.item() * accumulate_steps * batch_x.size(0)
            _, predicted = student_logits.max(1)
            train_total += batch_y.size(0)
            train_correct += predicted.eq(batch_y).sum().item()
            total_data_points += batch_x.size(0)

        combined_scheduler.step()
        train_loss /= max(train_total, 1)
        train_acc = train_correct / max(train_total, 1)

        # Validate with EMA weights
        ema.apply_shadow(student)
        val_loss, val_acc, val_top5 = evaluate(student, val_loader, device, scaler, num_species)
        ema.restore(student)

        current_lr = optimizer.param_groups[0]["lr"]
        epoch_time = time.time() - epoch_start

        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["train_acc"].append(train_acc)
        history["val_acc"].append(val_acc)
        history["val_top5"].append(val_top5)
        history["lr"].append(current_lr)

        improved = ""
        if val_acc > best_val_acc + 0.001:
            best_val_acc = val_acc
            best_top5 = val_top5
            patience_counter = 0
            improved = " ★ BEST"

            ema.apply_shadow(student)
            torch.save({
                "epoch": epoch,
                "model_state_dict": student.state_dict(),
                "val_acc": val_acc,
                "val_top5": val_top5,
                "num_species": num_species,
                "model_type": "student",
                "version": "v6-student",
                "lite": False,
            }, output_path / "best_model_v6.pth")
            ema.restore(student)
        else:
            patience_counter += 1

        log_fn(f"S Ep [{epoch+1:3d}/{num_epochs}] "
               f"L: {train_loss:.3f}/{val_loss:.3f} "
               f"Acc: {train_acc:.3f}/{val_acc:.3f} "
               f"T5: {val_top5:.3f} "
               f"LR: {current_lr:.2e} "
               f"pts:{total_data_points:,} "
               f"({epoch_time:.1f}s){improved}")

        elapsed = time.time() - start_time
        with open(progress_path, 'w') as pf:
            json.dump({
                "phase": "v6-student",
                "status": "running",
                "epoch": epoch + 1,
                "total_epochs": num_epochs,
                "total_data_points": total_data_points,
                "train_acc": round(train_acc, 4),
                "val_acc": round(val_acc, 4),
                "val_top5": round(val_top5, 4),
                "best_val_acc": round(best_val_acc, 4),
                "best_top5": round(best_top5, 4),
                "patience_counter": patience_counter,
                "elapsed_minutes": round(elapsed / 60, 1),
                "timestamp": datetime.now().isoformat(),
            }, pf, indent=2)

        with open(output_path / "student_v6_history.json", "w") as hf:
            json.dump(history, hf)

        if patience_counter >= patience:
            log_fn(f"\nStudent early stop at epoch {epoch+1} (patience={patience})")
            break

    total_time = time.time() - start_time
    log_fn(f"\n{'='*70}")
    log_fn(f"Phase 2 Complete: Student SE-ResNet-18 V6")
    log_fn(f"  Best Val Acc: {best_val_acc:.4f}")
    log_fn(f"  Best Top-5:   {best_top5:.4f}")
    log_fn(f"  Data points:  {total_data_points:,}")
    log_fn(f"  Time:         {total_time/60:.1f} min")
    log_fn(f"{'='*70}\n")

    return total_data_points, best_val_acc, best_top5


# ══════════════════════════════════════════════════════════
#  MAIN: Two-Phase Pipeline
# ══════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="GPU Training v6 — SE-ResNet V6 + Dual-Channel + Distillation")
    parser.add_argument("--manifest", type=str, required=True)
    parser.add_argument("--output", type=str, default="./checkpoints")
    parser.add_argument("--teacher-epochs", type=int, default=200)
    parser.add_argument("--student-epochs", type=int, default=150)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--patience", type=int, default=40)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--kd-temperature", type=float, default=4.0)
    parser.add_argument("--kd-alpha", type=float, default=0.7)
    parser.add_argument("--accumulate-steps", type=int, default=4,
                        help="Gradient accumulation steps (effective_batch = batch_size * accumulate_steps)")
    parser.add_argument("--gradient-checkpointing", action="store_true", default=True,
                        help="Enable gradient checkpointing to save VRAM")
    parser.add_argument("--skip-teacher", action="store_true",
                        help="Skip Phase 1 if teacher already trained")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)

    # File logger
    log_path = output_path / "training_v6.log"
    file_handler = logging.FileHandler(log_path, mode='w', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(message)s'))
    logger = logging.getLogger('train_v6')
    logger.setLevel(logging.INFO)
    logger.handlers = [file_handler]

    def log_fn(msg):
        logger.info(msg)
        print(msg)

    log_fn(f"V6 Training Pipeline — SE-ResNet + Dual-Channel Mel + GeM + Distillation")
    log_fn(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_fn(f"PyTorch: {torch.__version__}")
    log_fn(f"CUDA: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        log_fn(f"GPU: {torch.cuda.get_device_name(0)}, "
               f"{torch.cuda.get_device_properties(0).total_memory / 1e9:.1f}GB")

    # Load data
    train_items, val_items, species_to_idx, idx_to_species, num_species = \
        setup_data(args.manifest)
    log_fn(f"Data: {len(train_items)} train, {len(val_items)} val, {num_species} species")

    # Save species mapping
    with open(output_path / "species_mapping.json", "w", encoding="utf-8") as f:
        json.dump({
            "species_to_idx": species_to_idx,
            "idx_to_species": {str(k): v for k, v in idx_to_species.items()},
        }, f, ensure_ascii=False, indent=2)

    grand_start = time.time()
    total_pts = 0

    # ── Phase 1: Teacher ──
    teacher_path = output_path / "best_teacher_v6.pth"
    if not args.skip_teacher:
        pts, t_acc, t_top5 = train_teacher(
            train_items, val_items, species_to_idx, num_species,
            output_path, log_fn,
            batch_size=args.batch_size, num_epochs=args.teacher_epochs,
            lr=args.lr, patience=args.patience, num_workers=args.workers,
            accumulate_steps=args.accumulate_steps,
            gradient_checkpointing=args.gradient_checkpointing,
        )
        total_pts = pts
        # Free teacher VRAM before student phase
        torch.cuda.empty_cache()
    else:
        log_fn(f"Skipping Phase 1: teacher exists at {teacher_path}")

    # ── Phase 2: Student Distillation ──
    if teacher_path.exists():
        pts, s_acc, s_top5 = train_student(
            train_items, val_items, species_to_idx, num_species,
            output_path, log_fn, teacher_path=str(teacher_path),
            batch_size=args.batch_size, num_epochs=args.student_epochs,
            lr=args.lr, patience=args.patience - 5,
            num_workers=args.workers,
            kd_temperature=args.kd_temperature, kd_alpha=args.kd_alpha,
            total_data_points_offset=total_pts,
            accumulate_steps=args.accumulate_steps,
            gradient_checkpointing=args.gradient_checkpointing,
        )
        total_pts = pts
    else:
        log_fn("ERROR: No teacher checkpoint found. Cannot run Phase 2.")

    # ── Final Summary ──
    grand_time = time.time() - grand_start
    progress_path = output_path / "progress.json"
    with open(progress_path, 'w') as pf:
        json.dump({
            "phase": "v6-completed",
            "status": "completed",
            "total_data_points": total_pts,
            "elapsed_minutes": round(grand_time / 60, 1),
            "timestamp": datetime.now().isoformat(),
        }, pf, indent=2)

    log_fn(f"\n{'='*70}")
    log_fn(f"V6 Training Pipeline Complete!")
    log_fn(f"{'='*70}")
    log_fn(f"Total data points: {total_pts:,}")
    log_fn(f"Total time: {grand_time/60:.1f} min")
    log_fn(f"Output: {output_path}")


if __name__ == "__main__":
    main()
