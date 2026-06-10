"""Algo-D / P0-W1 supporting tool: targeted top-up for under-sampled species.

Built specifically for the case ticket #D surfaced: ``Zoothera dauma`` only has
18 records in xc_expanded/manifest.json while the v7-head-223 training run
wants ``>=30`` (and ideally ``>=50``) per class. This script fetches more
Xeno-canto recordings *only* for the species you name (or auto-picks LOW
species from the latest audit JSON), avoiding the full 223-class loop that
``scripts/download_expanded.py`` would do.

Standalone (no import-time API-key check). Same file naming, same manifest
format as ``download_expanded.py`` so the dataset stays uniform.

Usage:

  # 0) (one-time) get an API key from https://xeno-canto.org/account/api
  $env:XC_API_KEY = "<paste your key>"

  # 1) dry-run — preview how many downloadable recordings the API has
  python scripts/algo_d/topup_low_sample_species.py --species "Zoothera dauma" --target 50 --dry-run

  # 2) actually download (default target 50 per species)
  python scripts/algo_d/topup_low_sample_species.py --species "Zoothera dauma" --target 50

  # 3) auto-pick from the audit report (everything tagged LOW)
  python scripts/algo_d/topup_low_sample_species.py --from-audit --target 50

Exit codes:
  0 = success (manifest grew, or already at/above target)
  2 = API quota hit / network error
  3 = inputs missing (XC_API_KEY, manifest path, audit report)
  4 = species not found in Xeno-canto v3 API responses
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover
    print("[FATAL] 'requests' not installed; pip install requests")
    sys.exit(3)

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

REPO_ROOT = Path(__file__).resolve().parents[2]
SMP_DATA = REPO_ROOT / "species_monitoring_platform" / "data" / "xc_expanded"
MANIFEST_PATH = SMP_DATA / "manifest.json"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "_artifacts"
AUDIT_REPORT_PATH = ARTIFACTS_DIR / "head_gap_report.json"

BASE_URL = "https://xeno-canto.org/api/3/recordings"
REQUEST_DELAY = 0.8
DOWNLOAD_DELAY = 0.2
QUALITY_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}


def search_species(scientific_name: str, api_key: str, page: int = 1) -> dict:
    """Single XC v3 API page. Returns parsed JSON or empty result on error."""
    query = f'sp:"{scientific_name}" grp:birds'
    params = {"query": query, "key": api_key, "page": page}
    try:
        resp = requests.get(BASE_URL, params=params, timeout=30)
        if resp.status_code != 200:
            return {"recordings": [], "numRecordings": "0", "_http_status": resp.status_code}
        return resp.json()
    except requests.RequestException as exc:
        return {"recordings": [], "numRecordings": "0", "_error": str(exc)}


def get_downloadable(scientific_name: str, api_key: str, max_results: int) -> list[dict]:
    """Walk up to 6 pages, return recordings with file URLs sorted by quality."""
    results: list[dict] = []
    for page in range(1, 7):
        data = search_species(scientific_name, api_key, page=page)
        recs = data.get("recordings", [])
        if not recs:
            if "_http_status" in data:
                print(f"    [warn] page={page} HTTP {data['_http_status']}")
            if "_error" in data:
                print(f"    [warn] page={page} error: {data['_error']}")
            break
        for rec in recs:
            file_url = rec.get("file", "")
            if not file_url:
                continue
            if not file_url.startswith("http"):
                file_url = "https:" + file_url
            results.append({
                "id": rec.get("id", ""),
                "scientific": rec.get("sp", scientific_name),
                "english": rec.get("en", ""),
                "country": rec.get("cnt", ""),
                "quality": rec.get("q", ""),
                "length": rec.get("length", ""),
                "file_url": file_url,
            })
        if page == 1 and len(results) == 0:
            break
        if len(results) >= max_results:
            break
        time.sleep(REQUEST_DELAY)
    results.sort(key=lambda r: QUALITY_ORDER.get(r["quality"], 5))
    return results[:max_results]


def download_file(url: str, filepath: Path, api_key: str) -> bool:
    """Stream a recording to disk. Returns True if file > 1KB."""
    try:
        resp = requests.get(url, params={"key": api_key}, timeout=60, stream=True)
        if resp.status_code != 200:
            return False
        if "html" in resp.headers.get("content-type", "").lower():
            return False
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return filepath.stat().st_size > 1000
    except requests.RequestException:
        if filepath.exists():
            filepath.unlink(missing_ok=True)
        return False


def load_manifest() -> tuple[list[dict], dict[str, int], set[str]]:
    """Load existing manifest; return (rows, per-species count, file_path set)."""
    if not MANIFEST_PATH.exists():
        return [], {}, set()
    rows = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    paths: set[str] = set()
    for item in rows:
        sp = item.get("species_scientific", "")
        counts[sp] = counts.get(sp, 0) + 1
        if item.get("file_path"):
            paths.add(item["file_path"])
    return rows, counts, paths


def save_manifest(rows: list[dict]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def species_from_audit() -> list[str]:
    """Read the audit report and return the scientific names tagged LOW (<30)."""
    if not AUDIT_REPORT_PATH.exists():
        print(f"[FATAL] audit report not found: {AUDIT_REPORT_PATH}\n"
              f"        run audit_species_head_gap.py first.")
        return []
    rep = json.loads(AUDIT_REPORT_PATH.read_text(encoding="utf-8"))
    low = [s["scientific"]
           for s in rep.get("gap", {}).get("trimmed_at_runtime", [])
           if s.get("manifest_records", 0) < 30]
    return low


def topup_one(scientific: str, target: int, api_key: str, dry_run: bool,
              rows: list[dict], counts: dict[str, int], paths: set[str]) -> dict:
    """Top up one species. Returns a stats dict."""
    have = counts.get(scientific, 0)
    needed = max(0, target - have)
    stats = {"scientific": scientific, "have_before": have, "target": target,
             "needed": needed, "downloaded": 0, "failed": 0, "skipped": 0,
             "from_cache": 0, "no_api_files": 0}
    print(f"\n=== {scientific} :: have={have}, target={target}, need={needed} ===")
    if needed == 0:
        print("  -> already at/above target, skipping")
        stats["skipped"] = 1
        return stats

    # Ask the API for ~2x more than needed (low-yield filtering by quality)
    api_results = get_downloadable(scientific, api_key, max_results=needed * 2)
    if not api_results:
        stats["no_api_files"] = 1
        print("  -> XC API returned no downloadable recordings")
        return stats
    print(f"  -> XC API returned {len(api_results)} candidate recordings "
          f"(quality dist: {dict((q, sum(1 for r in api_results if r['quality']==q)) for q in 'ABCDE')})")

    if dry_run:
        print("  -> DRY RUN: not downloading.")
        for r in api_results[:5]:
            print(f"     [{r['quality']}] XC{r['id']} {r['country']}  {r['file_url']}")
        if len(api_results) > 5:
            print(f"     ... and {len(api_results) - 5} more")
        return stats

    sp_dir = SMP_DATA / scientific.replace(" ", "_")
    sp_dir.mkdir(parents=True, exist_ok=True)
    for rec in api_results:
        if stats["downloaded"] + stats["from_cache"] >= needed:
            break
        filepath = sp_dir / f"XC{rec['id']}.mp3"
        if str(filepath) in paths:
            continue
        if filepath.exists() and filepath.stat().st_size > 1000:
            stats["from_cache"] += 1
            entry = _make_entry(rec, scientific, filepath)
            rows.append(entry)
            paths.add(str(filepath))
            counts[scientific] = counts.get(scientific, 0) + 1
            print(f"     [cache] XC{rec['id']}")
            continue
        ok = download_file(rec["file_url"], filepath, api_key)
        time.sleep(DOWNLOAD_DELAY)
        if ok:
            stats["downloaded"] += 1
            entry = _make_entry(rec, scientific, filepath)
            rows.append(entry)
            paths.add(str(filepath))
            counts[scientific] = counts.get(scientific, 0) + 1
            print(f"     [ok]    XC{rec['id']} ({rec['quality']}, {rec['country']})")
        else:
            stats["failed"] += 1
            print(f"     [fail]  XC{rec['id']}")
    stats["have_after"] = counts.get(scientific, 0)
    print(f"  -> have_after={stats['have_after']}  downloaded={stats['downloaded']} "
          f"from_cache={stats['from_cache']} failed={stats['failed']}")
    return stats


def _make_entry(rec: dict, scientific: str, filepath: Path) -> dict:
    """Build a manifest row in the same shape as download_expanded.py."""
    return {
        "file_path": str(filepath),
        "species_scientific": scientific,
        "species_chinese": "",
        "species_english": rec.get("english", ""),
        "xc_id": rec.get("id", ""),
        "quality": rec.get("quality", ""),
        "country": rec.get("country", ""),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--species", action="append", default=[],
                    help="scientific name; repeatable. e.g. --species 'Zoothera dauma'")
    ap.add_argument("--from-audit", action="store_true",
                    help="auto-pick species tagged LOW from latest audit report")
    ap.add_argument("--target", type=int, default=50,
                    help="target per-species record count (default 50)")
    ap.add_argument("--dry-run", action="store_true",
                    help="query API but do not download")
    args = ap.parse_args()

    api_key = os.environ.get("XC_API_KEY", "").strip()
    if not api_key and not args.dry_run:
        # Allow dry-run to also fail without key, since XC v3 requires key on every call.
        print("[FATAL] XC_API_KEY env var is required (get one at https://xeno-canto.org/account/api)")
        return 3
    if not api_key:
        print("[FATAL] XC_API_KEY env var is required even for dry-run (XC v3 API)")
        return 3

    species_list: list[str] = list(args.species)
    if args.from_audit:
        species_list.extend(s for s in species_from_audit() if s not in species_list)
    if not species_list:
        print("[FATAL] no species given. Use --species or --from-audit.")
        return 3

    if not MANIFEST_PATH.exists():
        print(f"[FATAL] manifest not found: {MANIFEST_PATH}")
        return 3

    rows, counts, paths = load_manifest()
    print(f"Manifest: {len(rows)} rows, {len(counts)} species (current)")

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = ARTIFACTS_DIR / f"topup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%SZ')}.json"

    all_stats: list[dict] = []
    for sci in species_list:
        try:
            stats = topup_one(sci, args.target, api_key, args.dry_run, rows, counts, paths)
        except Exception as exc:  # pragma: no cover (network errors etc.)
            print(f"  [error] {sci}: {exc}")
            stats = {"scientific": sci, "error": str(exc)}
        all_stats.append(stats)
        # Per-species checkpoint of the manifest (cheap insurance against ctrl-c)
        if not args.dry_run:
            save_manifest(rows)

    if not args.dry_run:
        save_manifest(rows)
    log_path.write_text(json.dumps({
        "ran_at_utc": datetime.now(timezone.utc).isoformat(),
        "target": args.target,
        "dry_run": args.dry_run,
        "manifest_rows_after": len(rows),
        "per_species": all_stats,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSession log: {log_path}")
    print(f"Manifest:    {MANIFEST_PATH}")
    print(f"Manifest rows now: {len(rows)}")
    print("Next: re-run audit to confirm Zoothera dauma >= target:")
    print('  python "f:\\Gorsachius magnificus\\scripts\\algo_d\\audit_species_head_gap.py"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
