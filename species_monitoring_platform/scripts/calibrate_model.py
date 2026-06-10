"""
Model Calibration Diagnostic & Temperature Scaling

Diagnoses overconfidence (hallucination) and finds optimal temperature T
for post-hoc calibration of softmax outputs.

Metrics:
- ECE (Expected Calibration Error): measures confidence vs accuracy alignment
- MCE (Maximum Calibration Error): worst-case bin error
- Reliability diagram: visual calibration check
- Temperature scaling: find T that minimizes NLL on validation set

Usage:
    python scripts/calibrate_model.py
"""

import os
import sys
import json
import numpy as np
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

from audio_processor import (
    load_audio, audio_to_mel_spectrogram, normalize_spectrogram,
    SEGMENT_DURATION, DEFAULT_SR, AudioAugmentor,
)


# ──────────────────── Dataset (minimal) ────────────────────

class CalibrationDataset(torch.utils.data.Dataset):
    def __init__(self, items, species_to_idx):
        self.items = items
        self.species_to_idx = species_to_idx
        self.sr = DEFAULT_SR
        self.seg_dur = SEGMENT_DURATION

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        item = self.items[idx]
        label = self.species_to_idx.get(item["species_scientific"], 0)
        try:
            y, sr = load_audio(item["file_path"], sr=self.sr, duration=self.seg_dur + 1)
        except Exception:
            mel = np.zeros((128, int(self.seg_dur * self.sr / 512) + 1), dtype=np.float32)
            return torch.FloatTensor(mel).unsqueeze(0), label

        target_len = int(self.seg_dur * self.sr)
        if len(y) > target_len:
            start = (len(y) - target_len) // 2  # center crop for deterministic eval
            y = y[start:start + target_len]
        elif len(y) < target_len:
            y = np.pad(y, (0, target_len - len(y)))

        mel = audio_to_mel_spectrogram(y, sr=self.sr)
        mel = normalize_spectrogram(mel)
        return torch.FloatTensor(mel).unsqueeze(0), label


# ──────────────────── Calibration Metrics ────────────────────

def compute_ece(confidences, predictions, labels, n_bins=15):
    """Expected Calibration Error — measures confidence vs accuracy alignment.
    
    ECE = Σ (|B_m|/n) * |acc(B_m) - conf(B_m)|
    
    Perfect calibration: ECE = 0 (when confidence matches accuracy per bin).
    Overconfident model: ECE >> 0 (confidence > accuracy).
    """
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    bin_data = []

    for i in range(n_bins):
        lo, hi = bin_boundaries[i], bin_boundaries[i + 1]
        mask = (confidences > lo) & (confidences <= hi)
        if mask.sum() == 0:
            bin_data.append({"lo": lo, "hi": hi, "count": 0, "acc": 0, "conf": 0})
            continue

        bin_acc = (predictions[mask] == labels[mask]).mean()
        bin_conf = confidences[mask].mean()
        bin_count = mask.sum()

        ece += (bin_count / len(labels)) * abs(bin_acc - bin_conf)
        bin_data.append({
            "lo": round(lo, 3), "hi": round(hi, 3),
            "count": int(bin_count),
            "acc": round(float(bin_acc), 4),
            "conf": round(float(bin_conf), 4),
            "gap": round(float(bin_conf - bin_acc), 4),
        })

    return float(ece), bin_data


def find_optimal_temperature(logits, labels, lr=0.01, max_iter=500):
    """Find optimal temperature T that minimizes NLL on validation logits.
    
    Higher T → softer probabilities → less overconfident.
    T=1.0 is the default (no scaling).
    """
    temperature = torch.nn.Parameter(torch.ones(1) * 1.5)
    optimizer = torch.optim.LBFGS([temperature], lr=lr, max_iter=max_iter)
    logits_t = torch.FloatTensor(logits)
    labels_t = torch.LongTensor(labels)

    def eval_fn():
        optimizer.zero_grad()
        loss = F.cross_entropy(logits_t / temperature, labels_t)
        loss.backward()
        return loss

    optimizer.step(eval_fn)
    return float(temperature.item())


