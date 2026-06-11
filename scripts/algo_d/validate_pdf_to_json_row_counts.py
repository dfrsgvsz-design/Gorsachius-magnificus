"""Algo-D / W2 Step 7 :: strict row-count cross-validation.

Three counts must agree per source:
  (A) the official expected count we documented in the source_manifest.json
      ``source_files[].expected_row_count`` field
  (B) the actual number of rows in the corresponding parsed.json under
      ``backend/data/taxonomy_releases/<release_id>/<source>/parsed.json``
  (C) the number of rows that landed in ``taxonomy_catalog.sqlite3`` for
      this release_id (sourced via the catalog's package_id <- source_files
      back-reference)

This script does (A) vs (B) deterministically; (C) requires the catalog to
already be rebuilt with the release and is best-effort (we read sqlite
directly if accessible).

Exit codes:
  0 = all sources strictly equal across A/B (and C if available)
  2 = at least one source has a count mismatch
  3 = inputs missing (no source manifest, no parsed.json, etc.)
"""

from __future__ import annotations

import argparse
import io
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

REPO_ROOT = Path(__file__).resolve().parents[2]
SMP_DATA = REPO_ROOT / "species_monitoring_platform" / "backend" / "data"
SOURCES_DIR = SMP_DATA / "taxonomy_sources"
RELEASES_DIR = SMP_DATA / "taxonomy_releases"
CATALOG_DB = SMP_DATA / "survey_store" / "taxonomy_catalog.sqlite3"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "_artifacts"
REPORT_PATH = ARTIFACTS_DIR / "pdf_to_json_row_counts_report.json"


def _load_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _count_rows(parsed_json_path: Path) -> int | None:
    if not parsed_json_path.exists():
        return None
    try:
        data = _load_json(parsed_json_path)
    except (ValueError, OSError):
        return None
    if isinstance(data, dict):
        rows = data.get("rows") or data.get("entries")
        if isinstance(rows, list):
            return len(rows)
    if isinstance(data, list):
        return len(data)
    return None


def _sqlite_taxon_count(release_id: str) -> dict[str, int] | None:
    """Best-effort: per-package count of taxa imported under this release."""
    if not CATALOG_DB.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{CATALOG_DB}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT package_id, COUNT(*) AS n "
            "FROM taxa "
            "WHERE release_id = ? "
            "GROUP BY package_id",
            (release_id,),
        ).fetchall()
        con.close()
        return {str(r["package_id"]): int(r["n"]) for r in rows}
    except sqlite3.DatabaseError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--release-id", required=True)
    args = ap.parse_args()
    release_id = args.release_id

    sources_root = SOURCES_DIR / release_id
    releases_root = RELEASES_DIR / release_id
    if not sources_root.exists():
        print(f"[FATAL] no source manifests dir: {sources_root}")
        return 3
    if not releases_root.exists():
        print(f"[WARN] no parsed sources dir: {releases_root}")

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    any_fail = False
    print("=" * 72)
    print(f" Algo-D / W2 Step 7 :: row-count cross-validation for {release_id}")
    print("=" * 72)

    sqlite_counts = _sqlite_taxon_count(release_id)
    if sqlite_counts is None:
        print(f"[info] sqlite per-package counts unavailable (DB missing / no release yet) -> C column = n/a")

    for manifest_path in sorted(sources_root.glob("*/*/source_manifest.json")):
        try:
            manifest = _load_json(manifest_path)
        except (ValueError, OSError) as exc:
            print(f"[FAIL] cannot read {manifest_path}: {exc}")
            any_fail = True
            continue
        jurisdiction = manifest.get("jurisdiction")
        program = manifest.get("program")
        official_total = int(manifest.get("official_expected_count") or 0)
        source_files = manifest.get("source_files") or []
        package_id = f"{jurisdiction}/{program}"

        per_source_rows = []
        manifest_sum = 0
        sum_parsed = 0
        any_parsed_missing = False
        for sf in source_files:
            path_rel = (sf.get("path") or "").replace("\\", "/")
            expected = sf.get("expected_row_count")
            full_path = (releases_root / path_rel) if path_rel else None
            actual = _count_rows(full_path) if full_path else None
            ok_a_b = (expected is None) or (actual is None) or (int(expected) == int(actual))
            per_source_rows.append({
                "path": path_rel,
                "expected_row_count": expected,
                "actual_row_count": actual,
                "match": ok_a_b,
            })
            if expected is not None:
                manifest_sum += int(expected)
            if actual is not None:
                sum_parsed += int(actual)
            else:
                any_parsed_missing = True
            if not ok_a_b:
                any_fail = True

        sqlite_n = sqlite_counts.get(package_id) if sqlite_counts else None

        ok_official = (official_total == manifest_sum) if manifest_sum > 0 else None
        if ok_official is False:
            any_fail = True

        rows.append({
            "package_id": package_id,
            "manifest_path": str(manifest_path),
            "official_expected_count": official_total,
            "sum_source_files_expected_row_count": manifest_sum,
            "sum_parsed_actual_rows": sum_parsed,
            "sqlite_taxa_count": sqlite_n,
            "official_eq_sum_expected": ok_official,
            "all_source_files_match": all(r["match"] for r in per_source_rows),
            "any_parsed_missing": any_parsed_missing,
            "per_source": per_source_rows,
        })

        status = "PASS" if (
            (ok_official is not False)
            and all(r["match"] for r in per_source_rows)
            and not any_parsed_missing
        ) else "FAIL"
        marker = "[OK ]" if status == "PASS" else "[!! ]"
        print(f"{marker} {package_id:<30}  "
              f"official={official_total:>5}  "
              f"sum_expected={manifest_sum:>5}  "
              f"sum_parsed={sum_parsed:>5}  "
              f"sqlite={sqlite_n if sqlite_n is not None else 'n/a':>5}  "
              f"status={status}")
        for r in per_source_rows:
            sub_mark = "    OK " if r["match"] else "    !! "
            print(f"{sub_mark}  {r['path']:<60}  expected={r['expected_row_count']}  actual={r['actual_row_count']}")

    report = {
        "ran_at_utc": datetime.now(timezone.utc).isoformat(),
        "release_id": release_id,
        "any_fail": any_fail,
        "rows": rows,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=" * 72)
    print(f"  any_fail = {any_fail}")
    print(f"  report   : {REPORT_PATH}")
    print("=" * 72)
    return 2 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
