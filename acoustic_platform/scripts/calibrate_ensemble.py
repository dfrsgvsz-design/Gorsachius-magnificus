"""Re-calibrate temperature for ensemble (Teacher+Student) inference."""
import sys, json, numpy as np
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader
from cnn_model_v2 import SEResNet50, SEResNet18
from audio_processor import load_audio, audio_to_mel_spectrogram, normalize_spectrogram, SEGMENT_DURATION, DEFAULT_SR

class SimpleDS(torch.utils.data.Dataset):
    def __init__(self, items, s2i):
        self.items, self.s2i = items, s2i
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

def find_optimal_T(logits, labels):
    """Grid search for optimal T > 0 that minimizes NLL."""
    lt = torch.FloatTensor(logits)
    lb = torch.LongTensor(labels)
    best_T, best_nll = 1.0, float('inf')
    # Coarse search
    for t in np.arange(0.3, 3.0, 0.05):
        nll = F.cross_entropy(lt / t, lb).item()
        if nll < best_nll:
            best_nll, best_T = nll, t
    # Fine search around best
    for t in np.arange(max(0.1, best_T - 0.1), best_T + 0.1, 0.005):
        nll = F.cross_entropy(lt / t, lb).item()
        if nll < best_nll:
            best_nll, best_T = nll, t
    return float(best_T)

def compute_ece(conf, pred, labels, n_bins=15):
    ece = 0
    for lo, hi in zip(np.linspace(0,1,n_bins+1)[:-1], np.linspace(0,1,n_bins+1)[1:]):
        mask = (conf > lo) & (conf <= hi)
        if mask.sum() == 0: continue
        ece += mask.sum()/len(labels) * abs((pred[mask]==labels[mask]).mean() - conf[mask].mean())
    return float(ece)

def main():
    ckpt = Path(__file__).parent.parent / "backend" / "checkpoints"
    mf = Path(__file__).parent.parent / "data" / "xc_expanded" / "manifest.json"
    with open(mf, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    counts = Counter(i["species_scientific"] for i in manifest)
    valid = {sp for sp, c in counts.items() if c >= 3}
    manifest = [i for i in manifest if i["species_scientific"] in valid]
    s2i = {sp: i for i, sp in enumerate(sorted(valid))}
    num_sp = len(s2i)
    np.random.seed(42); np.random.shuffle(manifest)
    val_items = manifest[:int(len(manifest)*0.15)]
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    teacher = SEResNet50(num_species=num_sp).to(device)
    teacher.load_state_dict(torch.load(ckpt/"best_teacher.pth", map_location=device, weights_only=False)["model_state_dict"])
    teacher.eval()

    student = SEResNet18(num_species=num_sp).to(device)
    student.load_state_dict(torch.load(ckpt/"best_model.pth", map_location=device, weights_only=False)["model_state_dict"])
    student.eval()

    loader = DataLoader(SimpleDS(val_items, s2i), batch_size=64, shuffle=False, num_workers=2)

    all_logits, all_labels = [], []
    print("Collecting ensemble logits...")
    with torch.no_grad():
        for bx, by in loader:
            bx = bx.to(device)
            ens = (teacher(bx) + student(bx)) / 2.0
            all_logits.append(ens.cpu().numpy())
            all_labels.append(by.numpy())

    logits = np.concatenate(all_logits)
    labels = np.concatenate(all_labels)

    # Before calibration
    probs = np.exp(logits) / np.exp(logits).sum(axis=1, keepdims=True)
    conf = probs.max(axis=1)
    pred = probs.argmax(axis=1)
    acc = (pred == labels).mean()
    ece_before = compute_ece(conf, pred, labels)
    print(f"\nEnsemble (no calibration):")
    print(f"  Accuracy: {acc:.4f}, ECE: {ece_before:.4f}, Mean conf: {conf.mean():.4f}")

    # Find optimal T
    T = find_optimal_T(logits, labels)
    print(f"\nOptimal T for ensemble: {T:.4f}")

    # After calibration
    scaled = logits / T
    sprobs = np.exp(scaled) / np.exp(scaled).sum(axis=1, keepdims=True)
    sconf = sprobs.max(axis=1)
    spred = sprobs.argmax(axis=1)
    ece_after = compute_ece(sconf, spred, labels)
    print(f"\nEnsemble + T={T:.4f}:")
    print(f"  Accuracy: {(spred==labels).mean():.4f}, ECE: {ece_after:.4f}, Mean conf: {sconf.mean():.4f}")

    # Hallucination analysis
    wrong = spred != labels
    wconf = sconf[wrong]
    print(f"\n  Wrong: {wrong.sum()}/{len(labels)}")
    print(f"  Halluc(>0.5/0.7/0.9): {(wconf>0.5).sum()}/{(wconf>0.7).sum()}/{(wconf>0.9).sum()}")

    # Save
    calib = {
        "temperature": round(T, 4),
        "ece_before": round(ece_before, 4),
        "ece_after": round(ece_after, 4),
        "mean_conf_before": round(float(conf.mean()), 4),
        "mean_conf_after": round(float(sconf.mean()), 4),
        "accuracy": round(float(acc), 4),
        "model_version": "v3-ensemble",
        "ensemble": True,
    }
    with open(ckpt / "calibration.json", "w") as f:
        json.dump(calib, f, indent=2)
    print(f"\nSaved ensemble calibration: {ckpt / 'calibration.json'}")

if __name__ == "__main__":
    main()
