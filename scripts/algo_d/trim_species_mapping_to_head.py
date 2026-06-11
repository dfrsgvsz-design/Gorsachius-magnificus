"""Algo-D / P0-W1 PIVOT (GPU-off): trim runtime species_mapping.json down to
the checkpoint head and produce a sidecar list of the species we're
deliberately routing through BirdNET fallback instead of the main CNN.

This replaces the GPU-side fix (train head 217 -> 223) for the current
release cycle. After this script runs:

  backend/checkpoints/species_mapping.json
    -- only the species indices [0..head_out_features-1] kept (e.g. 0..216)
    -- the trimmed-off species DO NOT appear in main CNN outputs
  backend/checkpoints/explicit_fallback_species.json (NEW)
    -- the species indices >= head, with notes on why they are fallback-only
    -- inference_fallback.py will read this and proactively route them
       through BirdNET embedding + KNN (or BirdNET classifier)
  backend/checkpoints/species_mapping.pre_pivot_backup.json (NEW)
    -- pre-trim snapshot, in case GPU comes back later and we want to undo

Exit codes:
  0 = trim succeeded (or dry-run)
  2 = mapping == head already (no trim needed; safe re-run)
  3 = inputs missing
  4 = checkpoint load failed

Usage:
  python scripts/algo_d/trim_species_mapping_to_head.py
  python scripts/algo_d/trim_species_mapping_to_head.py --dry-run
  python scripts/algo_d/trim_species_mapping_to_head.py --restore   # roll back to backup
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

REPO_ROOT = Path(__file__).resolve().parents[2]
SMP = REPO_ROOT / "species_monitoring_platform"
CKPT_DIR = SMP / "backend" / "checkpoints"
MAPPING_PATH = CKPT_DIR / "species_mapping.json"
CHECKPOINT_PATH = CKPT_DIR / "best_model.pth"
BACKUP_PATH = CKPT_DIR / "species_mapping.pre_pivot_backup.json"
FALLBACK_PATH = CKPT_DIR / "explicit_fallback_species.json"


def _infer_head(checkpoint: dict) -> int | None:
    state = checkpoint.get("model_state_dict") or {}
    for key in ("fc.weight", "classifier.weight", "head.weight",
                "species_head.weight", "cls_head.weight"):
        tensor = state.get(key)
        if tensor is not None and getattr(tensor, "ndim", 0) >= 1:
            return int(tensor.shape[0])
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--restore", action="store_true",
                    help="restore from species_mapping.pre_pivot_backup.json")
    args = ap.parse_args()

    if args.restore:
        if not BACKUP_PATH.exists():
            print(f"[FATAL] no backup at {BACKUP_PATH}")
            return 3
        shutil.copy2(BACKUP_PATH, MAPPING_PATH)
        if FALLBACK_PATH.exists():
            FALLBACK_PATH.unlink()
        print(f"  restored {MAPPING_PATH.name} from backup")
        print(f"  removed {FALLBACK_PATH.name}")
        return 0

    if not MAPPING_PATH.exists():
        print(f"[FATAL] mapping not found: {MAPPING_PATH}")
        return 3
    if not CHECKPOINT_PATH.exists():
        print(f"[FATAL] checkpoint not found: {CHECKPOINT_PATH}")
        return 3

    print("=" * 72)
    print(" Algo-D / P0-W1 PIVOT :: trim species_mapping.json to checkpoint head")
    print(f"  mapping    = {MAPPING_PATH}")
    print(f"  checkpoint = {CHECKPOINT_PATH}")
    print(f"  dry_run    = {args.dry_run}")
    print("=" * 72)

    try:
        import torch  # noqa: WPS433  - deferred so script can show --help without torch
        checkpoint = torch.load(CHECKPOINT_PATH, map_location="cpu", weights_only=True)
    except Exception as exc:  # pragma: no cover
        print(f"[FATAL] cannot load checkpoint: {type(exc).__name__}: {exc}")
        return 4
    head = _infer_head(checkpoint)
    if head is None:
        print("[FATAL] could not infer checkpoint head size")
        return 4

    mapping = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    species_to_idx: dict[str, int] = mapping.get("species_to_idx") or {}
    idx_to_species: dict[str, str] = mapping.get("idx_to_species") or {}
    n = len(species_to_idx)

    print(f"  mapping species  : {n}")
    print(f"  checkpoint head  : {head}")

    if n == head:
        print(f"  status           : already in sync; nothing to trim. Exiting 2.")
        return 2

    if n < head:
        print(f"[WARN] mapping ({n}) is SMALLER than head ({head}); "
              "checkpoint will produce indices the mapping cannot resolve. "
              "Restore checkpoint or extend mapping.")
        return 4

    # Trim: keep [0..head-1], drop the rest.
    keep_pairs = [(sci, idx) for sci, idx in species_to_idx.items() if int(idx) < head]
    drop_pairs = [(sci, idx) for sci, idx in species_to_idx.items() if int(idx) >= head]
    drop_pairs.sort(key=lambda p: int(p[1]))

    print(f"  keep             : {len(keep_pairs)}")
    print(f"  drop -> fallback : {len(drop_pairs)}")
    for sci, idx in drop_pairs:
        print(f"      [{int(idx):>3}] {sci}")

    if args.dry_run:
        print("\n[DRY RUN] no files modified.")
        return 0

    if not BACKUP_PATH.exists():
        shutil.copy2(MAPPING_PATH, BACKUP_PATH)
        print(f"  backed up original to {BACKUP_PATH.name}")

    new_mapping = {
        "species_to_idx": {sci: int(idx) for sci, idx in keep_pairs},
        "idx_to_species": {str(idx): sci for sci, idx in keep_pairs},
        "_trim_meta": {
            "trimmed_at_utc": datetime.now(timezone.utc).isoformat(),
            "trimmed_by": "scripts/algo_d/trim_species_mapping_to_head.py",
            "ticket": "Algo-D / P0-W1 PIVOT (GPU-off; fall back to Option 2 + BirdNET routing)",
            "original_mapping_size": n,
            "checkpoint_head": head,
            "dropped_species_count": len(drop_pairs),
        },
    }
    MAPPING_PATH.write_text(json.dumps(new_mapping, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    print(f"\n  wrote trimmed mapping ({head} species) to {MAPPING_PATH}")

    fallback_doc = {
        "_comment": (
            "Species explicitly routed through inference_fallback (BirdNET embedding "
            "+ KNN, then BirdNET classifier). These are the species that USED to be "
            "in species_mapping at indices >= head, but the current CNN checkpoint "
            "head cannot output them. inference_fallback.predict_species_fallback "
            "should still serve them when an audio file is uploaded."
        ),
        "ticket": "Algo-D / P0-W1 PIVOT (GPU-off)",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "checkpoint_head": head,
        "species": [
            {
                "original_idx": int(idx),
                "scientific_name": sci,
                "fallback_engine_preferred": "birdnet_embedding_knn",
                "ui_disclosure_label": "本物种走声学辅助识别(BirdNET)，可能精度低于主模型",
            }
            for sci, idx in drop_pairs
        ],
    }
    FALLBACK_PATH.write_text(json.dumps(fallback_doc, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    print(f"  wrote explicit fallback list ({len(drop_pairs)} species) to {FALLBACK_PATH}")

    print("\nDONE. Next:")
    print(f"  python \"{REPO_ROOT}\\scripts\\algo_d\\audit_species_head_gap.py\"")
    print("  # expected: PASS (mapping length matches checkpoint head)")
    print(f"  $env:ALGO_D_STRICT_HEAD_MATCH = '1'")
    print(f"  cd \"{SMP}\\backend\"; python -m uvicorn backend.main:app  # 0 trim warning expected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
