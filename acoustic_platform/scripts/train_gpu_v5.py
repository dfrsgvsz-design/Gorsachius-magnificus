"""
GPU Training Pipeline v5 — EfficientNet + Dual-Channel + Prototype Learning

Architecture innovations (from BirdNET + Perch 2.0 research):
1. EfficientNet-B1 backbone (7.9M params, ImageNet pretrained)
2. Dual-channel mel spectrogram: low-freq 0-3kHz + high-freq 500Hz-15kHz
3. Prototype learning head with OOD detection
4. Self-distillation: prototype teacher → linear student
5. Non-event class for background noise rejection

Anti-hallucination (7-layer defense):
- R-Drop, Label Smoothing 0.12, Weight Decay 3e-3
- Stochastic Depth, EMA, CutMix/Mixup
- Prototype orthogonal loss for diversity
- Gap monitoring with auto-alert

Training plan: up to 12 hours, check every 60 minutes
Device: RTX 3080 10GB, batch_size=48
"""

import os, sys, json, time, warnings, logging, math
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

from cnn_model_v5 import (
    EfficientNetBird, EfficientNetBirdLarge,
    compute_dual_channel_mel, DUAL_CHANNEL_CONFIG,
    count_parameters, self_distillation_loss,
)


# ──────────────────── Focal Loss ────────────────────
class FocalLoss(nn.Module):
    def __init__(self, weight=None, gamma=2.0, label_smoothing=0.0):
        super().__init__()
        self.gamma, self.weight, self.ls = gamma, weight, label_smoothing
    def forward(self, inputs, targets):
        ce = F.cross_entropy(inputs, targets, weight=self.weight,
                             label_smoothing=self.ls, reduction='none')
        pt = torch.exp(-ce)
        return (((1 - pt) ** self.gamma) * ce).mean()


# ──────────────────── EMA ────────────────────
class EMA:
    def __init__(self, model, decay=0.999, warmup=300):
        self.decay, self.warmup, self.step = decay, warmup, 0
        self.shadow = {n: p.data.clone() for n, p in model.named_parameters() if p.requires_grad}
        self.backup = {}
    def update(self, model):
        self.step += 1
        d = min(self.decay, (1+self.step)/(self.warmup+self.step))
        for n, p in model.named_parameters():
            if p.requires_grad: self.shadow[n].lerp_(p.data, 1.0-d)
    def apply_shadow(self, model):
        for n, p in model.named_parameters():
            if p.requires_grad:
                self.backup[n] = p.data.clone()
                p.data.copy_(self.shadow[n])
    def restore(self, model):
        for n, p in model.named_parameters():
            if p.requires_grad: p.data.copy_(self.backup[n])
        self.backup = {}


# ──────────────────── Dataset: Dual-Channel ────────────────────
class BirdDatasetV5(Dataset):
    """Dual-channel mel spectrogram dataset for EfficientNet v5."""

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
            mel = np.zeros((2, 96, 512), dtype=np.float32)
            return torch.FloatTensor(mel), label

        tgt = int(self.dur * self.sr)
        if len(y) > tgt:
            start = np.random.randint(0, len(y) - tgt) if self.augment else (len(y) - tgt) // 2
            y = y[start:start + tgt]
        elif len(y) < tgt:
            y = np.pad(y, (0, tgt - len(y)))

        # Audio augmentation (enhanced for small-dataset regime)
        if self.augment:
            # Gaussian noise injection
            if np.random.random() < 0.5:
                y += np.random.randn(len(y)) * np.random.uniform(0.002, 0.015)
            # Time shift
            if np.random.random() < 0.3:
                y = np.roll(y, int(len(y) * np.random.uniform(-0.15, 0.15)))
            # Gain augmentation
            if np.random.random() < 0.4:
                y *= np.random.uniform(0.6, 1.4)
            # Time stretch (±15%, key for bird call variation)
            if np.random.random() < 0.3:
                rate = np.random.uniform(0.85, 1.15)
                y = librosa.effects.time_stretch(y, rate=rate)
                if len(y) > tgt:
                    y = y[:tgt]
                elif len(y) < tgt:
                    y = np.pad(y, (0, tgt - len(y)))
            # Pitch shift (±2 semitones, simulates different individuals)
            if np.random.random() < 0.25:
                n_steps = np.random.uniform(-2.0, 2.0)
                y = librosa.effects.pitch_shift(y, sr=self.sr, n_steps=n_steps)

        # Compute dual-channel mel
        mel = compute_dual_channel_mel(y, sr=self.sr)  # (2, 96, T)

        # SpecAugment on each channel (stronger: 5 masks, wider)
        if self.augment and np.random.random() < 0.8:
            mel = mel.copy()
            for ch in range(2):
                n_mels, n_frames = mel.shape[1], mel.shape[2]
                n_freq_masks = np.random.randint(3, 6)  # 3-5 freq masks
                n_time_masks = np.random.randint(3, 6)  # 3-5 time masks
                for _ in range(n_freq_masks):
                    f = np.random.randint(1, 25)
                    f0 = np.random.randint(0, max(1, n_mels - f))
                    mel[ch, f0:f0+f, :] = 0
                for _ in range(n_time_masks):
                    t = np.random.randint(1, 50)
                    t0 = np.random.randint(0, max(1, n_frames - t))
                    mel[ch, :, t0:t0+t] = 0

        return torch.FloatTensor(mel), label


