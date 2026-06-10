"""
GPU-Accelerated Training Pipeline — 基于BirdNET方法论的鸟声识别模型训练。

改进点 (vs 上一版本 43.59% val_acc):
1. 完整ResNet模型 (非lite版)  — 更强表达能力
2. 混合精度训练 (AMP)         — RTX 3080 Tensor Cores加速
3. 学习率Warmup + Cosine退火  — 更稳定的收敛
4. Mixup数据增强              — 减少过拟合
5. Label Smoothing             — 提高泛化能力
6. 梯度裁剪                   — 防止梯度爆炸
7. 多进程数据加载             — 充分利用CPU-GPU并行
8. Early Stopping              — 自动停止过拟合
9. 类别加权损失               — 处理不平衡数据
10. Top-5准确率监控            — 更全面的评估

目标: val_acc > 60% (254种), 为申请经费提供可靠初步结果。
"""

import os
import sys
import json
import time
import numpy as np
from pathlib import Path
from collections import Counter

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader, random_split, WeightedRandomSampler
from torch.amp import autocast, GradScaler

from cnn_model import create_model, count_parameters
from audio_processor import (
    load_audio, audio_to_mel_spectrogram, normalize_spectrogram,
    SEGMENT_DURATION, DEFAULT_SR, AudioAugmentor, SpectrogramAugmentor,
)


# ──────────────────── Config ────────────────────

class TrainConfig:
    # Data
    manifest_path: str = ""
    output_dir: str = ""
    val_split: float = 0.15
    min_samples_per_class: int = 3

    # Model
    lite: bool = False           # Use full ResNet (not lite)

    # Training
    num_epochs: int = 80
    batch_size: int = 48         # RTX 3080 10GB can handle 48-64
    lr: float = 3e-4
    weight_decay: float = 1e-3
    warmup_epochs: int = 5
    grad_clip: float = 1.0

    # Augmentation
    mixup_alpha: float = 0.2
    label_smoothing: float = 0.05
    augment_prob: float = 0.5

    # Early stopping
    patience: int = 20
    min_delta: float = 0.001

    # System
    num_workers: int = 4
    use_amp: bool = True         # Mixed precision


# ──────────────────── Dataset ────────────────────

class BirdSoundDatasetV2(Dataset):
    """Enhanced dataset with robust error handling and augmentation."""

    def __init__(self, items, species_to_idx, augment=False, config=None):
        self.items = items
        self.species_to_idx = species_to_idx
        self.augment = augment
        self.config = config or TrainConfig()
        self.sr = DEFAULT_SR
        self.seg_dur = SEGMENT_DURATION
        self.audio_aug = AudioAugmentor()
        self.spec_aug = SpectrogramAugmentor()

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

        # Random crop
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
                y = self.audio_aug.add_noise(y)
            if np.random.random() < p * 0.4:
                y = self.audio_aug.time_shift(y)
            if np.random.random() < p * 0.4:
                y = self.audio_aug.random_gain(y)

        # Mel-spectrogram
        mel = audio_to_mel_spectrogram(y, sr=self.sr)
        mel = normalize_spectrogram(mel)

        # Spectrogram augmentation
        if self.augment:
            p = self.config.augment_prob
            if np.random.random() < p * 0.6:
                mel = self.spec_aug.freq_mask(mel)
            if np.random.random() < p * 0.6:
                mel = self.spec_aug.time_mask(mel)

        tensor = torch.FloatTensor(mel).unsqueeze(0)
        return tensor, label


# ──────────────────── Mixup ────────────────────

def mixup_data(x, y, alpha=0.3):
    """Apply mixup augmentation."""
    if alpha > 0:
        lam = np.random.beta(alpha, alpha)
    else:
        lam = 1.0
    batch_size = x.size(0)
    index = torch.randperm(batch_size, device=x.device)
    mixed_x = lam * x + (1 - lam) * x[index]
    y_a, y_b = y, y[index]
    return mixed_x, y_a, y_b, lam


def mixup_criterion(criterion, pred, y_a, y_b, lam):
    return lam * criterion(pred, y_a) + (1 - lam) * criterion(pred, y_b)


# ──────────────────── Training ────────────────────

