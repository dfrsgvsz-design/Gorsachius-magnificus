#!/usr/bin/env python3
"""
Data Quality Checker — Scan downloaded audio data for issues.

Checks:
1. Corrupted files (can't be loaded)
2. Duration anomalies (too short < 1s or too long > 300s)
3. Silent recordings (max amplitude near zero)
4. Clipped recordings (excessive digital distortion)
5. Sample rate mismatches
6. Missing species in manifest

Usage:
    python scripts/check_data_quality.py --data ./data/xc_china
    python scripts/check_data_quality.py --data ./data/xc_v7 --fix
"""

import sys
import json
import argparse
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))


def check_audio_file(filepath, target_sr=48000):
    """Check a single audio file for quality issues."""
    issues = []
    try:
        import librosa
        y, sr = librosa.load(str(filepath), sr=None, mono=True)
    except Exception as e:
        return [{"type": "corrupted", "detail": str(e)}]

    duration = len(y) / sr
    if duration < 1.0:
        issues.append({"type": "too_short", "detail": f"{duration:.1f}s"})
    if duration > 300:
        issues.append({"type": "too_long", "detail": f"{duration:.1f}s"})

    import numpy as np
    max_amp = np.abs(y).max()
    if max_amp < 0.001:
        issues.append({"type": "silent", "detail": f"max_amp={max_amp:.6f}"})

    clip_ratio = np.mean(np.abs(y) > 0.99)
    if clip_ratio > 0.01:
        issues.append({"type": "clipped", "detail": f"{clip_ratio*100:.1f}% samples clipped"})

    if sr != target_sr:
        issues.append({"type": "sr_mismatch", "detail": f"expected {target_sr}, got {sr}"})

    return issues


def main():
    parser = argparse.ArgumentParser(description="Check audio data quality")
    parser.add_argument("--data", type=str, required=True, help="Data directory with manifest.json")
    parser.add_argument("--fix", action="store_true", help="Remove corrupted/silent files and update manifest")
    parser.add_argument("--limit", type=int, default=0, help="Check only first N files (0=all)")
    args = parser.parse_args()

    data_dir = Path(args.data)
    manifest_path = data_dir / "manifest.json"

    if not manifest_path.exists():
        print(f"[ERROR] manifest.json not found at {manifest_path}")
        sys.exit(1)

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    print(f"Checking {len(manifest)} recordings in {data_dir}...")
    print("=" * 60)

    if args.limit > 0:
        manifest = manifest[:args.limit]

    issue_counts = defaultdict(int)
    problematic = []
    good_entries = []

    for i, entry in enumerate(manifest):
        filepath = Path(entry["file_path"])
        if not filepath.exists():
            filepath = data_dir / filepath.name
        if not filepath.exists():
            issue_counts["missing"] += 1
            problematic.append((entry, [{"type": "missing", "detail": str(entry["file_path"])}]))
            continue

        issues = check_audio_file(filepath)
        if issues:
            for iss in issues:
                issue_counts[iss["type"]] += 1
            problematic.append((entry, issues))
        else:
            good_entries.append(entry)

        if (i + 1) % 100 == 0:
            print(f"  Checked {i+1}/{len(manifest)}...")

    print(f"\n{'=' * 60}")
    print(f"  Results:")
    print(f"  Total files: {len(manifest)}")
    print(f"  Good:        {len(good_entries)}")
    print(f"  Issues:      {len(problematic)}")
    print()
    for issue_type, count in sorted(issue_counts.items(), key=lambda x: -x[1]):
        print(f"    {issue_type:15s}: {count}")

    if problematic:
        print(f"\n  Problematic files:")
        for entry, issues in problematic[:20]:
            species = entry.get("species_chinese", entry.get("species_scientific", "?"))
            issue_str = ", ".join(f"{i['type']}" for i in issues)
            print(f"    {species}: {Path(entry['file_path']).name} [{issue_str}]")
        if len(problematic) > 20:
            print(f"    ... and {len(problematic) - 20} more")

    if args.fix and problematic:
        print(f"\n  Fixing: removing {len(problematic)} problematic entries from manifest...")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(good_entries, f, ensure_ascii=False, indent=2)
        print(f"  Updated manifest: {len(good_entries)} entries (was {len(manifest)})")

        # Remove corrupted files from disk
        removed = 0
        for entry, issues in problematic:
            if any(i["type"] in ("corrupted", "silent") for i in issues):
                fp = Path(entry["file_path"])
                if fp.exists():
                    fp.unlink()
                    removed += 1
        if removed:
            print(f"  Deleted {removed} corrupted/silent files from disk")

    report_path = data_dir / "quality_report.json"
    report = {
        "total": len(manifest),
        "good": len(good_entries),
        "issues": dict(issue_counts),
        "problematic_files": [
            {"file": str(entry["file_path"]), "species": entry.get("species_scientific", ""),
             "issues": issues}
            for entry, issues in problematic
        ],
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  Report saved: {report_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