# ──────────────────── CutMix / Mixup ────────────────────
def cutmix_data(x, y, alpha=1.0):
    lam = np.random.beta(alpha, alpha)
    B = x.size(0)
    idx = torch.randperm(B, device=x.device)
    W = x.size(-1)
    cut = int(W * (1 - lam))
    cx = np.random.randint(0, W)
    x1, x2 = max(0, cx - cut//2), min(W, cx + cut//2)
    x_mixed = x.clone()
    x_mixed[:, :, :, x1:x2] = x[idx, :, :, x1:x2]
    lam = 1 - (x2 - x1) / W
    return x_mixed, y[idx], y, lam

def mixup_data(x, y, alpha=0.4):
    lam = np.random.beta(alpha, alpha)
    idx = torch.randperm(x.size(0), device=x.device)
    return lam * x + (1-lam) * x[idx], y, y[idx], lam

def mix_criterion(criterion, pred, y_a, y_b, lam):
    return lam * criterion(pred, y_a) + (1-lam) * criterion(pred, y_b)


# ──────────────────── R-Drop ────────────────────
def rdrop_loss(logits1, logits2, alpha=0.5):
    p1 = F.log_softmax(logits1, dim=1)
    p2 = F.log_softmax(logits2, dim=1)
    return alpha * (F.kl_div(p1, p2.exp(), reduction='batchmean') +
                    F.kl_div(p2, p1.exp(), reduction='batchmean')) / 2


# ──────────────────── Main Training ────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", default="./checkpoints")
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=48)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=5e-3)
    parser.add_argument("--label-smoothing", type=float, default=0.12)
    parser.add_argument("--rdrop-alpha", type=float, default=0.5)
    parser.add_argument("--distill-weight", type=float, default=1.0)
    parser.add_argument("--distill-start", type=int, default=30,
                        help="Start self-distillation after N epochs")
    parser.add_argument("--dropout", type=float, default=0.4)
    parser.add_argument("--accum-steps", type=int, default=4,
                        help="Gradient accumulation steps (eff_batch = batch_size * accum_steps)")
    parser.add_argument("--warmup-epochs", type=int, default=5,
                        help="Linear warmup epochs before cosine schedule")
    parser.add_argument("--rdrop-prob", type=float, default=0.5,
                        help="Probability of applying R-Drop per batch (saves compute)")
    parser.add_argument("--resume", type=str, default=None,
                        help="Path to v5 checkpoint to resume training")
    parser.add_argument("--patience", type=int, default=40)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--max-hours", type=float, default=12.0)
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    fh = logging.FileHandler(output / "training_v5.log", mode='w', encoding='utf-8')
    fh.setFormatter(logging.Formatter('%(message)s'))
    logger = logging.getLogger('v5')
    logger.setLevel(logging.INFO)
    logger.handlers = [fh]
    def log(msg):
        logger.info(msg)
        print(msg)

    # ── Data ──
    with open(args.manifest, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    counts = Counter(i["species_scientific"] for i in manifest)
    valid = {sp for sp, c in counts.items() if c >= 3}
    manifest = [i for i in manifest if i["species_scientific"] in valid]
    species_list = sorted(valid)
    s2i = {sp: i for i, sp in enumerate(species_list)}
    num_sp = len(s2i)

    np.random.seed(42)
    np.random.shuffle(manifest)
    val_size = int(len(manifest) * 0.15)
    train_items, val_items = manifest[val_size:], manifest[:val_size]
    log(f"Data: {len(train_items)} train, {len(val_items)} val, {num_sp} species")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log(f"Device: {device}")
    if device.type == "cuda":
        log(f"GPU: {torch.cuda.get_device_name()}, {torch.cuda.get_device_properties(0).total_memory/1e9:.1f}GB")

    train_ds = BirdDatasetV5(train_items, s2i, augment=True)
    val_ds = BirdDatasetV5(val_items, s2i, augment=False)

    # Class-balanced sampling
    train_labels = [s2i.get(i["species_scientific"], 0) for i in train_items]
    cc = Counter(train_labels)
    cw = torch.FloatTensor([1.0/max(cc.get(i,1),1) for i in range(num_sp)])
    cw = cw / cw.sum() * num_sp
    sw = [1.0/max(cc.get(l,1),1) for l in train_labels]
    sampler = WeightedRandomSampler(sw, len(sw), replacement=True)

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, sampler=sampler,
                              num_workers=args.workers, pin_memory=True,
                              persistent_workers=args.workers > 0)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False,
                            num_workers=args.workers, pin_memory=True,
                            persistent_workers=args.workers > 0)

    # ── Model ──
    model = EfficientNetBird(
        num_classes=num_sp, dropout=args.dropout, pretrained=True, num_prototypes=4
    ).to(device)
    log(f"Model: EfficientNet-B1 Bird, {count_parameters(model):,} params, embed={model.embed_dim}")

    # Resume from v5 checkpoint if specified
    start_epoch = 0
    if args.resume and os.path.isfile(args.resume):
        ckpt = torch.load(args.resume, map_location=device, weights_only=False)
        if "model_state_dict" in ckpt:
            model.load_state_dict(ckpt["model_state_dict"], strict=False)
            start_epoch = ckpt.get("epoch", 0) + 1
            log(f"Resumed from {args.resume}, epoch {start_epoch}, "
                f"prev_val_acc={ckpt.get('val_acc', 0):.4f}")
        else:
            log(f"Warning: checkpoint has no model_state_dict, training from scratch")

    # ── Optimizer ──
    criterion = FocalLoss(weight=cw.to(device), gamma=2.0, label_smoothing=args.label_smoothing)
    optimizer = optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)

    # Cosine Annealing with Warm Restarts
    scheduler = optim.lr_scheduler.CosineAnnealingWarmRestarts(
        optimizer, T_0=30, T_mult=2, eta_min=1e-6
    )
    ema = EMA(model, decay=0.999, warmup=300)
    scaler = GradScaler("cuda") if device.type == "cuda" else None

    best_val_acc, best_top5, patience_counter = 0.0, 0.0, 0
    total_pts = 0
    progress_path = output / "progress.json"
    start_time = time.time()
    max_seconds = args.max_hours * 3600
    accum_steps = args.accum_steps
    eff_batch = args.batch_size * accum_steps

    log(f"\n{'='*70}")
    log(f"V5 EfficientNet Training — Optimized Architecture")
    log(f"  Epochs: {args.epochs}, Batch: {args.batch_size}x{accum_steps}={eff_batch}, LR: {args.lr}")
    log(f"  Weight Decay: {args.weight_decay}, Label Smoothing: {args.label_smoothing}, Dropout: {args.dropout}")
    log(f"  R-Drop: {args.rdrop_alpha} (p={args.rdrop_prob}), Self-Distill: {args.distill_weight} (start@ep{args.distill_start})")
    log(f"  Warmup: {args.warmup_epochs} epochs, Patience: {args.patience}")
    log(f"  Max Hours: {args.max_hours}, Resume: {args.resume or 'None'}")
    log(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"{'='*70}\n")

    for epoch in range(start_epoch, args.epochs):
        # Time limit check
        if time.time() - start_time > max_seconds:
            log(f"\nTime limit ({args.max_hours}h) reached at epoch {epoch+1}")
            break

        # ── Learning rate: linear warmup then cosine ──
        if epoch < args.warmup_epochs:
            warmup_factor = (epoch + 1) / args.warmup_epochs
            for pg in optimizer.param_groups:
                pg['lr'] = args.lr * warmup_factor

        ep_start = time.time()
        model.train()
        train_loss, train_correct, train_total = 0, 0, 0
        proto_loss_sum, distill_loss_sum = 0, 0

        use_distill = epoch >= args.distill_start
        optimizer.zero_grad(set_to_none=True)

        for step, (bx, by) in enumerate(train_loader):
            bx = bx.to(device, non_blocking=True)
            by = by.to(device, non_blocking=True)

            # Augmentation selection
            aug = np.random.random()
            use_cutmix = aug < 0.30
            use_mixup = 0.30 <= aug < 0.55

            if use_cutmix:
                bx, y_b, y_a, lam = cutmix_data(bx, by)
            elif use_mixup:
                bx, y_a, y_b, lam = mixup_data(bx, by)

            # R-Drop: only apply with probability rdrop_prob to save compute
            apply_rdrop = np.random.random() < args.rdrop_prob

            if scaler:
                with autocast("cuda"):
                    # Forward pass 1 (with prototype)
                    logits1, (proto_logits1, _) = model(bx, return_proto=True)

                    # Task loss
                    if use_cutmix or use_mixup:
                        task_loss = mix_criterion(criterion, logits1, y_a, y_b, lam)
                    else:
                        task_loss = criterion(logits1, by)

                    # R-Drop loss (conditional — saves ~30% compute)
                    if apply_rdrop:
                        logits2 = model(bx)
                        r_loss = rdrop_loss(logits1, logits2, alpha=args.rdrop_alpha)
                    else:
                        r_loss = torch.tensor(0.0, device=device)

                    # Prototype losses
                    if use_cutmix or use_mixup:
                        p_task = mix_criterion(criterion, proto_logits1, y_a, y_b, lam)
                    else:
                        p_task = criterion(proto_logits1, by)
                    p_ortho = model.head_proto.orthogonal_loss()

                    # Self-distillation (after warmup)
                    d_loss = torch.tensor(0.0, device=device)
                    if use_distill:
                        d_loss = self_distillation_loss(logits1, proto_logits1)

                    loss = (task_loss + r_loss + 0.5 * p_task + 0.1 * p_ortho +
                            args.distill_weight * d_loss)
                    loss = loss / accum_steps  # Scale for gradient accumulation

                scaler.scale(loss).backward()

                # Step optimizer every accum_steps
                if (step + 1) % accum_steps == 0 or (step + 1) == len(train_loader):
                    scaler.unscale_(optimizer)
                    nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    scaler.step(optimizer)
                    scaler.update()
                    optimizer.zero_grad(set_to_none=True)
            else:
                logits1, (proto_logits1, _) = model(bx, return_proto=True)
                if use_cutmix or use_mixup:
                    task_loss = mix_criterion(criterion, logits1, y_a, y_b, lam)
                else:
                    task_loss = criterion(logits1, by)
                if apply_rdrop:
                    logits2 = model(bx)
                    r_loss = rdrop_loss(logits1, logits2, alpha=args.rdrop_alpha)
                else:
                    r_loss = torch.tensor(0.0, device=device)
                if use_cutmix or use_mixup:
                    p_task = mix_criterion(criterion, proto_logits1, y_a, y_b, lam)
                else:
                    p_task = criterion(proto_logits1, by)
                p_ortho = model.head_proto.orthogonal_loss()
                d_loss = torch.tensor(0.0, device=device)
                if use_distill:
                    d_loss = self_distillation_loss(logits1, proto_logits1)
                loss = (task_loss + r_loss + 0.5 * p_task + 0.1 * p_ortho +
                        args.distill_weight * d_loss)
                loss = loss / accum_steps
                loss.backward()
                if (step + 1) % accum_steps == 0 or (step + 1) == len(train_loader):
                    nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    optimizer.step()
                    optimizer.zero_grad(set_to_none=True)

            ema.update(model)
            train_loss += loss.item() * accum_steps * bx.size(0)  # Undo scaling for logging
            _, pred = logits1.max(1)
            train_total += by.size(0)
            train_correct += pred.eq(by).sum().item()
            total_pts += bx.size(0)
            proto_loss_sum += p_task.item()
            distill_loss_sum += d_loss.item()

        # ── LR schedule: only cosine after warmup ──
        if epoch >= args.warmup_epochs:
            scheduler.step()
        train_loss /= max(train_total, 1)
        train_acc = train_correct / max(train_total, 1)

        # ── Validate with EMA ──
        ema.apply_shadow(model)
        model.eval()
        val_loss, val_correct, val_top5_correct, val_total = 0, 0, 0, 0
        with torch.no_grad():
            for bx, by in val_loader:
                bx, by = bx.to(device, non_blocking=True), by.to(device, non_blocking=True)
                if scaler:
                    with autocast("cuda"):
                        out = model(bx)
                        vl = F.cross_entropy(out, by)
                else:
                    out = model(bx)
                    vl = F.cross_entropy(out, by)
                val_loss += vl.item() * bx.size(0)
                _, pred = out.max(1)
                val_total += by.size(0)
                val_correct += pred.eq(by).sum().item()
                _, t5 = out.topk(5, dim=1)
                for i in range(by.size(0)):
                    if by[i] in t5[i]:
                        val_top5_correct += 1
        ema.restore(model)

        val_loss /= max(val_total, 1)
        val_acc = val_correct / max(val_total, 1)
        val_top5 = val_top5_correct / max(val_total, 1)
        lr_now = optimizer.param_groups[0]["lr"]
        ep_time = time.time() - ep_start
        gap = train_acc - val_acc

        improved = ""
        if val_acc > best_val_acc + 0.001:
            best_val_acc, best_top5 = val_acc, val_top5
            patience_counter = 0
            improved = " ★ BEST"
            ema.apply_shadow(model)
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "val_acc": val_acc, "val_top5": val_top5,
                "num_species": num_sp,
                "model_type": "student",
                "version": "v5-efficientnet",
                "backbone": "efficientnet_b1",
                "dual_channel": True,
                "embed_dim": model.embed_dim,
            }, output / "best_model.pth")
            ema.restore(model)
        else:
            patience_counter += 1

        # Gap warning
        gap_warn = ""
        if gap > 0.15:
            gap_warn = " ⚠️GAP"
        elif gap > 0.08:
            gap_warn = " ⚡GAP"

        log(f"Ep [{epoch+1:3d}/{args.epochs}] "
            f"L: {train_loss:.3f}/{val_loss:.3f} "
            f"Acc: {train_acc:.3f}/{val_acc:.3f} "
            f"Gap: {gap:+.3f}{gap_warn} "
            f"T5: {val_top5:.3f} "
            f"LR: {lr_now:.2e} "
            f"({ep_time:.1f}s){improved}")

        # Save progress JSON
        elapsed = time.time() - start_time
        with open(progress_path, 'w') as pf:
            json.dump({
                "phase": "v5-efficientnet", "status": "running",
                "epoch": epoch+1, "total_epochs": args.epochs,
                "total_data_points": total_pts,
                "train_acc": round(train_acc, 4), "val_acc": round(val_acc, 4),
                "val_top5": round(val_top5, 4),
                "best_val_acc": round(best_val_acc, 4), "best_top5": round(best_top5, 4),
                "train_val_gap": round(gap, 4),
                "patience_counter": patience_counter,
                "self_distill_active": use_distill,
                "elapsed_minutes": round(elapsed/60, 1),
                "timestamp": datetime.now().isoformat(),
            }, pf, indent=2)

        if patience_counter >= args.patience:
            log(f"\nEarly stop at epoch {epoch+1} (patience={args.patience})")
            break

    total_time = time.time() - start_time
    log(f"\n{'='*70}")
    log(f"V5 Training Complete")
    log(f"  Best Val Acc:  {best_val_acc:.4f}")
    log(f"  Best Top-5:    {best_top5:.4f}")
    log(f"  Data points:   {total_pts:,}")
    log(f"  Time:          {total_time/60:.1f} min ({total_time/3600:.1f} h)")
    log(f"{'='*70}")

    with open(progress_path, 'w') as pf:
        json.dump({
            "phase": "v5-complete", "status": "completed",
            "total_data_points": total_pts,
            "best_val_acc": round(best_val_acc, 4),
            "best_top5": round(best_top5, 4),
            "elapsed_minutes": round(total_time/60, 1),
            "timestamp": datetime.now().isoformat(),
        }, pf, indent=2)


if __name__ == "__main__":
    main()
