"""Verify deployed model: load from backend/checkpoints and test inference."""
import sys
import json
import time
import numpy as np
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import torch
from cnn_model import create_model, count_parameters
from audio_processor import load_audio, audio_to_mel_spectrogram, normalize_spectrogram, DEFAULT_SR, SEGMENT_DURATION

MODEL_DIR = Path(__file__).parent.parent / "backend" / "checkpoints"
MANIFEST = Path(__file__).parent.parent / "data" / "xc_expanded" / "manifest.json"


def load_model():
    model_path = MODEL_DIR / "best_model.pth"
    mapping_path = MODEL_DIR / "species_mapping.json"

    with open(mapping_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    species_to_idx = data["species_to_idx"]
    idx_to_species = {int(k): v for k, v in data["idx_to_species"].items()}

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    checkpoint = torch.load(model_path, map_location=device, weights_only=False)

    lite = checkpoint.get("lite", False)
    num_species = len(species_to_idx)
    model = create_model(num_species=num_species, lite=lite).to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    print(f"Model loaded: {num_species} species, "
          f"{'Lite' if lite else 'Full ResNet'}, "
          f"params={count_parameters(model):,}, "
          f"val_acc={checkpoint.get('val_acc', '?'):.4f}, "
          f"epoch={checkpoint.get('epoch', '?')}")
    print(f"Device: {device}")

    return model, species_to_idx, idx_to_species, device


def predict(model, file_path, device, top_k=5, use_tta=False):
    try:
        y, sr = load_audio(file_path, sr=DEFAULT_SR, duration=SEGMENT_DURATION + 1)
    except Exception as e:
        return None, f"load error: {e}"

    target_len = int(SEGMENT_DURATION * DEFAULT_SR)
    if len(y) > target_len:
        start = (len(y) - target_len) // 2
        y = y[start:start + target_len]
    elif len(y) < target_len:
        y = np.pad(y, (0, target_len - len(y)))

    mel = audio_to_mel_spectrogram(y, sr=DEFAULT_SR)
    mel = normalize_spectrogram(mel)
    tensor = torch.FloatTensor(mel).unsqueeze(0).unsqueeze(0).to(device)

    with torch.no_grad():
        logits = model(tensor)
        if use_tta:
            tensor_flip = torch.flip(tensor, dims=[-1])
            logits_flip = model(tensor_flip)
            logits = (logits + logits_flip) / 2.0
        probs = torch.softmax(logits, dim=1)[0]
        top_probs, top_indices = probs.topk(top_k)

    results = []
    for p, idx in zip(top_probs.cpu().numpy(), top_indices.cpu().numpy()):
        results.append((int(idx), float(p)))
    return results, None


def evaluate(model, test_items, species_to_idx, device, use_tta=False, label=""):
    correct_top1 = 0
    correct_top5 = 0
    total = 0
    errors = 0

    start = time.time()
    for i, item in enumerate(test_items):
        fp = item["file_path"]
        true_species = item["species_scientific"]
        true_idx = species_to_idx.get(true_species, -1)
        if true_idx < 0:
            continue

        results, err = predict(model, fp, device, use_tta=use_tta)
        if err:
            errors += 1
            continue

        total += 1
        pred_idx = results[0][0]
        if pred_idx == true_idx:
            correct_top1 += 1
        if any(idx == true_idx for idx, _ in results):
            correct_top5 += 1

    elapsed = time.time() - start
    top1 = correct_top1 / max(total, 1)
    top5 = correct_top5 / max(total, 1)
    speed = elapsed / max(total, 1) * 1000

    print(f"  [{label}] Top-1: {top1:.4f} ({correct_top1}/{total})  "
          f"Top-5: {top5:.4f} ({correct_top5}/{total})  "
          f"Speed: {speed:.0f}ms/sample  Errors: {errors}")
    return top1, top5


def main():
    model, species_to_idx, idx_to_species, device = load_model()

    manifest = json.load(open(MANIFEST, "r", encoding="utf-8"))
    np.random.seed(42)
    np.random.shuffle(manifest)

    test_items = manifest[:300]
    print(f"\nEvaluating on {len(test_items)} samples (seed=42)...")
    print(f"{'='*70}")

    t1_no, t5_no = evaluate(model, test_items, species_to_idx, device,
                             use_tta=False, label="No TTA ")
    t1_tta, t5_tta = evaluate(model, test_items, species_to_idx, device,
                               use_tta=True, label="With TTA")

    print(f"{'='*70}")
    print(f"TTA improvement: Top-1 {t1_no:.4f} -> {t1_tta:.4f} "
          f"(+{(t1_tta-t1_no)*100:.2f}pp)")
    print(f"                 Top-5 {t5_no:.4f} -> {t5_tta:.4f} "
          f"(+{(t5_tta-t5_no)*100:.2f}pp)")


if __name__ == "__main__":
    main()
