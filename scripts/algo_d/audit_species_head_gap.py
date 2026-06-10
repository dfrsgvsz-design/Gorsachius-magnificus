"""Audit species-head gap for Algorithm-D ticket #D, P0-W1.

Compares:
  - Runtime mapping  (species_mapping.json shipped under MODEL_DIR)
  - Checkpoint head  (out_features of fc / classifier / head weight)
  - Training manifest (data/xc_expanded/manifest.json source of truth)

Outputs a structured JSON report at  scripts/algo_d/_artifacts/head_gap_report.json
and a human-readable summary on stdout. Exit code:
  0 = mapping len == checkpoint head out_features  (no gap)
  2 = gap detected (the failure mode that triggered ticket #D)
  3 = inputs missing
"""

from __future__ import annotations

import io
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

REPO_ROOT = Path(__file__).resolve().parents[2]
SMP = REPO_ROOT / "species_monitoring_platform"

MAPPING_PATH = SMP / "backend" / "checkpoints" / "species_mapping.json"
CHECKPOINT_PATH = SMP / "backend" / "checkpoints" / "best_model.pth"
MANIFEST_PATH = SMP / "data" / "xc_expanded" / "manifest.json"
CALIBRATION_PATH = SMP / "backend" / "checkpoints" / "calibration.json"

ARTIFACTS_DIR = Path(__file__).resolve().parent / "_artifacts"
REPORT_PATH = ARTIFACTS_DIR / "head_gap_report.json"

CANDIDATE_HEAD_KEYS = (
    "fc.weight",
    "classifier.weight",
    "head.weight",
    "species_head.weight",
    "cls_head.weight",
)


def infer_checkpoint_head(checkpoint: dict) -> int | None:
    state = checkpoint.get("model_state_dict") or {}
    for key in CANDIDATE_HEAD_KEYS:
        tensor = state.get(key)
        if tensor is not None and getattr(tensor, "ndim", 0) >= 1:
            return int(tensor.shape[0])
    return None


def load_json(p: Path):
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    mapping = load_json(MAPPING_PATH)
    if mapping is None:
        print(f"[FATAL] species_mapping.json missing: {MAPPING_PATH}")
        return 3

    species_to_idx: dict[str, int] = mapping["species_to_idx"]
    mapping_species = sorted(species_to_idx.keys())
    mapping_len = len(mapping_species)

    # Checkpoint head requires torch; gate the import so audit can still report
    # mapping + manifest stats on machines without torch installed.
    head: int | None = None
    head_error: str | None = None
    if CHECKPOINT_PATH.exists():
        try:
            import torch  # noqa: WPS433  (deferred import is intentional)

            checkpoint = torch.load(CHECKPOINT_PATH, map_location="cpu", weights_only=True)
            head = infer_checkpoint_head(checkpoint)
        except Exception as exc:  # pragma: no cover  (env without torch / corrupt ckpt)
            head_error = f"{type(exc).__name__}: {exc}"
    else:
        head_error = f"checkpoint missing: {CHECKPOINT_PATH}"

    manifest_species_counts: Counter[str] = Counter()
    manifest_rows = 0
    if MANIFEST_PATH.exists():
        manifest = load_json(MANIFEST_PATH)
        if isinstance(manifest, list):
            manifest_rows = len(manifest)
            manifest_species_counts.update(
                item.get("species_scientific", "")
                for item in manifest
                if isinstance(item, dict)
            )

    manifest_species = sorted(k for k in manifest_species_counts if k)
    manifest_len = len(manifest_species)

    trimmed_species: list[dict] = []
    if head is not None and mapping_len > head:
        idx_to_species = {int(k): v for k, v in mapping["idx_to_species"].items()}
        for idx in sorted(idx_to_species):
            if idx >= head:
                sci = idx_to_species[idx]
                trimmed_species.append(
                    {
                        "idx": idx,
                        "scientific": sci,
                        "manifest_records": manifest_species_counts.get(sci, 0),
                    }
                )

    in_mapping_not_in_manifest = sorted(set(mapping_species) - set(manifest_species))
    in_manifest_not_in_mapping = sorted(set(manifest_species) - set(mapping_species))

    calibration = load_json(CALIBRATION_PATH) or {}

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "ticket": "Algo-D / P0-W1 head-mapping gap audit",
        "paths": {
            "mapping": str(MAPPING_PATH),
            "checkpoint": str(CHECKPOINT_PATH),
            "manifest": str(MANIFEST_PATH),
            "calibration": str(CALIBRATION_PATH),
        },
        "mapping": {
            "len": mapping_len,
            "first": mapping_species[:3],
            "last": mapping_species[-3:],
        },
        "checkpoint": {
            "head_out_features": head,
            "load_error": head_error,
            "current_calibration": calibration,
        },
        "manifest_xc_expanded": {
            "rows": manifest_rows,
            "unique_species": manifest_len,
        },
        "gap": {
            "mapping_minus_head": (mapping_len - head) if head is not None else None,
            "trimmed_at_runtime": trimmed_species,
            "in_mapping_not_in_manifest": in_mapping_not_in_manifest,
            "in_manifest_not_in_mapping": in_manifest_not_in_mapping,
        },
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 72)
    print(" Algo-D species-head gap audit")
    print("=" * 72)
    print(f"  mapping len               : {mapping_len}")
    print(f"  checkpoint head           : {head}  ({'OK' if head_error is None else head_error})")
    print(f"  manifest xc_expanded rows : {manifest_rows}  unique_species={manifest_len}")
    print(f"  report                    : {REPORT_PATH}")
    if trimmed_species:
        print("  >> runtime-trimmed species (silently dropped from inference today):")
        for s in trimmed_species:
            tag = "OK " if s["manifest_records"] >= 30 else "LOW"
            print(f"    [{tag}] idx={s['idx']:>3}  {s['scientific']:<32}  manifest_rec={s['manifest_records']}")
    if in_mapping_not_in_manifest:
        print(f"  !! mapping species absent from manifest: {len(in_mapping_not_in_manifest)}")
        for sci in in_mapping_not_in_manifest[:20]:
            print(f"    - {sci}")
    if in_manifest_not_in_mapping:
        print(f"  !! manifest species absent from mapping: {len(in_manifest_not_in_mapping)}")
        for sci in in_manifest_not_in_mapping[:20]:
            print(f"    - {sci}")
    print("=" * 72)

    if head is not None and mapping_len != head:
        print(f"FAIL: mapping_len({mapping_len}) != head({head}); ticket P0-W1 condition reproduces.")
        return 2
    if head is None:
        print("WARN: could not infer checkpoint head; see load_error in report.")
        return 3
    print("PASS: mapping length matches checkpoint head; 0 trim warnings expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
