"""
GPU Training Pipeline v3 — 知识蒸馏 + SE注意力 + 满负荷GPU
基线: v2 = 56.83% val_acc (217种, 176ep, ResNet-18)

改进:
1. SE-ResNet-50 教师模型   — 26.5M参数, 通道注意力, Stochastic Depth
2. 知识蒸馏              — 教师软标签 → SE-ResNet-18 学生
3. CutMix + Mixup        — 两种混合增强随机切换
4. 大batch=96            — 充分利用RTX 3080 10GB VRAM
5. 所有v2特性保留        — Focal Loss, EMA, SpecAugment, Warm Restarts

两阶段流程:
  Phase 1: 训练 SE-ResNet-50 教师 (200 epochs)
  Phase 2: 蒸馏到 SE-ResNet-18 学生 (150 epochs)
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

from cnn_model_v2 import (
    SEResNet50, SEResNet18, DistillationLoss, cutmix_data,
    count_parameters,
)
from audio_processor import (
    load_audio, audio_to_mel_spectrogram, normalize_spectrogram,
    SEGMENT_DURATION, DEFAULT_SR, AudioAugmentor,
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


# ──────────────────── Dataset ────────────────────

class BirdSoundDatasetV4(Dataset):
    """V4 dataset with CutMix-compatible output."""

    def __init__(self, items, species_to_idx, augment=False,
                 augment_prob=0.6, spec_mask_num=2,
                 spec_freq_width=24, spec_time_width=40):
        self.items = items
        self.species_to_idx = species_to_idx
        self.augment = augment
        self.augment_prob = augment_prob
        self.spec_mask_num = spec_mask_num
        self.spec_freq_width = spec_freq_width
        self.spec_time_width = spec_time_width
        self.sr = DEFAULT_SR
        self.seg_dur = SEGMENT_DURATION
        self.audio_aug = AudioAugmentor()

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        item = self.items[idx]
        file_path = item["file_path"]
        species = item["species_scientific"]
        label = self.species_to_idx.get(species, 0)

        try:
            y, sr = load_audio(file_path, sr=self.sr, duration=self.seg_dur + 1)
        except Exception:
            mel = np.zeros((128, int(self.seg_dur * self.sr / 512) + 1), dtype=np.float32)
            return torch.FloatTensor(mel).unsqueeze(0), label

        target_len = int(self.seg_dur * self.sr)
        if len(y) > target_len:
            start = np.random.randint(0, len(y) - target_len)
            y = y[start:start + target_len]
        elif len(y) < target_len:
            y = np.pad(y, (0, target_len - len(y)))

        if self.augment:
            p = self.augment_prob
            if np.random.random() < p * 0.6:
                y = self.audio_aug.add_noise(y, noise_level=np.random.uniform(0.002, 0.01))
            if np.random.random() < p * 0.4:
                y = self.audio_aug.time_shift(y)
            if np.random.random() < p * 0.4:
                y = self.audio_aug.random_gain(y)

        mel = audio_to_mel_spectrogram(y, sr=self.sr)
        mel = normalize_spectrogram(mel)

        if self.augment:
            n_mels, n_frames = mel.shape
            if np.random.random() < self.augment_prob:
                mel = mel.copy()
                for _ in range(self.spec_mask_num):
                    f = np.random.randint(1, self.spec_freq_width + 1)
                    f0 = np.random.randint(0, max(1, n_mels - f))
                    mel[f0:f0 + f, :] = 0
                for _ in range(self.spec_mask_num):
                    t = np.random.randint(1, self.spec_time_width + 1)
                    t0 = np.random.randint(0, max(1, n_frames - t))
                    mel[:, t0:t0 + t] = 0

        tensor = torch.FloatTensor(mel).unsqueeze(0)
        return tensor, label


# ──────────────────── Mixup ────────────────────

def mixup_data(x, y, alpha=0.3):
    if alpha > 0:
        lam = np.random.beta(alpha, alpha)
    else:
        lam = 1.0
    index = torch.randperm(x.size(0), device=x.device)
    mixed_x = lam * x + (1 - lam) * x[index]
    return mixed_x, y, y[index], lam


def mixup_criterion(criterion, pred, y_a, y_b, lam):
    return lam * criterion(pred, y_a) + (1 - lam) * criterion(pred, y_b)


# ──────────────────── Shared Utilities ────────────────────

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
#  PHASE 1: Train SE-ResNet-50 Teacher
# ══════════════════════════════════════════════════════════

def train_teacher(train_items, val_items, species_to_idx, num_species,
                  output_path, log_fn, batch_size=96, num_epochs=200,
                  lr=3e-4, patience=40, num_workers=2):
    """Train SE-ResNet-50 teacher model at full GPU capacity."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log_fn(f"Device: {device} ({torch.cuda.get_device_name(0)})")

    train_dataset = BirdSoundDatasetV4(train_items, species_to_idx, augment=True)
    val_dataset = BirdSoundDatasetV4(val_items, species_to_idx, augment=False)

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

    model = SEResNet50(num_species=num_species, drop_path_rate=0.1).to(device)
    log_fn(f"Teacher: SE-ResNet-50, {count_parameters(model):,} params")

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
    log_fn(f"Phase 1: Train Teacher SE-ResNet-50")
    log_fn(f"  Epochs: {num_epochs}, Batch: {batch_size}, LR: {lr}")
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

            # Randomly choose CutMix or Mixup
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
                scaler.scale(loss).backward()
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
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                ema.update(model)

            train_loss += loss.item() * batch_x.size(0)
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
                "version": "v3-teacher",
            }, output_path / "best_teacher.pth")
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
                "phase": "teacher",
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

        with open(output_path / "teacher_history.json", "w") as hf:
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
        "version": "v3-teacher-final",
    }, output_path / "final_teacher.pth")
    ema.restore(model)

    total_time = time.time() - start_time
    log_fn(f"\n{'='*70}")
    log_fn(f"Phase 1 Complete: Teacher SE-ResNet-50")
    log_fn(f"  Best Val Acc: {best_val_acc:.4f}")
    log_fn(f"  Best Top-5:   {best_top5:.4f}")
    log_fn(f"  Data points:  {total_data_points:,}")
    log_fn(f"  Time:         {total_time/60:.1f} min")
    log_fn(f"{'='*70}\n")

    return total_data_points, best_val_acc, best_top5


