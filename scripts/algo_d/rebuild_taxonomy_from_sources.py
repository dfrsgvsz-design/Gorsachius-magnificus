"""Algo-D / W2 Steps 5+6 :: rebuild taxonomy_catalog.sqlite3 from source manifests.

Wraps :mod:`taxonomy_release_builder` so the W2 ingestion pipeline can be
driven from one command. It:

  1. Validates that every required ``source_manifest.json`` exists under
     ``backend/data/taxonomy_sources/<release_id>/`` and that all referenced
     source files (parsed.json from PDF parsing) exist under
     ``backend/data/taxonomy_releases/<release_id>/``.
  2. Calls ``build_full_release_manifest(release_id)`` to assemble the
     full backbone manifest. This is what enforces the hardcoded
     mainland_china/terrestrial_vertebrates birds=1505 check.
  3. Writes the full manifest to
     ``backend/data/taxonomy_packages.full.<release_id>.json`` (parallel to
     the existing seed manifest; does NOT overwrite ``taxonomy_packages.json``).
  4. Triggers ``TaxonomyCatalog.rebuild_release(force=True, activate=...)``
     which inside :mod:`taxonomy_catalog` recomputes ``manifest_signature``
     and stores it on the ``taxonomy_releases`` row + the meta table.

Exit codes:
  0 = success (or dry-run completed without errors)
  2 = validation FAIL (missing sources, count mismatch, etc.)
  3 = inputs missing
  4 = catalog rebuild crashed

Usage:

  python scripts/algo_d/rebuild_taxonomy_from_sources.py `
      --release-id "taxonomy_full_release_2026_W2"

  # Activate immediately after build (PM has signed off):
  python scripts/algo_d/rebuild_taxonomy_from_sources.py `
      --release-id "taxonomy_full_release_2026_W2" --activate

  # Validate only, don't write or rebuild:
  python scripts/algo_d/rebuild_taxonomy_from_sources.py `
      --release-id "taxonomy_full_release_2026_W2" --dry-run
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
SHARED_DIR = REPO_ROOT / "shared"
SMP_DATA = SMP_BACKEND / "data"

sys.path.insert(0, str(SMP_BACKEND))
sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--release-id", required=True,
                    help="release id; must match every source_manifest.json release_id field")
    ap.add_argument("--activate", action="store_true",
                    help="activate the rebuilt release immediately (default: candidate-first)")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate inputs, do not write or rebuild")
    args = ap.parse_args()

    release_id = args.release_id
    print("=" * 72)
    print(" Algo-D / W2 :: rebuild taxonomy from source manifests")
    print(f"  release_id = {release_id}")
    print(f"  activate   = {args.activate}")
    print(f"  dry_run    = {args.dry_run}")
    print(f"  sources    = {SMP_DATA / 'taxonomy_sources' / release_id}")
    print(f"  releases   = {SMP_DATA / 'taxonomy_releases' / release_id}")
    print("=" * 72)

    # --- Step 1: validate source presence ---
    try:
        from shared.backend.stores import taxonomy_release_builder as trb
    except ImportError as exc:
        print(f"[FATAL] cannot import taxonomy_release_builder: {exc}")
        return 3

    print("\n[1/4] validate source presence...")
    try:
        reports = trb.validate_full_release_sources(release_id)
    except Exception as exc:  # pragma: no cover
        print(f"[FATAL] validate_full_release_sources crashed: {type(exc).__name__}: {exc}")
        return 4

    any_error = False
    for r in reports:
        pkg = r.get("package_id")
        errors = r.get("errors") or []
        if errors:
            any_error = True
            print(f"  [FAIL] {pkg}")
            for e in errors:
                print(f"     - {e}")
        else:
            print(f"  [OK]   {pkg}  ({r.get('source_manifest_path')})")
    if any_error:
        print("\nValidation FAILED. Fix source_manifest.json files / source_files and re-run.")
        return 2

    # --- Step 2: build full release manifest in memory ---
    print("\n[2/4] build_full_release_manifest(release_id)...")
    try:
        full_manifest = trb.build_full_release_manifest(release_id)
    except trb.FullReleaseValidationError as exc:
        print(f"[FAIL] build raised FullReleaseValidationError:\n{exc}")
        return 2
    except Exception as exc:  # pragma: no cover
        print(f"[FATAL] build crashed: {type(exc).__name__}: {exc}")
        return 4
    pkg_count = len(full_manifest.get("packages") or [])
    print(f"  OK: built manifest with {pkg_count} packages")

    full_manifest_path = SMP_DATA / f"taxonomy_packages.full.{release_id}.json"
    if args.dry_run:
        print(f"\n[DRY RUN] would write: {full_manifest_path}")
        print(f"[DRY RUN] would call catalog.rebuild_release(force=True, activate={args.activate})")
        return 0

    print(f"\n[3/4] write {full_manifest_path}")
    trb.write_json_file(full_manifest_path, full_manifest)

    # --- Step 4: trigger catalog rebuild ---
    print(f"\n[4/4] rebuild catalog (activate={args.activate})")
    try:
        from shared.backend.stores import taxonomy_catalog as tc
    except ImportError as exc:
        print(f"[FATAL] cannot import taxonomy_catalog: {exc}")
        return 3

    try:
        catalog = tc.get_taxonomy_catalog()
    except Exception as exc:  # pragma: no cover
        print(f"[FATAL] get_taxonomy_catalog crashed: {type(exc).__name__}: {exc}")
        return 4

    if not hasattr(catalog, "rebuild_release"):
        print("[FATAL] catalog has no rebuild_release method; check taxonomy_catalog version")
        return 4

    try:
        release_summary = catalog.rebuild_release(force=True, activate=args.activate)
    except ValueError as exc:
        print(f"[FAIL] rebuild_release raised: {exc}")
        return 2
    except Exception as exc:  # pragma: no cover
        print(f"[FATAL] rebuild crashed: {type(exc).__name__}: {exc}")
        return 4

    signature = release_summary.get("manifest_signature") or "(missing)"
    print(f"  OK: release_id={release_summary.get('taxonomy_release_id')}")
    print(f"      manifest_signature={signature[:16]}...{signature[-8:] if len(signature) > 24 else ''}")
    print(f"      is_current={release_summary.get('is_current_release')}")
    print(f"      imported_at={release_summary.get('imported_at')}")
    print(f"      activated_at={release_summary.get('activated_at')}")

    print("\nDONE. Next:")
    print(f"  python \"{REPO_ROOT}\\scripts\\algo_d\\validate_pdf_to_json_row_counts.py\" --release-id {release_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
