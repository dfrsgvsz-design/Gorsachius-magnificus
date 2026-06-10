"""
GPU Training Pipeline v2 — 架构改进版
基线: v1 = 54.47% val_acc (217种, 80ep)

改进:
1. Focal Loss        — 自适应难样本加权, 更好处理类别不平衡
2. EMA               — 指数移动平均权重, 更平滑的泛化
3. 更强SpecAugment   — 多次freq/time mask + mixup增强
4. Cosine Warm Restarts — 多周期余弦退火, 避免陷入局部最优
5. 梯度累积          — 等效更大batch size
"""

import os
import sys
import json
import time
import copy
import math
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

from cnn_model import create_model, count_parameters
from audio_processor import (
    load_audio, audio_to_mel_spectrogram, normalize_spectrogram,
    SEGMENT_DURATION, DEFAULT_SR, AudioAugmentor, SpectrogramAugmentor,
)


# ──────────────────── Focal Loss ────────────────────

class FocalLoss(nn.Module):
    """Focal Loss: down-weights easy examples, focuses on hard ones.
    
    FL(p_t) = -alpha_t * (1 - p_t)^gamma * log(p_t)
    
    gamma=0 reduces to standard cross-entropy.
    gamma=2 is the standard setting from Lin et al. (2017).
    """

    def __init__(self, weight=None, gamma=2.0, label_smoothing=0.0, reduction='mean'):
        super().__init__()
        self.gamma = gamma
        self.weight = weight
        self.label_smoothing = label_smoothing
        self.reduction = reduction

    def forward(self, inputs, targets):
        ce_loss = F.cross_entropy(
            inputs, targets,
            weight=self.weight,
            label_smoothing=self.label_smoothing,
            reduction='none',
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
    """Exponential Moving Average of model weights with warmup.
    
    Dynamic decay: decay_t = min(target_decay, (1 + step) / (warmup + step))
    This ramps from ~0 to target_decay over warmup steps,
    avoiding the slow-start problem where shadow ≈ random init.
    """

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


# ──────────────────── Config ────────────────────

class TrainConfigV2:
    manifest_path: str = ""
    output_dir: str = ""
    val_split: float = 0.15
    min_samples_per_class: int = 3

    lite: bool = False
    num_epochs: int = 200
    batch_size: int = 48
    lr: float = 3e-4
    weight_decay: float = 1e-3
    warmup_epochs: int = 5
    grad_clip: float = 1.0
    grad_accum_steps: int = 2        # Effective batch = 48*2 = 96

    # Focal Loss
    focal_gamma: float = 2.0
    label_smoothing: float = 0.05

    # Augmentation
    mixup_alpha: float = 0.3
    augment_prob: float = 0.6
    spec_mask_num: int = 2            # Number of freq/time masks
    spec_freq_width: int = 24         # Max freq mask width
    spec_time_width: int = 40         # Max time mask width

    # EMA
    ema_decay: float = 0.999

    # Cosine warm restarts
    T_0: int = 20                     # First cycle length
    T_mult: int = 2                   # Cycle length multiplier

    # Early stopping
    patience: int = 40
    min_delta: float = 0.001

    num_workers: int = 2
    use_amp: bool = True


# ──────────────────── Dataset ────────────────────

class BirdSoundDatasetV3(Dataset):
    """Enhanced dataset with stronger augmentation."""

    def __init__(self, items, species_to_idx, augment=False, config=None):
        self.items = items
        self.species_to_idx = species_to_idx
        self.augment = augment
        self.config = config or TrainConfigV2()
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

        # Audio augmentation
        if self.augment:
            p = self.config.augment_prob
            if np.random.random() < p * 0.6:
                y = self.audio_aug.add_noise(y, noise_level=np.random.uniform(0.002, 0.01))
            if np.random.random() < p * 0.4:
                y = self.audio_aug.time_shift(y)
            if np.random.random() < p * 0.4:
                y = self.audio_aug.random_gain(y)

        # Mel-spectrogram
        mel = audio_to_mel_spectrogram(y, sr=self.sr)
        mel = normalize_spectrogram(mel)

        # Stronger SpecAugment
        if self.augment:
            p = self.config.augment_prob
            n_mels, n_frames = mel.shape
            apply_mask = np.random.random() < p
            if apply_mask:
                mel = mel.copy()
                # Multiple frequency masks
                for _ in range(self.config.spec_mask_num):
                    f = np.random.randint(1, self.config.spec_freq_width + 1)
                    f0 = np.random.randint(0, max(1, n_mels - f))
                    mel[f0:f0 + f, :] = 0
                # Multiple time masks
                for _ in range(self.config.spec_mask_num):
                    t = np.random.randint(1, self.config.spec_time_width + 1)
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
    y_a, y_b = y, y[index]
    return mixed_x, y_a, y_b, lam


def mixup_criterion(criterion, pred, y_a, y_b, lam):
    return lam * criterion(pred, y_a) + (1 - lam) * criterion(pred, y_b)


# ──────────────────── Training ────────────────────

def train_model(config: TrainConfigV2):
    output_path = Path(config.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # ── Load manifest ──
    with open(config.manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    print(f"Total recordings: {len(manifest)}")

    species_counts = Counter(item["species_scientific"] for item in manifest)
    valid_species = {sp for sp, cnt in species_counts.items()
                     if cnt >= config.min_samples_per_class}
    manifest = [item for item in manifest if item["species_scientific"] in valid_species]
    print(f"After filter ({config.min_samples_per_class}): {len(manifest)} recs, {len(valid_species)} species")

    species_list = sorted(valid_species)
    species_to_idx = {sp: i for i, sp in enumerate(species_list)}
    idx_to_species = {i: sp for sp, i in species_to_idx.items()}
    num_species = len(species_to_idx)
    print(f"Species: {num_species}")

    mapping_path = output_path / "species_mapping.json"
    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump({
            "species_to_idx": species_to_idx,
            "idx_to_species": {str(k): v for k, v in idx_to_species.items()},
        }, f, ensure_ascii=False, indent=2)

    # ── Split ──
    np.random.seed(42)
    np.random.shuffle(manifest)
    val_size = int(len(manifest) * config.val_split)
    train_items = manifest[val_size:]
    val_items = manifest[:val_size]

    train_dataset = BirdSoundDatasetV3(train_items, species_to_idx, augment=True, config=config)
    val_dataset = BirdSoundDatasetV3(val_items, species_to_idx, augment=False, config=config)

    # ── Class weights ──
    train_labels = [species_to_idx.get(item["species_scientific"], 0) for item in train_items]
    class_counts = Counter(train_labels)
    class_weights = torch.FloatTensor([
        1.0 / max(class_counts.get(i, 1), 1) for i in range(num_species)
    ])
    class_weights = class_weights / class_weights.sum() * num_species

    sample_weights = [1.0 / max(class_counts.get(lbl, 1), 1) for lbl in train_labels]
    sampler = WeightedRandomSampler(sample_weights, len(sample_weights), replacement=True)

    train_loader = DataLoader(
        train_dataset, batch_size=config.batch_size,
        sampler=sampler, num_workers=config.num_workers,
        pin_memory=True, drop_last=True,
    )
    val_loader = DataLoader(
        val_dataset, batch_size=config.batch_size,
        shuffle=False, num_workers=config.num_workers,
        pin_memory=True,
    )

    print(f"Train: {len(train_dataset)}, Val: {len(val_dataset)}")

    # ── Model ──
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = create_model(num_species=num_species, lite=config.lite).to(device)
    print(f"Model: {'Lite' if config.lite else 'Full ResNet'} on {device}")
    print(f"Parameters: {count_parameters(model):,}")

    # ── Focal Loss ──
    criterion = FocalLoss(
        weight=class_weights.to(device),
        gamma=config.focal_gamma,
        label_smoothing=config.label_smoothing,
    )
    print(f"Loss: FocalLoss(gamma={config.focal_gamma}, ls={config.label_smoothing})")

    # ── Optimizer ──
    optimizer = optim.AdamW(
        model.parameters(), lr=config.lr, weight_decay=config.weight_decay,
    )

    # ── Cosine Warm Restarts ──
    scheduler = optim.lr_scheduler.CosineAnnealingWarmRestarts(
        optimizer, T_0=config.T_0, T_mult=config.T_mult, eta_min=1e-6,
    )
    # Manual warmup on top of scheduler
    warmup_scheduler = optim.lr_scheduler.LinearLR(
        optimizer, start_factor=0.01, total_iters=config.warmup_epochs,
    )
    combined_scheduler = optim.lr_scheduler.SequentialLR(
        optimizer, [warmup_scheduler, scheduler],
        milestones=[config.warmup_epochs],
    )

    # ── EMA ──
    ema = EMA(model, decay=config.ema_decay)
    print(f"EMA: decay={config.ema_decay}")

    # ── AMP ──
    scaler = GradScaler("cuda") if config.use_amp and device.type == "cuda" else None

    # ── File logger ──
    log_path = output_path / "training.log"
    progress_path = output_path / "progress.json"
    file_handler = logging.FileHandler(log_path, mode='w', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(message)s'))
    logger = logging.getLogger('train_v2')
    logger.setLevel(logging.INFO)
    logger.handlers = [file_handler]

    def log(msg):
        logger.info(msg)
        print(msg)

    # ── Training loop ──
    best_val_acc = 0.0
    best_top5 = 0.0
    patience_counter = 0
    total_data_points = 0
    history = {
        "train_loss": [], "val_loss": [],
        "train_acc": [], "val_acc": [],
        "val_top5": [], "lr": [],
    }

    start_time = time.time()
    effective_batch = config.batch_size * config.grad_accum_steps
    log(f"{'='*70}")
    log(f"Training v2: {config.num_epochs} epochs, "
        f"batch={config.batch_size}x{config.grad_accum_steps}={effective_batch}, "
        f"AMP={'ON' if scaler else 'OFF'}")
    log(f"Train samples/epoch: {len(train_items)}, "
        f"Target data points: {len(train_items) * config.num_epochs:,}")
    log(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"{'='*70}")

    for epoch in range(config.num_epochs):
        epoch_start = time.time()

        # ── Train ──
        model.train()
        train_loss = 0.0
        train_correct = 0
        train_total = 0
        optimizer.zero_grad(set_to_none=True)

        for step, (batch_x, batch_y) in enumerate(train_loader):
            batch_x = batch_x.to(device, non_blocking=True)
            batch_y = batch_y.to(device, non_blocking=True)

            use_mixup = config.mixup_alpha > 0 and np.random.random() < 0.5
            if use_mixup:
                batch_x, y_a, y_b, lam = mixup_data(batch_x, batch_y, config.mixup_alpha)

            if scaler:
                with autocast("cuda"):
                    outputs = model(batch_x)
                    if use_mixup:
                        loss = mixup_criterion(criterion, outputs, y_a, y_b, lam)
                    else:
                        loss = criterion(outputs, batch_y)
                    loss = loss / config.grad_accum_steps
                scaler.scale(loss).backward()

                if (step + 1) % config.grad_accum_steps == 0:
                    scaler.unscale_(optimizer)
                    nn.utils.clip_grad_norm_(model.parameters(), config.grad_clip)
                    scaler.step(optimizer)
                    scaler.update()
                    optimizer.zero_grad(set_to_none=True)
                    ema.update(model)
            else:
                outputs = model(batch_x)
                if use_mixup:
                    loss = mixup_criterion(criterion, outputs, y_a, y_b, lam)
                else:
                    loss = criterion(outputs, batch_y)
                loss = loss / config.grad_accum_steps
                loss.backward()

                if (step + 1) % config.grad_accum_steps == 0:
                    nn.utils.clip_grad_norm_(model.parameters(), config.grad_clip)
                    optimizer.step()
                    optimizer.zero_grad(set_to_none=True)
                    ema.update(model)

            train_loss += loss.item() * config.grad_accum_steps * batch_x.size(0)
            _, predicted = outputs.max(1)
            train_total += batch_y.size(0)
            train_correct += predicted.eq(batch_y).sum().item()
            total_data_points += batch_x.size(0)

        combined_scheduler.step()

        train_loss /= max(train_total, 1)
        train_acc = train_correct / max(train_total, 1)

        # ── Validate with EMA weights ──
        ema.apply_shadow(model)
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

        ema.restore(model)

        val_loss /= max(val_total, 1)
        val_acc = val_correct / max(val_total, 1)
        val_top5 = val_top5_correct / max(val_total, 1) if num_species >= 5 else val_acc

        current_lr = optimizer.param_groups[0]["lr"]
        epoch_time = time.time() - epoch_start

        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["train_acc"].append(train_acc)
        history["val_acc"].append(val_acc)
        history["val_top5"].append(val_top5)
        history["lr"].append(current_lr)

        improved = ""
        if val_acc > best_val_acc + config.min_delta:
            best_val_acc = val_acc
            best_top5 = val_top5
            patience_counter = 0
            improved = " ★ BEST"

            # Save EMA weights as best model
            ema.apply_shadow(model)
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "val_acc": val_acc,
                "val_top5": val_top5,
                "num_species": num_species,
                "lite": config.lite,
                "version": "v2",
            }, output_path / "best_model.pth")
            ema.restore(model)
        else:
            patience_counter += 1

        log(f"Ep [{epoch+1:3d}/{config.num_epochs}] "
            f"L: {train_loss:.3f}/{val_loss:.3f} "
            f"Acc: {train_acc:.3f}/{val_acc:.3f} "
            f"T5: {val_top5:.3f} "
            f"LR: {current_lr:.2e} "
            f"pts:{total_data_points:,} "
            f"({epoch_time:.1f}s){improved}")

        # Write real-time progress JSON (overwrite each epoch)
        elapsed = time.time() - start_time
        with open(progress_path, 'w') as pf:
            json.dump({
                "status": "running",
                "epoch": epoch + 1,
                "total_epochs": config.num_epochs,
                "total_data_points": total_data_points,
                "train_loss": round(train_loss, 4),
                "train_acc": round(train_acc, 4),
                "val_acc": round(val_acc, 4),
                "val_top5": round(val_top5, 4),
                "best_val_acc": round(best_val_acc, 4),
                "best_top5": round(best_top5, 4),
                "lr": current_lr,
                "patience_counter": patience_counter,
                "elapsed_minutes": round(elapsed / 60, 1),
                "epoch_time_sec": round(epoch_time, 1),
                "timestamp": datetime.now().isoformat(),
            }, pf, indent=2)

        # Save history incrementally
        with open(output_path / "training_history.json", "w") as hf:
            json.dump(history, hf)

        if patience_counter >= config.patience:
            log(f"\nEarly stop at epoch {epoch+1} (patience={config.patience})")
            break

    # ── Final ──
    total_time = time.time() - start_time

    # Save final EMA model
    ema.apply_shadow(model)
    torch.save({
        "epoch": config.num_epochs,
        "model_state_dict": model.state_dict(),
        "num_species": num_species,
        "lite": config.lite,
        "version": "v2",
    }, output_path / "final_model.pth")
    ema.restore(model)

    with open(output_path / "training_history.json", "w") as f:
        json.dump(history, f, indent=2)

    with open(output_path / "train_config.json", "w") as f:
        json.dump({
            "version": "v2",
            "num_epochs": config.num_epochs,
            "batch_size": config.batch_size,
            "effective_batch": effective_batch,
            "lr": config.lr,
            "focal_gamma": config.focal_gamma,
            "label_smoothing": config.label_smoothing,
            "mixup_alpha": config.mixup_alpha,
            "ema_decay": config.ema_decay,
            "T_0": config.T_0,
            "T_mult": config.T_mult,
            "augment_prob": config.augment_prob,
            "num_species": num_species,
            "train_size": len(train_items),
            "val_size": len(val_items),
            "best_val_acc": best_val_acc,
            "best_val_top5": best_top5,
            "total_time_minutes": total_time / 60,
        }, f, indent=2)

    # Mark complete in progress
    with open(progress_path, 'w') as pf:
        json.dump({
            "status": "completed",
            "epoch": epoch + 1 if 'epoch' in dir() else 0,
            "total_epochs": config.num_epochs,
            "total_data_points": total_data_points,
            "best_val_acc": round(best_val_acc, 4),
            "best_top5": round(best_top5, 4),
            "elapsed_minutes": round(total_time / 60, 1),
            "timestamp": datetime.now().isoformat(),
        }, pf, indent=2)

    log(f"\n{'='*70}")
    log(f"Training v2 Complete!")
    log(f"{'='*70}")
    log(f"Best Val Acc:  {best_val_acc:.4f}")
    log(f"Best Top-5:    {best_top5:.4f}")
    log(f"Data points:   {total_data_points:,}")
    log(f"Time:          {total_time/60:.1f} min")
    log(f"Species:       {num_species}")
    log(f"Output:        {output_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="GPU Training v2 — Focal+EMA+SpecAug")
    parser.add_argument("--manifest", type=str, required=True)
    parser.add_argument("--output", type=str, default="./checkpoints")
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=48)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--lite", action="store_true")
    parser.add_argument("--no-amp", action="store_true")
    parser.add_argument("--patience", type=int, default=40)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--gamma", type=float, default=2.0)
    parser.add_argument("--ema-decay", type=float, default=0.999)
    args = parser.parse_args()

    cfg = TrainConfigV2()
    cfg.manifest_path = args.manifest
    cfg.output_dir = args.output
    cfg.num_epochs = args.epochs
    cfg.batch_size = args.batch_size
    cfg.lr = args.lr
    cfg.lite = args.lite
    cfg.use_amp = not args.no_amp
    cfg.patience = args.patience
    cfg.num_workers = args.workers
    cfg.focal_gamma = args.gamma
    cfg.ema_decay = args.ema_decay

    train_model(cfg)