# ══════════════════════════════════════════════════════════
#  PHASE 2: Knowledge Distillation → SE-ResNet-18 Student
# ══════════════════════════════════════════════════════════

def train_student(train_items, val_items, species_to_idx, num_species,
                  output_path, log_fn, teacher_path,
                  batch_size=96, num_epochs=150, lr=3e-4,
                  patience=35, num_workers=2,
                  kd_temperature=4.0, kd_alpha=0.7,
                  total_data_points_offset=0):
    """Train SE-ResNet-18 student via knowledge distillation from teacher."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Load teacher
    teacher = SEResNet50(num_species=num_species).to(device)
    ckpt = torch.load(teacher_path, map_location=device, weights_only=False)
    teacher.load_state_dict(ckpt["model_state_dict"])
    teacher.eval()
    for p in teacher.parameters():
        p.requires_grad = False
    log_fn(f"Teacher loaded: val_acc={ckpt.get('val_acc', '?'):.4f}")

    train_dataset = BirdSoundDatasetV4(train_items, species_to_idx, augment=True)
    val_dataset = BirdSoundDatasetV4(val_items, species_to_idx, augment=False)

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

    student = SEResNet18(num_species=num_species, drop_path_rate=0.05).to(device)
    log_fn(f"Student: SE-ResNet-18, {count_parameters(student):,} params")

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
    log_fn(f"Phase 2: Knowledge Distillation → SE-ResNet-18")
    log_fn(f"  Epochs: {num_epochs}, Batch: {batch_size}, T={kd_temperature}, α={kd_alpha}")
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

            # CutMix / Mixup (apply to both teacher and student input)
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

                scaler.scale(loss).backward()
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

                loss.backward()
                nn.utils.clip_grad_norm_(student.parameters(), 1.0)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                ema.update(student)

            train_loss += loss.item() * batch_x.size(0)
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
                "version": "v3-student",
                "lite": False,
            }, output_path / "best_model.pth")
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
                "phase": "student",
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

        with open(output_path / "student_history.json", "w") as hf:
            json.dump(history, hf)

        if patience_counter >= patience:
            log_fn(f"\nStudent early stop at epoch {epoch+1} (patience={patience})")
            break

    total_time = time.time() - start_time
    log_fn(f"\n{'='*70}")
    log_fn(f"Phase 2 Complete: Student SE-ResNet-18")
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
    parser = argparse.ArgumentParser(description="GPU Training v3 — SE-ResNet + Distillation")
    parser.add_argument("--manifest", type=str, required=True)
    parser.add_argument("--output", type=str, default="./checkpoints")
    parser.add_argument("--teacher-epochs", type=int, default=200)
    parser.add_argument("--student-epochs", type=int, default=150)
    parser.add_argument("--batch-size", type=int, default=96)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--patience", type=int, default=40)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--kd-temperature", type=float, default=4.0)
    parser.add_argument("--kd-alpha", type=float, default=0.7)
    parser.add_argument("--skip-teacher", action="store_true",
                        help="Skip Phase 1 if teacher already trained")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)

    # File logger
    log_path = output_path / "training_v3.log"
    file_handler = logging.FileHandler(log_path, mode='w', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(message)s'))
    logger = logging.getLogger('train_v3')
    logger.setLevel(logging.INFO)
    logger.handlers = [file_handler]

    def log_fn(msg):
        logger.info(msg)
        print(msg)

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
    teacher_path = output_path / "best_teacher.pth"
    if not args.skip_teacher:
        pts, t_acc, t_top5 = train_teacher(
            train_items, val_items, species_to_idx, num_species,
            output_path, log_fn,
            batch_size=args.batch_size, num_epochs=args.teacher_epochs,
            lr=args.lr, patience=args.patience, num_workers=args.workers,
        )
        total_pts = pts
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
        )
        total_pts = pts
    else:
        log_fn("ERROR: No teacher checkpoint found. Cannot run Phase 2.")

    # ── Final Summary ──
    grand_time = time.time() - grand_start
    progress_path = output_path / "progress.json"
    with open(progress_path, 'w') as pf:
        json.dump({
            "phase": "completed",
            "status": "completed",
            "total_data_points": total_pts,
            "elapsed_minutes": round(grand_time / 60, 1),
            "timestamp": datetime.now().isoformat(),
        }, pf, indent=2)

    log_fn(f"\n{'='*70}")
    log_fn(f"V3 Training Pipeline Complete!")
    log_fn(f"{'='*70}")
    log_fn(f"Total data points: {total_pts:,}")
    log_fn(f"Total time: {grand_time/60:.1f} min")
    log_fn(f"Output: {output_path}")


if __name__ == "__main__":
    main()
