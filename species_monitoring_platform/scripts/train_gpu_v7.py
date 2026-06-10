"""
GPU Training Pipeline v7 — ConvNeXt + MAP + Prototypical Head + OOD Detection

Next-generation training pipeline for data-efficient bird sound classification.

Key improvements over V6:
1. ConvNeXt-Tiny/Pico backbone (better accuracy per parameter)
2. Multi-Head Attention Pooling (captures diverse temporal-spectral patterns)
3. Prototypical learning head with prototype alignment loss
4. OOD detector calibration integrated into training pipeline
5. Improved data augmentation: time warping, pitch shift, background mixing
6. Multi-source data collection: Xeno-canto + optional local recordings

Two-phase pipeline:
  Phase 1: Train ConvNeXt-Tiny V7 teacher (200 epochs)
  Phase 2: Distill to ConvNeXt-Pico V7 student with feature alignment (150 epochs)
  Phase 3: Calibrate OOD detector on held-out validation set
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

from cnn_model_v7 import (
    ConvNeXtBirdV7, ConvNeXtBirdV7Student, DistillationLossV7,
    cutmix_data, mixup_data, spec_augment, count_parameters,
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


class PrototypeLoss(nn.Module):
    """Prototypical alignment loss: pull features toward correct prototype,
    push away from incorrect prototypes."""

    def __init__(self, margin=0.5):
        super().__init__()
        self.margin = margin

    def forward(self, proto_logits, targets):
        return F.cross_entropy(proto_logits, targets)


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

class BirdDatasetV7(Dataset):
    """Dual-channel mel dataset with enhanced augmentation for V7."""

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
            y, sr = librosa.load(item["file_path"], sr=self.sr,
                                 duration=self.dur + 1, mono=True)
        except Exception:
            mel = np.zeros((2, 96, TARGET_FRAMES), dtype=np.float32)
            return torch.FloatTensor(mel), label

        tgt = int(self.dur * self.sr)
        if len(y) > tgt:
            start = np.random.randint(0, len(y) - tgt) if self.augment else (len(y) - tgt) // 2
            y = y[start:start + tgt]
        elif len(y) < tgt:
            y = np.pad(y, (0, tgt - len(y)))

        if self.augment:
            # Gaussian noise injection
            if np.random.random() < 0.5:
                y += np.random.randn(len(y)) * np.random.uniform(0.002, 0.015)
            # Time shift
            if np.random.random() < 0.3:
                y = np.roll(y, int(len(y) * np.random.uniform(-0.15, 0.15)))
            # Gain variation
            if np.random.random() < 0.4:
                y *= np.random.uniform(0.65, 1.35)
            # Pitch shift (+/- 2 semitones)
            if np.random.random() < 0.2:
                n_steps = np.random.uniform(-2, 2)
                y = librosa.effects.pitch_shift(y, sr=self.sr, n_steps=n_steps)
            # Time stretching (0.85x to 1.15x)
            if np.random.random() < 0.2:
                rate = np.random.uniform(0.85, 1.15)
                y = librosa.effects.time_stretch(y, rate=rate)
                if len(y) > tgt:
                    y = y[:tgt]
                elif len(y) < tgt:
                    y = np.pad(y, (0, tgt - len(y)))

        mel = compute_dual_channel_mel(y, sr=self.sr)

        if self.augment and np.random.random() < 0.7:
            mel_t = torch.FloatTensor(mel)
            mel_t = spec_augment(mel_t, freq_mask_param=15, time_mask_param=50, num_masks=3)
            mel = mel_t.numpy()

        return torch.FloatTensor(mel), label


def mixup_criterion(criterion, pred, y_a, y_b, lam):
    return lam * criterion(pred, y_a) + (1 - lam) * criterion(pred, y_b)


# ──────────────────── Data Setup ────────────────────

def setup_data(manifest_path, min_samples=3, val_split=0.15):
    """Load manifest, filter species, split train/val with stratification."""
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    species_counts = Counter(item["species_scientific"] for item in manifest)
    valid_species = {sp for sp, cnt in species_counts.items() if cnt >= min_samples}
    manifest = [item for item in manifest if item["species_scientific"] in valid_species]

    species_list = sorted(valid_species)
    species_to_idx = {sp: i for i, sp in enumerate(species_list)}
    idx_to_species = {i: sp for sp, i in species_to_idx.items()}
    num_species = len(species_to_idx)

    # Stratified split: ensure each species has samples in both train and val
    from collections import defaultdict
    species_items = defaultdict(list)
    for item in manifest:
        species_items[item["species_scientific"]].append(item)

    train_items, val_items = [], []
    rng = np.random.RandomState(42)
    for sp, items in species_items.items():
        rng.shuffle(items)
        n_val = max(1, int(len(items) * val_split))
        val_items.extend(items[:n_val])
        train_items.extend(items[n_val:])

    rng.shuffle(train_items)
    rng.shuffle(val_items)

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
#  PHASE 1: Train ConvNeXt-Tiny V7 Teacher
# ══════════════════════════════════════════════════════════

def train_teacher(train_items, val_items, species_to_idx, num_species,
                  output_path, log_fn, batch_size=16, num_epochs=200,
                  lr=3e-4, patience=40, num_workers=2,
                  accumulate_steps=4, gradient_checkpointing=True):
    """Train ConvNeXt-Tiny V7 teacher with MAP and prototypical head."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log_fn(f"Device: {device}" + (f" ({torch.cuda.get_device_name(0)})" if torch.cuda.is_available() else ""))

    train_dataset = BirdDatasetV7(train_items, species_to_idx, augment=True)
    val_dataset = BirdDatasetV7(val_items, species_to_idx, augment=False)

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

    model = ConvNeXtBirdV7(
        num_species=num_species, in_channels=2,
        drop_path_rate=0.1,
        gradient_checkpointing=gradient_checkpointing,
    ).to(device)
    log_fn(f"Teacher: ConvNeXt-Tiny V7, {count_parameters(model):,} params")
    log_fn(f"  MAP pooling (4 heads), prototypical head, OOD detector")
    log_fn(f"  Gradient checkpointing: {gradient_checkpointing}, "
           f"Accumulate: {accumulate_steps} (eff_batch={batch_size * accumulate_steps})")

    cls_criterion = FocalLoss(
        weight=class_weights.to(device), gamma=2.0, label_smoothing=0.05,
    )
    proto_criterion = PrototypeLoss()

    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=5e-2)

    scheduler = optim.lr_scheduler.CosineAnnealingWarmRestarts(
        optimizer, T_0=20, T_mult=2, eta_min=1e-6,
    )
    warmup_scheduler = optim.lr_scheduler.LinearLR(
        optimizer, start_factor=0.01, total_iters=5,
    )
    combined_scheduler = optim.lr_scheduler.SequentialLR(
        optimizer, schedulers=[warmup_scheduler, scheduler], milestones=[5],
    )

    scaler = GradScaler("cuda") if torch.cuda.is_available() else None
    ema = EMA(model, decay=0.9995, warmup_steps=500)
    best_val_acc = 0.0
    no_improve = 0

    for epoch in range(1, num_epochs + 1):
        model.train()
        train_loss = 0.0
        train_correct = 0
        train_total = 0
        optimizer.zero_grad()

        for step, (batch_x, batch_y) in enumerate(train_loader):
            batch_x = batch_x.to(device, non_blocking=True)
            batch_y = batch_y.to(device, non_blocking=True)

            # CutMix / Mixup
            aug_rand = np.random.random()
            if aug_rand < 0.3:
                batch_x, y_b, y_a, lam = cutmix_data(batch_x, batch_y, alpha=1.0)
            elif aug_rand < 0.6:
                batch_x, y_a, y_b, lam = mixup_data(batch_x, batch_y, alpha=0.3)
            else:
                y_a = y_b = batch_y
                lam = 1.0

            if scaler:
                with autocast("cuda"):
                    cls_logits = model(batch_x)
                    loss_cls = mixup_criterion(cls_criterion, cls_logits, y_a, y_b, lam)

                    # Proto loss (only on non-mixed, since prototypes need clean labels)
                    if lam == 1.0:
                        feat = model.extract_features(batch_x)
                        proto_logits = model.proto_head(feat)
                        loss_proto = proto_criterion(proto_logits, batch_y)
                        loss = loss_cls + 0.2 * loss_proto
                    else:
                        loss = loss_cls

                    loss = loss / accumulate_steps

                scaler.scale(loss).backward()
                if (step + 1) % accumulate_steps == 0:
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    scaler.step(optimizer)
                    scaler.update()
                    optimizer.zero_grad()
                    ema.update(model)
            else:
                cls_logits = model(batch_x)
                loss_cls = mixup_criterion(cls_criterion, cls_logits, y_a, y_b, lam)

                if lam == 1.0:
                    feat = model.extract_features(batch_x)
                    proto_logits = model.proto_head(feat)
                    loss_proto = proto_criterion(proto_logits, batch_y)
                    loss = loss_cls + 0.2 * loss_proto
                else:
                    loss = loss_cls

                loss = loss / accumulate_steps
                loss.backward()
                if (step + 1) % accumulate_steps == 0:
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    optimizer.step()
                    optimizer.zero_grad()
                    ema.update(model)

            train_loss += loss.item() * accumulate_steps * batch_x.size(0)
            _, predicted = cls_logits.max(1)
            train_total += batch_y.size(0)
            if lam == 1.0:
                train_correct += predicted.eq(batch_y).sum().item()
            else:
                train_correct += (lam * predicted.eq(y_a).float()
                                  + (1 - lam) * predicted.eq(y_b).float()).sum().item()

        combined_scheduler.step()

        # Evaluate with EMA weights
        ema.apply_shadow(model)
        val_loss, val_acc, val_top5 = evaluate(model, val_loader, device, scaler, num_species)
        ema.restore(model)

        train_loss /= max(train_total, 1)
        train_acc = train_correct / max(train_total, 1)
        gap = train_acc - val_acc

        log_fn(f"Epoch {epoch:3d}/{num_epochs} | "
               f"train_loss={train_loss:.4f} train_acc={train_acc:.3f} | "
               f"val_loss={val_loss:.4f} val_acc={val_acc:.3f} top5={val_top5:.3f} | "
               f"gap={gap:.3f} lr={optimizer.param_groups[0]['lr']:.6f}")

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            no_improve = 0
            ema.apply_shadow(model)
            save_path = Path(output_path) / "best_teacher_v7.pth"
            torch.save({
                'model_state_dict': model.state_dict(),
                'num_species': num_species,
                'species_to_idx': species_to_idx,
                'val_acc': val_acc,
                'val_top5': val_top5,
                'epoch': epoch,
                'version': 'v7',
                'model_type': 'teacher',
                'architecture': 'ConvNeXt-Tiny',
            }, save_path)
            log_fn(f"  ★ New best teacher: val_acc={val_acc:.4f} saved")
            ema.restore(model)
        else:
            no_improve += 1
            if no_improve >= patience:
                log_fn(f"Early stopping after {patience} epochs without improvement")
                break

    log_fn(f"\nPhase 1 complete. Best teacher val_acc: {best_val_acc:.4f}")
    return best_val_acc