# ──────────────────── Main ────────────────────

def main():
    ckpt_dir = Path(__file__).parent.parent / "backend" / "checkpoints"
    manifest_path = Path(__file__).parent.parent / "data" / "xc_expanded" / "manifest.json"

    # Load manifest
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    species_counts = Counter(item["species_scientific"] for item in manifest)
    valid_species = {sp for sp, cnt in species_counts.items() if cnt >= 3}
    manifest = [item for item in manifest if item["species_scientific"] in valid_species]
    species_list = sorted(valid_species)
    species_to_idx = {sp: i for i, sp in enumerate(species_list)}
    num_species = len(species_to_idx)

    # Same split as training
    np.random.seed(42)
    np.random.shuffle(manifest)
    val_size = int(len(manifest) * 0.15)
    val_items = manifest[:val_size]

    print(f"Validation set: {len(val_items)} samples, {num_species} species")

    # Load model — detect version
    model_path = ckpt_dir / "best_model.pth"
    checkpoint = torch.load(model_path, map_location="cpu", weights_only=False)
    version = checkpoint.get("version", "v1")
    model_type = checkpoint.get("model_type", "unknown")
    print(f"Model: {version}, type={model_type}, val_acc={checkpoint.get('val_acc', '?')}")

    if "v3" in version or model_type in ("student", "teacher"):
        from cnn_model_v2 import SEResNet18, SEResNet50
        if model_type == "teacher":
            model = SEResNet50(num_species=num_species)
        else:
            model = SEResNet18(num_species=num_species)
    else:
        from cnn_model import create_model
        lite = checkpoint.get("lite", False)
        model = create_model(num_species=num_species, lite=lite)

    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)

    # Collect logits on validation set
    val_dataset = CalibrationDataset(val_items, species_to_idx)
    val_loader = DataLoader(val_dataset, batch_size=64, shuffle=False, num_workers=2)

    all_logits = []
    all_labels = []
    all_confidences = []
    all_predictions = []

    print("Collecting validation logits...")
    with torch.no_grad():
        for batch_x, batch_y in val_loader:
            batch_x = batch_x.to(device)
            logits = model(batch_x)
            probs = F.softmax(logits, dim=1)
            conf, pred = probs.max(dim=1)

            all_logits.append(logits.cpu().numpy())
            all_labels.append(batch_y.numpy())
            all_confidences.append(conf.cpu().numpy())
            all_predictions.append(pred.cpu().numpy())

    all_logits = np.concatenate(all_logits)
    all_labels = np.concatenate(all_labels)
    all_confidences = np.concatenate(all_confidences)
    all_predictions = np.concatenate(all_predictions)

    # Basic accuracy
    accuracy = (all_predictions == all_labels).mean()
    mean_confidence = all_confidences.mean()
    print(f"\nAccuracy: {accuracy:.4f}")
    print(f"Mean confidence: {mean_confidence:.4f}")
    print(f"Confidence - Accuracy gap: {mean_confidence - accuracy:.4f}")

    if mean_confidence > accuracy + 0.05:
        print(f"⚠️  MODEL IS OVERCONFIDENT by {mean_confidence - accuracy:.2%}")
    elif mean_confidence < accuracy - 0.05:
        print(f"⚠️  Model is underconfident by {accuracy - mean_confidence:.2%}")
    else:
        print(f"✅ Model confidence is reasonably calibrated")

    # ECE before calibration
    ece_before, bins_before = compute_ece(all_confidences, all_predictions, all_labels)
    print(f"\nECE (before calibration): {ece_before:.4f}")

    print("\nReliability diagram (before):")
    print(f"  {'Bin':>10} {'Count':>6} {'Acc':>6} {'Conf':>6} {'Gap':>6}")
    for b in bins_before:
        if b["count"] > 0:
            gap_str = f"+{b['gap']:.3f}" if b["gap"] > 0 else f"{b['gap']:.3f}"
            print(f"  {b['lo']:.2f}-{b['hi']:.2f} {b['count']:>6} {b['acc']:.4f} {b['conf']:.4f} {gap_str}")

    # Find optimal temperature
    print("\nFinding optimal temperature...")
    T_opt = find_optimal_temperature(all_logits, all_labels)
    print(f"Optimal temperature: T = {T_opt:.4f}")

    # Re-calibrate with optimal T
    scaled_logits = all_logits / T_opt
    scaled_probs = np.exp(scaled_logits) / np.exp(scaled_logits).sum(axis=1, keepdims=True)
    scaled_conf = scaled_probs.max(axis=1)
    scaled_pred = scaled_probs.argmax(axis=1)

    # ECE after calibration
    ece_after, bins_after = compute_ece(scaled_conf, scaled_pred, all_labels)
    print(f"\nECE (after T={T_opt:.2f}): {ece_after:.4f}")
    print(f"ECE reduction: {ece_before:.4f} → {ece_after:.4f} ({(1-ece_after/ece_before)*100:.1f}% better)")

    mean_conf_after = scaled_conf.mean()
    acc_after = (scaled_pred == all_labels).mean()
    print(f"Mean confidence after: {mean_conf_after:.4f} (was {mean_confidence:.4f})")
    print(f"Accuracy unchanged: {acc_after:.4f}")

    print("\nReliability diagram (after T scaling):")
    print(f"  {'Bin':>10} {'Count':>6} {'Acc':>6} {'Conf':>6} {'Gap':>6}")
    for b in bins_after:
        if b["count"] > 0:
            gap_str = f"+{b['gap']:.3f}" if b["gap"] > 0 else f"{b['gap']:.3f}"
            print(f"  {b['lo']:.2f}-{b['hi']:.2f} {b['count']:>6} {b['acc']:.4f} {b['conf']:.4f} {gap_str}")

    # Analyze wrong predictions by confidence
    wrong_mask = all_predictions != all_labels
    if wrong_mask.sum() > 0:
        wrong_confs = all_confidences[wrong_mask]
        print(f"\nHallucination analysis (wrong predictions):")
        print(f"  Total wrong: {wrong_mask.sum()} / {len(all_labels)} ({wrong_mask.mean():.2%})")
        print(f"  Mean confidence on wrong: {wrong_confs.mean():.4f}")
        print(f"  Wrong with conf > 0.5:  {(wrong_confs > 0.5).sum()}")
        print(f"  Wrong with conf > 0.7:  {(wrong_confs > 0.7).sum()}")
        print(f"  Wrong with conf > 0.9:  {(wrong_confs > 0.9).sum()}")

        # After calibration
        wrong_confs_cal = scaled_conf[wrong_mask]
        print(f"\n  After T={T_opt:.2f} calibration:")
        print(f"  Mean confidence on wrong: {wrong_confs_cal.mean():.4f}")
        print(f"  Wrong with conf > 0.5:  {(wrong_confs_cal > 0.5).sum()}")
        print(f"  Wrong with conf > 0.7:  {(wrong_confs_cal > 0.7).sum()}")
        print(f"  Wrong with conf > 0.9:  {(wrong_confs_cal > 0.9).sum()}")

    # Save calibration config
    calib_config = {
        "temperature": round(T_opt, 4),
        "ece_before": round(ece_before, 4),
        "ece_after": round(ece_after, 4),
        "mean_conf_before": round(float(mean_confidence), 4),
        "mean_conf_after": round(float(mean_conf_after), 4),
        "accuracy": round(float(accuracy), 4),
        "model_version": version,
    }
    calib_path = ckpt_dir / "calibration.json"
    with open(calib_path, "w") as f:
        json.dump(calib_config, f, indent=2)
    print(f"\nCalibration config saved to {calib_path}")


if __name__ == "__main__":
    main()