def train_model(config: TrainConfig):
    """Main training loop with all improvements."""

    output_path = Path(config.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # ── Load manifest ──
    with open(config.manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    print(f"Total recordings in manifest: {len(manifest)}")

    # Filter species with minimum samples
    species_counts = Counter(item["species_scientific"] for item in manifest)
    valid_species = {sp for sp, cnt in species_counts.items()
                     if cnt >= config.min_samples_per_class}
    manifest = [item for item in manifest if item["species_scientific"] in valid_species]
    print(f"After min_samples filter ({config.min_samples_per_class}): "
          f"{len(manifest)} recordings, {len(valid_species)} species")

    # Build species mapping
    species_list = sorted(valid_species)
    species_to_idx = {sp: i for i, sp in enumerate(species_list)}
    idx_to_species = {i: sp for sp, i in species_to_idx.items()}
    num_species = len(species_to_idx)
    print(f"Number of species: {num_species}")

    # Save mapping
    mapping_path = output_path / "species_mapping.json"
    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump({
            "species_to_idx": species_to_idx,
            "idx_to_species": {str(k): v for k, v in idx_to_species.items()},
        }, f, ensure_ascii=False, indent=2)

    # ── Split data ──
    np.random.shuffle(manifest)
    val_size = int(len(manifest) * config.val_split)
    train_items = manifest[val_size:]
    val_items = manifest[:val_size]

    train_dataset = BirdSoundDatasetV2(train_items, species_to_idx,
                                        augment=True, config=config)
    val_dataset = BirdSoundDatasetV2(val_items, species_to_idx,
                                      augment=False, config=config)

    # ── Class weights for imbalanced data ──
    train_labels = [species_to_idx.get(item["species_scientific"], 0) for item in train_items]
    class_counts = Counter(train_labels)
    class_weights = torch.FloatTensor([
        1.0 / max(class_counts.get(i, 1), 1) for i in range(num_species)
    ])
    class_weights = class_weights / class_weights.sum() * num_species

    # Weighted sampler for balanced batches
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

    print(f"Train: {len(train_dataset)} samples, Val: {len(val_dataset)} samples")
    print(f"Batch size: {config.batch_size}, "
          f"Train batches: {len(train_loader)}, Val batches: {len(val_loader)}")

    # ── Model ──
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = create_model(num_species=num_species, lite=config.lite).to(device)
    print(f"Model: {'Lite' if config.lite else 'Full ResNet'} on {device}")
    print(f"Parameters: {count_parameters(model):,}")

    # ── Loss / Optimizer / Scheduler ──
    criterion = nn.CrossEntropyLoss(
        weight=class_weights.to(device),
        label_smoothing=config.label_smoothing,
    )
    optimizer = optim.AdamW(
        model.parameters(),
        lr=config.lr,
        weight_decay=config.weight_decay,
    )

    # Warmup + Cosine Annealing
    def lr_lambda(epoch):
        if epoch < config.warmup_epochs:
            return (epoch + 1) / config.warmup_epochs
        progress = (epoch - config.warmup_epochs) / max(1, config.num_epochs - config.warmup_epochs)
        return 0.5 * (1 + np.cos(np.pi * progress))

    scheduler = optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)

    # Mixed precision
    scaler = GradScaler("cuda") if config.use_amp and device.type == "cuda" else None

    # ── Training loop ──
    best_val_acc = 0.0
    best_top5_acc = 0.0
    patience_counter = 0
    history = {
        "train_loss": [], "val_loss": [],
        "train_acc": [], "val_acc": [],
        "train_top5": [], "val_top5": [],
        "lr": [],
    }

    start_time = time.time()
    print(f"\n{'='*70}")
    print(f"Starting training: {config.num_epochs} epochs, AMP={'ON' if scaler else 'OFF'}")
    print(f"{'='*70}\n")

    for epoch in range(config.num_epochs):
        epoch_start = time.time()

        # ── Train ──
        model.train()
        train_loss = 0.0
        train_correct = 0
        train_top5_correct = 0
        train_total = 0

        for batch_x, batch_y in train_loader:
            batch_x = batch_x.to(device, non_blocking=True)
            batch_y = batch_y.to(device, non_blocking=True)

            # Mixup
            use_mixup = config.mixup_alpha > 0 and np.random.random() < 0.5
            if use_mixup:
                batch_x, y_a, y_b, lam = mixup_data(batch_x, batch_y, config.mixup_alpha)

            optimizer.zero_grad(set_to_none=True)

            if scaler:
                with autocast("cuda"):
                    outputs = model(batch_x)
                    if use_mixup:
                        loss = mixup_criterion(criterion, outputs, y_a, y_b, lam)
                    else:
                        loss = criterion(outputs, batch_y)
                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                nn.utils.clip_grad_norm_(model.parameters(), config.grad_clip)
                scaler.step(optimizer)
                scaler.update()
            else:
                outputs = model(batch_x)
                if use_mixup:
                    loss = mixup_criterion(criterion, outputs, y_a, y_b, lam)
                else:
                    loss = criterion(outputs, batch_y)
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), config.grad_clip)
                optimizer.step()

            train_loss += loss.item() * batch_x.size(0)
            _, predicted = outputs.max(1)
            train_total += batch_y.size(0)
            train_correct += predicted.eq(batch_y).sum().item()

            # Top-5 accuracy
            if num_species >= 5:
                _, top5_pred = outputs.topk(5, dim=1)
                for i in range(batch_y.size(0)):
                    if batch_y[i] in top5_pred[i]:
                        train_top5_correct += 1

        scheduler.step()

        train_loss /= max(train_total, 1)
        train_acc = train_correct / max(train_total, 1)
        train_top5 = train_top5_correct / max(train_total, 1) if num_species >= 5 else train_acc

        # ── Validate ──
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
                        loss = criterion(outputs, batch_y)
                else:
                    outputs = model(batch_x)
                    loss = criterion(outputs, batch_y)

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

        current_lr = optimizer.param_groups[0]["lr"]
        epoch_time = time.time() - epoch_start

        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["train_acc"].append(train_acc)
        history["val_acc"].append(val_acc)
        history["train_top5"].append(train_top5)
        history["val_top5"].append(val_top5)
        history["lr"].append(current_lr)

        # Print progress
        improved = ""
        if val_acc > best_val_acc + config.min_delta:
            best_val_acc = val_acc
            best_top5_acc = val_top5
            patience_counter = 0
            improved = " ★ BEST"

            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "val_acc": val_acc,
                "val_top5": val_top5,
                "num_species": num_species,
                "lite": config.lite,
            }, output_path / "best_model.pth")
        else:
            patience_counter += 1

        print(f"Epoch [{epoch+1:3d}/{config.num_epochs}] "
              f"Loss: {train_loss:.3f}/{val_loss:.3f} "
              f"Acc: {train_acc:.3f}/{val_acc:.3f} "
              f"Top5: {train_top5:.3f}/{val_top5:.3f} "
              f"LR: {current_lr:.2e} "
              f"({epoch_time:.1f}s){improved}")

        # Early stopping
        if patience_counter >= config.patience:
            print(f"\nEarly stopping at epoch {epoch+1} (patience={config.patience})")
            break

        # Save checkpoint every 10 epochs
        if (epoch + 1) % 10 == 0:
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "num_species": num_species,
                "lite": config.lite,
                "val_acc": val_acc,
            }, output_path / f"checkpoint_epoch{epoch+1}.pth")

    # ── Final save ──
    total_time = time.time() - start_time
    torch.save({
        "epoch": config.num_epochs,
        "model_state_dict": model.state_dict(),
        "num_species": num_species,
        "lite": config.lite,
    }, output_path / "final_model.pth")

    with open(output_path / "training_history.json", "w") as f:
        json.dump(history, f, indent=2)

    # Save config
    with open(output_path / "train_config.json", "w") as f:
        json.dump({
            "num_epochs": config.num_epochs,
            "batch_size": config.batch_size,
            "lr": config.lr,
            "weight_decay": config.weight_decay,
            "warmup_epochs": config.warmup_epochs,
            "mixup_alpha": config.mixup_alpha,
            "label_smoothing": config.label_smoothing,
            "lite": config.lite,
            "use_amp": config.use_amp,
            "num_species": num_species,
            "train_size": len(train_items),
            "val_size": len(val_items),
            "best_val_acc": best_val_acc,
            "best_val_top5": best_top5_acc,
            "total_time_minutes": total_time / 60,
        }, f, indent=2)

    print(f"\n{'='*70}")
    print(f"Training Complete!")
    print(f"{'='*70}")
    print(f"Best Val Accuracy:  {best_val_acc:.4f} (Top-1)")
    print(f"Best Val Top-5:     {best_top5_acc:.4f}")
    print(f"Total Time:         {total_time/60:.1f} minutes")
    print(f"Species:            {num_species}")
    print(f"Model:              {'Lite' if config.lite else 'Full ResNet'}")
    print(f"Output:             {output_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="GPU-Accelerated Bird Sound Training")
    parser.add_argument("--manifest", type=str, required=True)
    parser.add_argument("--output", type=str, default="./checkpoints")
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--batch-size", type=int, default=48)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--lite", action="store_true")
    parser.add_argument("--no-amp", action="store_true")
    parser.add_argument("--patience", type=int, default=15)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    cfg = TrainConfig()
    cfg.manifest_path = args.manifest
    cfg.output_dir = args.output
    cfg.num_epochs = args.epochs
    cfg.batch_size = args.batch_size
    cfg.lr = args.lr
    cfg.lite = args.lite
    cfg.use_amp = not args.no_amp
    cfg.patience = args.patience
    cfg.num_workers = args.workers

    train_model(cfg)