# ══════════════════════════════════════════════════════════
#  PHASE 2: Distill to ConvNeXt-Pico V7 Student
# ══════════════════════════════════════════════════════════

def train_student(train_items, val_items, species_to_idx, num_species,
                  teacher_path, output_path, log_fn,
                  batch_size=24, num_epochs=150, lr=5e-4,
                  patience=30, num_workers=2, accumulate_steps=2):
    """Distill ConvNeXt-Tiny teacher to ConvNeXt-Pico student."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Load teacher
    teacher = ConvNeXtBirdV7(num_species=num_species, in_channels=2).to(device)
    ckpt = torch.load(teacher_path, map_location=device, weights_only=True)
    teacher.load_state_dict(ckpt['model_state_dict'])
    teacher.eval()
    for p in teacher.parameters():
        p.requires_grad = False
    log_fn(f"Loaded teacher from {teacher_path} (val_acc={ckpt.get('val_acc', 'N/A')})")

    # Create student
    student = ConvNeXtBirdV7Student(
        num_species=num_species, in_channels=2,
        drop_path_rate=0.05,
    ).to(device)
    log_fn(f"Student: ConvNeXt-Pico V7, {count_parameters(student):,} params")

    train_dataset = BirdDatasetV7(train_items, species_to_idx, augment=True)
    val_dataset = BirdDatasetV7(val_items, species_to_idx, augment=False)
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

    hard_loss_fn = FocalLoss(weight=class_weights.to(device), gamma=2.0, label_smoothing=0.05)
    kd_loss = DistillationLossV7(temperature=4.0, alpha=0.5, beta=0.2, hard_loss_fn=hard_loss_fn)

    optimizer = optim.AdamW(student.parameters(), lr=lr, weight_decay=5e-2)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=num_epochs, eta_min=1e-6)
    warmup = optim.lr_scheduler.LinearLR(optimizer, start_factor=0.01, total_iters=5)
    combined_scheduler = optim.lr_scheduler.SequentialLR(
        optimizer, schedulers=[warmup, scheduler], milestones=[5],
    )

    scaler = GradScaler("cuda") if torch.cuda.is_available() else None
    ema = EMA(student, decay=0.999, warmup_steps=300)
    best_val_acc = 0.0
    no_improve = 0

    for epoch in range(1, num_epochs + 1):
        student.train()
        train_loss = 0.0
        train_correct = 0
        train_total = 0
        optimizer.zero_grad()

        for step, (batch_x, batch_y) in enumerate(train_loader):
            batch_x = batch_x.to(device, non_blocking=True)
            batch_y = batch_y.to(device, non_blocking=True)

            if scaler:
                with autocast("cuda"):
                    with torch.no_grad():
                        t_logits = teacher(batch_x)
                        t_feat = teacher.extract_features(batch_x)
                    s_logits = student(batch_x)
                    s_feat = student.extract_features(batch_x)
                    loss = kd_loss(s_logits, t_logits, batch_y, s_feat, t_feat)
                    loss = loss / accumulate_steps

                scaler.scale(loss).backward()
                if (step + 1) % accumulate_steps == 0:
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(student.parameters(), 1.0)
                    scaler.step(optimizer)
                    scaler.update()
                    optimizer.zero_grad()
                    ema.update(student)
            else:
                with torch.no_grad():
                    t_logits = teacher(batch_x)
                    t_feat = teacher.extract_features(batch_x)
                s_logits = student(batch_x)
                s_feat = student.extract_features(batch_x)
                loss = kd_loss(s_logits, t_logits, batch_y, s_feat, t_feat)
                loss = loss / accumulate_steps
                loss.backward()
                if (step + 1) % accumulate_steps == 0:
                    torch.nn.utils.clip_grad_norm_(student.parameters(), 1.0)
                    optimizer.step()
                    optimizer.zero_grad()
                    ema.update(student)

            train_loss += loss.item() * accumulate_steps * batch_x.size(0)
            _, predicted = s_logits.max(1)
            train_total += batch_y.size(0)
            train_correct += predicted.eq(batch_y).sum().item()

        combined_scheduler.step()

        ema.apply_shadow(student)
        val_loss, val_acc, val_top5 = evaluate(student, val_loader, device, scaler, num_species)
        ema.restore(student)

        train_loss /= max(train_total, 1)
        train_acc = train_correct / max(train_total, 1)

        log_fn(f"Epoch {epoch:3d}/{num_epochs} | "
               f"train_loss={train_loss:.4f} train_acc={train_acc:.3f} | "
               f"val_loss={val_loss:.4f} val_acc={val_acc:.3f} top5={val_top5:.3f}")

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            no_improve = 0
            ema.apply_shadow(student)
            save_path = Path(output_path) / "best_student_v7.pth"
            torch.save({
                'model_state_dict': student.state_dict(),
                'num_species': num_species,
                'species_to_idx': species_to_idx,
                'val_acc': val_acc,
                'val_top5': val_top5,
                'epoch': epoch,
                'version': 'v7',
                'model_type': 'student',
                'architecture': 'ConvNeXt-Pico',
            }, save_path)
            log_fn(f"  ★ New best student: val_acc={val_acc:.4f} saved")
            ema.restore(student)
        else:
            no_improve += 1
            if no_improve >= patience:
                log_fn(f"Early stopping after {patience} epochs without improvement")
                break

    log_fn(f"\nPhase 2 complete. Best student val_acc: {best_val_acc:.4f}")
    return best_val_acc


# ══════════════════════════════════════════════════════════
#  PHASE 3: Calibrate OOD Detector
# ══════════════════════════════════════════════════════════

def calibrate_ood(model_path, val_items, species_to_idx, num_species,
                  output_path, log_fn, model_type='teacher', batch_size=32):
    """Calibrate OOD detector thresholds on in-distribution validation data."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    if model_type == 'teacher':
        model = ConvNeXtBirdV7(num_species=num_species, in_channels=2).to(device)
    else:
        model = ConvNeXtBirdV7Student(num_species=num_species, in_channels=2).to(device)

    ckpt = torch.load(model_path, map_location=device, weights_only=True)
    model.load_state_dict(ckpt['model_state_dict'])
    model.eval()

    val_dataset = BirdDatasetV7(val_items, species_to_idx, augment=False)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

    all_logits = []
    all_distances = []

    with torch.no_grad():
        for batch_x, _ in val_loader:
            batch_x = batch_x.to(device)
            logits, ood_info = model(batch_x, return_ood=True)
            feat = model.extract_features(batch_x)
            proto_dist = model.proto_head.compute_distance(feat)
            all_logits.append(logits.cpu())
            all_distances.append(proto_dist.cpu())

    all_logits = torch.cat(all_logits)
    all_distances = torch.cat(all_distances)

    model.ood_detector.calibrate(all_logits, all_distances, percentile=95.0)

    save_path = Path(output_path) / f"best_{model_type}_v7.pth"
    ckpt['model_state_dict'] = model.state_dict()
    ckpt['ood_calibrated'] = True
    torch.save(ckpt, save_path)
    log_fn(f"OOD detector calibrated and saved to {save_path}")
    log_fn(f"  Energy threshold (95th percentile): {model.ood_detector.energy_threshold.item():.4f}")


