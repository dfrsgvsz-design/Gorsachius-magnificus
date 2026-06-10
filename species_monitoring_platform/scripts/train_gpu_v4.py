"""
GPU Training Pipeline v4 — 抗幻觉微调
基线: v3 Student = 60.50% val_acc, Ensemble = 61.68%

目标: 缩小 train/val gap (14pp → <8pp), 减少高置信错误预测

策略:
1. 从v3 Student加载预训练权重 (不从零训练)
2. 更强weight decay: 1e-3 → 5e-3
3. 更强label smoothing: 0.05 → 0.15
4. R-Drop正则: KL散度约束两次dropout前向传播一致性
5. 更强CutMix/Mixup: 概率提升
6. 更强SpecAugment: 3次mask, 更宽
7. 低LR微调: 5e-5
8. 80 epochs (微调, 非从零开始)
"""

import os, sys, json, time, warnings, logging
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

from cnn_model_v2 import SEResNet18, cutmix_data, count_parameters
from audio_processor import (
    load_audio, audio_to_mel_spectrogram, normalize_spectrogram,
    SEGMENT_DURATION, DEFAULT_SR, AudioAugmentor,
)


# ──────────────────── Focal Loss ────────────────────
class FocalLoss(nn.Module):
    def __init__(self, weight=None, gamma=2.0, label_smoothing=0.0, reduction='mean'):
        super().__init__()
        self.gamma, self.weight = gamma, weight
        self.label_smoothing, self.reduction = label_smoothing, reduction
    def forward(self, inputs, targets):
        ce = F.cross_entropy(inputs, targets, weight=self.weight,
                             label_smoothing=self.label_smoothing, reduction='none')
        pt = torch.exp(-ce)
        fl = ((1 - pt) ** self.gamma) * ce
        return fl.mean() if self.reduction == 'mean' else fl.sum() if self.reduction == 'sum' else fl


# ──────────────────── EMA ────────────────────
class EMA:
    def __init__(self, model, decay=0.999, warmup_steps=200):
        self.target_decay, self.warmup_steps, self.step_count = decay, warmup_steps, 0
        self.shadow, self.backup = {}, {}
        for n, p in model.named_parameters():
            if p.requires_grad: self.shadow[n] = p.data.clone()
    @property
    def current_decay(self):
        return min(self.target_decay, (1+self.step_count)/(self.warmup_steps+self.step_count))
    def update(self, model):
        self.step_count += 1
        d = self.current_decay
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


# ──────────────────── Dataset with stronger augment ────────────────────
class BirdDatasetV5(Dataset):
    def __init__(self, items, species_to_idx, augment=False):
        self.items, self.s2i, self.augment = items, species_to_idx, augment
        self.sr, self.dur = DEFAULT_SR, SEGMENT_DURATION
        self.audio_aug = AudioAugmentor()
    def __len__(self): return len(self.items)
    def __getitem__(self, idx):
        item = self.items[idx]
        label = self.s2i.get(item["species_scientific"], 0)
        try:
            y, sr = load_audio(item["file_path"], sr=self.sr, duration=self.dur+1)
        except Exception:
            mel = np.zeros((128, int(self.dur*self.sr/512)+1), dtype=np.float32)
            return torch.FloatTensor(mel).unsqueeze(0), label
        tgt = int(self.dur * self.sr)
        if len(y) > tgt:
            start = np.random.randint(0, len(y)-tgt)
            y = y[start:start+tgt]
        elif len(y) < tgt:
            y = np.pad(y, (0, tgt-len(y)))
        if self.augment:
            if np.random.random() < 0.5: y = self.audio_aug.add_noise(y, noise_level=np.random.uniform(0.003, 0.015))
            if np.random.random() < 0.4: y = self.audio_aug.time_shift(y)
            if np.random.random() < 0.4: y = self.audio_aug.random_gain(y)
        mel = audio_to_mel_spectrogram(y, sr=self.sr)
        mel = normalize_spectrogram(mel)
        if self.augment:
            n_mels, n_frames = mel.shape
            if np.random.random() < 0.7:
                mel = mel.copy()
                for _ in range(3):  # 3 freq masks (was 2)
                    f = np.random.randint(1, 28)  # wider (was 24)
                    f0 = np.random.randint(0, max(1, n_mels-f))
                    mel[f0:f0+f, :] = 0
                for _ in range(3):  # 3 time masks (was 2)
                    t = np.random.randint(1, 50)  # wider (was 40)
                    t0 = np.random.randint(0, max(1, n_frames-t))
                    mel[:, t0:t0+t] = 0
        return torch.FloatTensor(mel).unsqueeze(0), label


# ──────────────────── Mixup ────────────────────
def mixup_data(x, y, alpha=0.4):
    lam = np.random.beta(alpha, alpha) if alpha > 0 else 1.0
    idx = torch.randperm(x.size(0), device=x.device)
    return lam * x + (1-lam) * x[idx], y, y[idx], lam

