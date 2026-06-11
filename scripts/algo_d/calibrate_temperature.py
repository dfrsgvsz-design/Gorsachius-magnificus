r"""Algo-D / P0-W1: temperature scaling for the trained V7 student model.

Writes a calibration.json compatible with backend/main.py:load_model() which
reads `temperature`, `ece_after`, `model_version`. ECE_before and ECE_after
are computed with the standard equal-width-binning estimator (15 bins).

This docstring is a raw string (r-prefix) so the Windows example paths
below keep their literal backslashes. Without the prefix, 'data' followed
by a backslash and 'xc_expanded' would be parsed as a truncated hex
escape (Python sees \x then an underscore) and the repo-wide AST sweep /
compileall chokes here.

Usage (Windows):

  python "f:\Gorsachius magnificus\scripts\algo_d\calibrate_temperature.py" `
      --checkpoint "f:\Gorsachius magnificus\species_monitoring_platform\checkpoints_v7_223\best_student_v7.pth" `
      --manifest   "f:\Gorsachius magnificus\species_monitoring_platform\data\xc_expanded\manifest.json" `
      --output     "f:\Gorsachius magnificus\species_monitoring_platform\checkpoints_v7_223\calibration.json"

Requires the same conda/venv as train_gpu_v7.py (torch + librosa + the
cnn_model_v7 module on PYTHONPATH).
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

REPO_ROOT = Path(__file__).resolve().parents[2]
SMP_BACKEND = REPO_ROOT / "species_monitoring_platform" / "backend"
# Make backend modules importable so we can reuse the V7 model classes.
sys.path.insert(0, str(SMP_BACKEND))


def _compute_ece(probs, labels, n_bins: int = 15) -> float:
    """Standard ECE (Naeini et al., 2015), equal-width confidence bins."""
    import numpy as np

    confidences = probs.max(axis=1)
    predictions = probs.argmax(axis=1)
    accuracies = (predictions == labels).astype(float)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = len(labels)
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (confidences > lo) & (confidences <= hi) if i > 0 else (confidences >= lo) & (confidences <= hi)
        if mask.sum() == 0:
            continue
        avg_conf = float(confidences[mask].mean())
        avg_acc = float(accuracies[mask].mean())
        ece += (mask.sum() / n) * abs(avg_conf - avg_acc)
    return float(ece)


def _fit_temperature(logits, labels, max_iter: int = 200, lr: float = 0.02) -> float:
    """Minimize NLL on val set w.r.t. a single scalar temperature T > 0."""
    import torch
    import torch.nn.functional as F

    T = torch.nn.Parameter(torch.ones(1) * 1.5)
    opt = torch.optim.LBFGS([T], lr=lr, max_iter=max_iter)
    logits_t = torch.from_numpy(logits).float()
    labels_t = torch.from_numpy(labels).long()

    def closure():
        opt.zero_grad()
        loss = F.cross_entropy(logits_t / T.clamp(min=1e-3), labels_t)
        loss.backward()
        return loss

    opt.step(closure)
    return float(T.detach().clamp(min=1e-3).item())


def _build_val_loader(items, species_to_idx, batch_size: int = 24, num_workers: int = 2):
    """Reuse the V7 dataset class for parity with training-time preprocessing."""
    from torch.utils.data import DataLoader

    # Local import: depends on PYTHONPATH set above.
    from train_gpu_v7 import BirdDatasetV7  # type: ignore  (sibling-script import)

    ds = BirdDatasetV7(items, species_to_idx, augment=False)
    return DataLoader(ds, batch_size=batch_size, shuffle=False, num_workers=num_workers,
                      pin_memory=True, persistent_workers=num_workers > 0)


def _split_val_items(manifest_path: Path, val_split: float = 0.15, min_samples: int = 3):
    """Reproduce the train/val split logic from train_gpu_v7.setup_data."""
    import numpy as np
    from collections import Counter, defaultdict

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    species_counts = Counter(it.get("species_scientific", "") for it in manifest)
    valid = {sp for sp, c in species_counts.items() if sp and c >= min_samples}
    manifest = [it for it in manifest if it.get("species_scientific") in valid]
    species_list = sorted(valid)
    species_to_idx = {sp: i for i, sp in enumerate(species_list)}

    species_items: dict[str, list] = defaultdict(list)
    for it in manifest:
        species_items[it["species_scientific"]].append(it)

    rng = np.random.RandomState(42)
    val_items = []
    for sp, items in species_items.items():
        rng.shuffle(items)
        n_val = max(1, int(len(items) * val_split))
        val_items.extend(items[:n_val])
    rng.shuffle(val_items)
    return val_items, species_to_idx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True, help="path to best_student_v7.pth")
    parser.add_argument("--manifest", required=True, help="path to xc_expanded/manifest.json")
    parser.add_argument("--output", required=True, help="path to write calibration.json")
    parser.add_argument("--batch-size", type=int, default=24)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--val-split", type=float, default=0.15)
    parser.add_argument("--min-samples", type=int, default=3)
    args = parser.parse_args()

    ckpt_path = Path(args.checkpoint).resolve()
    manifest_path = Path(args.manifest).resolve()
    output_path = Path(args.output).resolve()

    if not ckpt_path.exists():
        print(f"[FATAL] checkpoint missing: {ckpt_path}")
        return 3
    if not manifest_path.exists():
        print(f"[FATAL] manifest missing: {manifest_path}")
        return 3

    print(f"[1/5] split val from manifest (seed=42, val_split={args.val_split})")
    val_items, species_to_idx = _split_val_items(manifest_path, args.val_split, args.min_samples)
    print(f"  val_items={len(val_items)}  num_species={len(species_to_idx)}")

    print("[2/5] load checkpoint")
    import numpy as np
    import torch

    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=True)
    ckpt_num_species = int(ckpt.get("num_species", -1))
    model_type = ckpt.get("model_type", "student")
    version = ckpt.get("version", "v7")
    if ckpt_num_species != len(species_to_idx):
        print(f"[FATAL] checkpoint num_species={ckpt_num_species} != manifest-derived={len(species_to_idx)};"
              " re-run training or re-check manifest")
        return 4

    print("[3/5] build model and load weights")
    from cnn_model_v7 import ConvNeXtBirdV7, ConvNeXtBirdV7Student  # type: ignore

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if model_type == "teacher":
        model = ConvNeXtBirdV7(num_species=ckpt_num_species, in_channels=2).to(device)
    else:
        model = ConvNeXtBirdV7Student(num_species=ckpt_num_species, in_channels=2).to(device)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()

    print(f"[4/5] run validation set through model on {device}")
    loader = _build_val_loader(val_items, species_to_idx, args.batch_size, args.workers)
    all_logits, all_labels = [], []
    with torch.no_grad():
        for batch_x, batch_y in loader:
            batch_x = batch_x.to(device, non_blocking=True)
            logits = model(batch_x)
            all_logits.append(logits.cpu().numpy())
            all_labels.append(batch_y.numpy())
    logits = np.concatenate(all_logits, axis=0)
    labels = np.concatenate(all_labels, axis=0)
    print(f"  collected logits.shape={logits.shape}, labels.shape={labels.shape}")

    print("[5/5] fit temperature, compute ECE before/after")
    probs_before = torch.softmax(torch.from_numpy(logits), dim=1).numpy()
    ece_before = _compute_ece(probs_before, labels)
    mean_conf_before = float(probs_before.max(axis=1).mean())
    acc = float((probs_before.argmax(axis=1) == labels).mean())

    T = _fit_temperature(logits, labels)
    probs_after = torch.softmax(torch.from_numpy(logits) / T, dim=1).numpy()
    ece_after = _compute_ece(probs_after, labels)
    mean_conf_after = float(probs_after.max(axis=1).mean())

    out = {
        "temperature": round(T, 4),
        "ece_before": round(ece_before, 4),
        "ece_after": round(ece_after, 4),
        "mean_conf_before": round(mean_conf_before, 4),
        "mean_conf_after": round(mean_conf_after, 4),
        "accuracy": round(acc, 4),
        "model_version": f"{version}-{model_type}",
        "ensemble": False,
        "calibrated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_checkpoint": str(ckpt_path),
        "source_manifest": str(manifest_path),
        "val_split": args.val_split,
        "val_items": len(val_items),
        "num_species": ckpt_num_species,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=" * 72)
    print(f"  T              = {T:.4f}")
    print(f"  ECE before     = {ece_before:.4f}")
    print(f"  ECE after      = {ece_after:.4f}")
    print(f"  accuracy       = {acc:.4f}")
    print(f"  model_version  = {out['model_version']}")
    print(f"  written        : {output_path}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