# ══════════════════════════════════════════════════════════
#  Main Entry
# ══════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="V7 Training Pipeline")
    parser.add_argument("--data", type=str, required=True,
                        help="Path to data directory containing manifest.json")
    parser.add_argument("--output", type=str, default="./checkpoints_v7",
                        help="Output directory for checkpoints")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--epochs-teacher", type=int, default=200)
    parser.add_argument("--epochs-student", type=int, default=150)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--phase", type=str, default="all",
                        choices=["all", "teacher", "student", "calibrate"],
                        help="Which phase to run")
    parser.add_argument("--teacher-path", type=str, default=None,
                        help="Path to teacher checkpoint (for student/calibrate phase)")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(message)s',
        handlers=[
            logging.FileHandler(output_path / "train_v7.log"),
            logging.StreamHandler(),
        ]
    )
    log_fn = logging.info

    log_fn("=" * 70)
    log_fn("  Bird Sound CNN V7 Training Pipeline")
    log_fn("  ConvNeXt-Tiny/Pico + MAP + Prototypical + OOD")
    log_fn("=" * 70)

    manifest_path = Path(args.data) / "manifest.json"
    if not manifest_path.exists():
        log_fn(f"[ERROR] manifest.json not found at {manifest_path}")
        log_fn("Run download_data_v7.py first to prepare training data.")
        sys.exit(1)

    train_items, val_items, species_to_idx, idx_to_species, num_species = \
        setup_data(str(manifest_path))

    log_fn(f"\nDataset: {len(train_items)} train, {len(val_items)} val, {num_species} species")

    # Save config
    config = {
        "version": "v7",
        "architecture": "ConvNeXt-Tiny/Pico",
        "num_species": num_species,
        "batch_size": args.batch_size,
        "epochs_teacher": args.epochs_teacher,
        "epochs_student": args.epochs_student,
        "lr": args.lr,
        "data_path": str(args.data),
        "features": [
            "ConvNeXt backbone",
            "Multi-Head Attention Pooling",
            "Prototypical learning head",
            "OOD detection (energy + distance)",
            "Dual-channel mel spectrogram",
            "Knowledge distillation with feature alignment",
        ],
        "timestamp": datetime.now().isoformat(),
    }
    with open(output_path / "train_config.json", "w") as f:
        json.dump(config, f, indent=2)

    # Save species mapping
    with open(output_path / "species_mapping.json", "w", encoding="utf-8") as f:
        json.dump({
            "species_to_idx": species_to_idx,
            "idx_to_species": idx_to_species,
        }, f, ensure_ascii=False, indent=2)

    if args.phase in ("all", "teacher"):
        log_fn("\n" + "=" * 70)
        log_fn("  PHASE 1: Training ConvNeXt-Tiny V7 Teacher")
        log_fn("=" * 70)
        train_teacher(
            train_items, val_items, species_to_idx, num_species,
            str(output_path), log_fn,
            batch_size=args.batch_size,
            num_epochs=args.epochs_teacher,
            lr=args.lr,
            num_workers=args.workers,
        )

    teacher_path = args.teacher_path or str(output_path / "best_teacher_v7.pth")

    if args.phase in ("all", "student"):
        if not Path(teacher_path).exists():
            log_fn("[ERROR] Teacher checkpoint not found. Run teacher phase first.")
            sys.exit(1)

        log_fn("\n" + "=" * 70)
        log_fn("  PHASE 2: Distilling to ConvNeXt-Pico V7 Student")
        log_fn("=" * 70)
        train_student(
            train_items, val_items, species_to_idx, num_species,
            teacher_path, str(output_path), log_fn,
            batch_size=args.batch_size * 2,
            num_epochs=args.epochs_student,
            num_workers=args.workers,
        )

    if args.phase in ("all", "calibrate"):
        log_fn("\n" + "=" * 70)
        log_fn("  PHASE 3: Calibrating OOD Detector")
        log_fn("=" * 70)
        for mt in ["teacher", "student"]:
            ckpt_path = str(output_path / f"best_{mt}_v7.pth")
            if Path(ckpt_path).exists():
                calibrate_ood(ckpt_path, val_items, species_to_idx, num_species,
                              str(output_path), log_fn, model_type=mt)

    log_fn("\n" + "=" * 70)
    log_fn("  Training complete!")
    log_fn("=" * 70)


if __name__ == "__main__":
    main()