def mixup_criterion(criterion, pred, y_a, y_b, lam):
    return lam * criterion(pred, y_a) + (1-lam) * criterion(pred, y_b)


# ──────────────────── R-Drop ────────────────────
def rdrop_loss(logits1, logits2, alpha=1.0):
    """R-Drop: KL divergence between two forward passes with different dropout.
    Forces model to produce consistent predictions regardless of dropout mask,
    reducing reliance on memorized patterns → less overfitting → fewer hallucinations.
    """
    p1 = F.log_softmax(logits1, dim=1)
    p2 = F.log_softmax(logits2, dim=1)
    kl1 = F.kl_div(p1, p2.exp(), reduction='batchmean')
    kl2 = F.kl_div(p2, p1.exp(), reduction='batchmean')
    return alpha * (kl1 + kl2) / 2


# ──────────────────── Main ────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=str, required=True)
    parser.add_argument("--output", type=str, default="./checkpoints")
    parser.add_argument("--pretrained", type=str, default=None, help="Path to v3 student checkpoint")
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--batch-size", type=int, default=96)
    parser.add_argument("--lr", type=float, default=5e-5)
    parser.add_argument("--weight-decay", type=float, default=5e-3)
    parser.add_argument("--label-smoothing", type=float, default=0.15)
    parser.add_argument("--rdrop-alpha", type=float, default=1.0)
    parser.add_argument("--patience", type=int, default=30)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)

    log_path = output_path / "training_v4.log"
    fh = logging.FileHandler(log_path, mode='w', encoding='utf-8')
    fh.setFormatter(logging.Formatter('%(message)s'))
    logger = logging.getLogger('v4')
    logger.setLevel(logging.INFO)
    logger.handlers = [fh]
    def log(msg):
        logger.info(msg)
        print(msg)

    # Load data
    with open(args.manifest, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    counts = Counter(i["species_scientific"] for i in manifest)
    valid = {sp for sp, c in counts.items() if c >= 3}
    manifest = [i for i in manifest if i["species_scientific"] in valid]
    species_list = sorted(valid)
    s2i = {sp: i for i, sp in enumerate(species_list)}
    num_sp = len(s2i)

    np.random.seed(42); np.random.shuffle(manifest)
    val_size = int(len(manifest) * 0.15)
    train_items, val_items = manifest[val_size:], manifest[:val_size]
    log(f"Data: {len(train_items)} train, {len(val_items)} val, {num_sp} species")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    train_ds = BirdDatasetV5(train_items, s2i, augment=True)
    val_ds = BirdDatasetV5(val_items, s2i, augment=False)

    train_labels = [s2i.get(i["species_scientific"], 0) for i in train_items]
    cc = Counter(train_labels)
    cw = torch.FloatTensor([1.0/max(cc.get(i,1),1) for i in range(num_sp)])
    cw = cw / cw.sum() * num_sp
    sw = [1.0/max(cc.get(l,1),1) for l in train_labels]
    sampler = WeightedRandomSampler(sw, len(sw), replacement=True)

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, sampler=sampler,
                              num_workers=args.workers, pin_memory=True, persistent_workers=args.workers>0)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False,
                            num_workers=args.workers, pin_memory=True, persistent_workers=args.workers>0)

    # Model
    model = SEResNet18(num_species=num_sp, drop_path_rate=0.1).to(device)  # Higher drop_path

    if args.pretrained:
        ckpt = torch.load(args.pretrained, map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model_state_dict"], strict=False)
        log(f"Loaded pretrained: {ckpt.get('version','?')}, val_acc={ckpt.get('val_acc',0):.4f}")
    else:
        log("Training from scratch (no pretrained)")

    log(f"Model: SE-ResNet-18, {count_parameters(model):,} params, drop_path=0.1")

    criterion = FocalLoss(weight=cw.to(device), gamma=2.0, label_smoothing=args.label_smoothing)
    optimizer = optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=1e-7)
    ema = EMA(model, decay=0.999, warmup_steps=200)
    scaler = GradScaler("cuda") if device.type == "cuda" else None

    best_val_acc, best_top5, patience_counter = 0.0, 0.0, 0
    total_pts = 0
    progress_path = output_path / "progress.json"
    start_time = time.time()

    log(f"{'='*70}")
    log(f"V4 Anti-Hallucination Fine-Tune")
    log(f"  Epochs: {args.epochs}, Batch: {args.batch_size}, LR: {args.lr}")
    log(f"  Weight decay: {args.weight_decay}, Label smoothing: {args.label_smoothing}")
    log(f"  R-Drop alpha: {args.rdrop_alpha}, Drop path: 0.1")
    log(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"{'='*70}")

    for epoch in range(args.epochs):
        ep_start = time.time()
        model.train()
        train_loss, train_correct, train_total = 0, 0, 0
        optimizer.zero_grad(set_to_none=True)

        for step, (bx, by) in enumerate(train_loader):
            bx = bx.to(device, non_blocking=True)
            by = by.to(device, non_blocking=True)

            aug = np.random.random()
            use_cutmix = aug < 0.35
            use_mixup = 0.35 <= aug < 0.65

            if use_cutmix:
                bx, y_b, y_a, lam = cutmix_data(bx, by, alpha=1.0)
            elif use_mixup:
                bx, y_a, y_b, lam = mixup_data(bx, by, alpha=0.4)

            if scaler:
                with autocast("cuda"):
                    # R-Drop: two forward passes
                    logits1 = model(bx)
                    logits2 = model(bx)

                    if use_cutmix or use_mixup:
                        task_loss = mixup_criterion(criterion, logits1, y_a, y_b, lam)
                    else:
                        task_loss = criterion(logits1, by)

                    r_loss = rdrop_loss(logits1, logits2, alpha=args.rdrop_alpha)
                    loss = task_loss + r_loss

                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)
                ema.update(model)
            else:
                logits1 = model(bx)
                logits2 = model(bx)
                if use_cutmix or use_mixup:
                    task_loss = mixup_criterion(criterion, logits1, y_a, y_b, lam)
                else:
                    task_loss = criterion(logits1, by)
                r_loss = rdrop_loss(logits1, logits2, alpha=args.rdrop_alpha)
                loss = task_loss + r_loss
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                ema.update(model)

            train_loss += loss.item() * bx.size(0)
            _, pred = logits1.max(1)
            train_total += by.size(0)
            train_correct += pred.eq(by).sum().item()
            total_pts += bx.size(0)

        scheduler.step()
        train_loss /= max(train_total, 1)
        train_acc = train_correct / max(train_total, 1)

        # Validate with EMA
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
                    if by[i] in t5[i]: val_top5_correct += 1
        ema.restore(model)

        val_loss /= max(val_total, 1)
        val_acc = val_correct / max(val_total, 1)
        val_top5 = val_top5_correct / max(val_total, 1)
        lr_now = optimizer.param_groups[0]["lr"]
        ep_time = time.time() - ep_start

        # Train/val gap monitoring (key anti-hallucination metric)
        gap = train_acc - val_acc

        improved = ""
        if val_acc > best_val_acc + 0.001:
            best_val_acc, best_top5 = val_acc, val_top5
            patience_counter = 0
            improved = " ★ BEST"
            ema.apply_shadow(model)
            torch.save({
                "epoch": epoch, "model_state_dict": model.state_dict(),
                "val_acc": val_acc, "val_top5": val_top5,
                "num_species": num_sp, "model_type": "student",
                "version": "v4-student", "lite": False,
            }, output_path / "best_model.pth")
            ema.restore(model)
        else:
            patience_counter += 1

        log(f"Ep [{epoch+1:3d}/{args.epochs}] "
            f"L: {train_loss:.3f}/{val_loss:.3f} "
            f"Acc: {train_acc:.3f}/{val_acc:.3f} "
            f"Gap: {gap:.3f} "
            f"T5: {val_top5:.3f} "
            f"LR: {lr_now:.2e} "
            f"({ep_time:.1f}s){improved}")

        elapsed = time.time() - start_time
        with open(progress_path, 'w') as pf:
            json.dump({
                "phase": "v4-finetune", "status": "running",
                "epoch": epoch+1, "total_epochs": args.epochs,
                "total_data_points": total_pts,
                "train_acc": round(train_acc, 4), "val_acc": round(val_acc, 4),
                "val_top5": round(val_top5, 4),
                "best_val_acc": round(best_val_acc, 4), "best_top5": round(best_top5, 4),
                "train_val_gap": round(gap, 4),
                "patience_counter": patience_counter,
                "elapsed_minutes": round(elapsed/60, 1),
                "timestamp": datetime.now().isoformat(),
            }, pf, indent=2)

        if patience_counter >= args.patience:
            log(f"\nEarly stop at epoch {epoch+1} (patience={args.patience})")
            break

    total_time = time.time() - start_time
    log(f"\n{'='*70}")
    log(f"V4 Fine-Tune Complete")
    log(f"  Best Val Acc: {best_val_acc:.4f}")
    log(f"  Best Top-5:   {best_top5:.4f}")
    log(f"  Data points:  {total_pts:,}")
    log(f"  Time:         {total_time/60:.1f} min")
    log(f"{'='*70}")

    with open(progress_path, 'w') as pf:
        json.dump({
            "phase": "v4-complete", "status": "completed",
            "total_data_points": total_pts,
            "best_val_acc": round(best_val_acc, 4),
            "best_top5": round(best_top5, 4),
            "elapsed_minutes": round(total_time/60, 1),
            "timestamp": datetime.now().isoformat(),
        }, pf, indent=2)

if __name__ == "__main__":
    main()
