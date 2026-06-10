"""
Evaluate ensemble inference: Teacher + Student averaging.
Measures accuracy improvement and hallucination reduction vs single model.
"""
import sys, json, numpy as np
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

from cnn_model_v2 import SEResNet50, SEResNet18
from audio_processor import (
    load_audio, audio_to_mel_spectrogram, normalize_spectrogram,
    SEGMENT_DURATION, DEFAULT_SR,
)

class SimpleDataset(torch.utils.data.Dataset):
    def __init__(self, items, species_to_idx):
        self.items, self.s2i = items, species_to_idx
        self.sr, self.dur = DEFAULT_SR, SEGMENT_DURATION
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
        if len(y) > tgt: y = y[(len(y)-tgt)//2:(len(y)-tgt)//2+tgt]
        elif len(y) < tgt: y = np.pad(y, (0, tgt-len(y)))
        mel = audio_to_mel_spectrogram(y, sr=self.sr)
        mel = normalize_spectrogram(mel)
        return torch.FloatTensor(mel).unsqueeze(0), label

def main():
    ckpt = Path(__file__).parent.parent / "backend" / "checkpoints"
    manifest_path = Path(__file__).parent.parent / "data" / "xc_expanded" / "manifest.json"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    counts = Counter(i["species_scientific"] for i in manifest)
    valid = {sp for sp, c in counts.items() if c >= 3}
    manifest = [i for i in manifest if i["species_scientific"] in valid]
    s2i = {sp: i for i, sp in enumerate(sorted(valid))}
    num_sp = len(s2i)

    np.random.seed(42); np.random.shuffle(manifest)
    val_items = manifest[:int(len(manifest)*0.15)]
    print(f"Val: {len(val_items)} samples, {num_sp} species")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Load calibration
    calib = json.load(open(ckpt / "calibration.json"))
    T = calib["temperature"]
    print(f"Calibration T={T:.4f}")

    # Load teacher
    t_ckpt = torch.load(ckpt/"best_teacher.pth", map_location=device, weights_only=False)
    teacher = SEResNet50(num_species=num_sp).to(device)
    teacher.load_state_dict(t_ckpt["model_state_dict"]); teacher.eval()
    print(f"Teacher: val_acc={t_ckpt.get('val_acc',0):.4f}")

    # Load student
    s_ckpt = torch.load(ckpt/"best_model.pth", map_location=device, weights_only=False)
    student = SEResNet18(num_species=num_sp).to(device)
    student.load_state_dict(s_ckpt["model_state_dict"]); student.eval()
    print(f"Student: val_acc={s_ckpt.get('val_acc',0):.4f}")

    loader = DataLoader(SimpleDataset(val_items, s2i), batch_size=64, shuffle=False, num_workers=2)

    # Collect all logits
    t_logits_all, s_logits_all, labels_all = [], [], []
    print("Running inference...")
    with torch.no_grad():
        for bx, by in loader:
            bx = bx.to(device)
            t_logits_all.append(teacher(bx).cpu())
            s_logits_all.append(student(bx).cpu())
            labels_all.append(by)

    t_logits = torch.cat(t_logits_all)
    s_logits = torch.cat(s_logits_all)
    labels = torch.cat(labels_all)
    N = len(labels)

    # Also with TTA (flip)
    t_logits_tta, s_logits_tta = [], []
    with torch.no_grad():
        for bx, by in loader:
            bx = bx.to(device)
            bx_flip = torch.flip(bx, dims=[-1])
            t_logits_tta.append(((teacher(bx) + teacher(bx_flip))/2).cpu())
            s_logits_tta.append(((student(bx) + student(bx_flip))/2).cpu())
    t_logits_tta = torch.cat(t_logits_tta)
    s_logits_tta = torch.cat(s_logits_tta)

    def eval_logits(logits, name):
        probs = F.softmax(logits / T, dim=1)
        conf, pred = probs.max(dim=1)
        acc = (pred == labels).float().mean().item()
        # Top-5
        _, top5 = probs.topk(5, dim=1)
        t5 = sum(1 for i in range(N) if labels[i] in top5[i]) / N
        # Wrong predictions analysis
        wrong = pred != labels
        w_conf = conf[wrong]
        halluc_50 = (w_conf > 0.5).sum().item()
        halluc_70 = (w_conf > 0.7).sum().item()
        halluc_90 = (w_conf > 0.9).sum().item()
        # ECE
        ece = 0
        for lo, hi in zip(np.linspace(0,1,16)[:-1], np.linspace(0,1,16)[1:]):
            mask = (conf.numpy() > lo) & (conf.numpy() <= hi)
            if mask.sum() == 0: continue
            ece += mask.sum()/N * abs((pred[mask]==labels[mask]).float().mean().item() - conf[mask].mean().item())

        print(f"\n  {name}:")
        print(f"    Accuracy:  {acc:.4f}  Top-5: {t5:.4f}")
        print(f"    ECE:       {ece:.4f}")
        print(f"    Mean conf: {conf.mean():.4f}")
        print(f"    Wrong:     {wrong.sum().item()}/{N}")
        print(f"    Halluc(>0.5/0.7/0.9): {halluc_50}/{halluc_70}/{halluc_90}")
        return acc, t5

    print("\n" + "="*60)
    print("RESULTS (with temperature calibration T={:.4f})".format(T))
    print("="*60)

    # Individual models
    eval_logits(t_logits, "Teacher only")
    eval_logits(s_logits, "Student only")
    eval_logits(t_logits_tta, "Teacher + TTA")
    s_acc, s_t5 = eval_logits(s_logits_tta, "Student + TTA")

    # Ensemble: average logits
    ens_logits = (t_logits + s_logits) / 2
    eval_logits(ens_logits, "Ensemble (T+S avg)")

    # Ensemble + TTA
    ens_tta = (t_logits_tta + s_logits_tta) / 2
    e_acc, e_t5 = eval_logits(ens_tta, "Ensemble + TTA (T+S)")

    # Weighted ensemble (student slightly higher since it's better)
    w_ens = 0.45 * t_logits_tta + 0.55 * s_logits_tta
    eval_logits(w_ens, "Weighted Ensemble (0.45T+0.55S) + TTA")

    print(f"\n{'='*60}")
    print(f"SUMMARY: Ensemble+TTA vs Student+TTA")
    print(f"  Accuracy: {s_acc:.4f} → {e_acc:.4f} ({(e_acc-s_acc)*100:+.2f}pp)")
    print(f"  Top-5:    {s_t5:.4f} → {e_t5:.4f} ({(e_t5-s_t5)*100:+.2f}pp)")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
