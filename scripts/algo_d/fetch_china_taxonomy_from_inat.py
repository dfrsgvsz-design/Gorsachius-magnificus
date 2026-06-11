"""Algo-D :: fetch China wildlife catalog from iNaturalist (no auth, no GPU).

Pulls research-grade species_counts for each of the 8 main groups in
China (iNat place_id = 6903) via the public iNaturalist API. For each
group, writes a JSON file under

    species_monitoring_platform/backend/data/taxonomy_releases/
        taxonomy_full_release_2026_W2/inat_china_species/
        <group>.json

in the same schema the rest of the catalog ingestion expects (entries
with internal_taxon_id, scientific_name, simplified_chinese_name,
english_common_name, group, inat_taxon_id, inat_observation_count_china).

The data is **observation-ranked**, not government-authoritative; it's
useful as a baseline national-scope catalog when the official PDFs
(\u4e09\u6709 2023 / \u56fd\u5bb6\u91cd\u70b9 2021 / Flora of China) are not yet ingested.

Usage:

  python scripts/algo_d/fetch_china_taxonomy_from_inat.py
  python scripts/algo_d/fetch_china_taxonomy_from_inat.py --groups Aves Plantae
  python scripts/algo_d/fetch_china_taxonomy_from_inat.py --max-per-group 5000

Requires only ``requests``; works on any machine, no GPU.
"""

from __future__ import annotations

import argparse
import io
import json
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
SMP_DATA = REPO_ROOT / "species_monitoring_platform" / "backend" / "data"
OUT_DIR_DEFAULT = SMP_DATA / "taxonomy_releases" / "taxonomy_full_release_2026_W2" / "inat_china_species"

CHINA_PLACE_ID = 6903
INAT_API = "https://api.inaturalist.org/v1/observations/species_counts"
USER_AGENT = "algo-d-research/1.0 (academic biodiversity catalog seeding; gorsachius monitoring platform)"
REQUEST_DELAY = 1.2  # iNat asks 1 req/s; be generous

ICONIC_GROUPS = [
    ("Aves",            "birds",            "\u9e1f"),
    ("Mammalia",        "mammals",          "\u54fa\u4e73"),
    ("Reptilia",        "reptiles",         "\u722c\u884c"),
    ("Amphibia",        "amphibians",       "\u4e24\u6816"),
    ("Actinopterygii",  "freshwater_fish",  "\u9c7c\u7c7b\uff08\u8f90\u9ccd\uff09"),
    ("Insecta",         "insects",          "\u6606\u866b"),
    ("Plantae",         "vascular_plants",  "\u690d\u7269"),
    ("Fungi",           "macrofungi",       "\u83cc\u83c7+\u5730\u8863"),
]


def fetch_species_counts_page(iconic: str, page: int, per_page: int = 500,
                              quality_grade: str | None = "research") -> dict:
    params = {
        "place_id": CHINA_PLACE_ID,
        "iconic_taxa": iconic,
        "per_page": per_page,
        "page": page,
        "locale": "zh-CN",
    }
    if quality_grade:
        # research = only research-grade IDs; "any" / None = all observations
        params["quality_grade"] = quality_grade
    sess = requests.Session()
    sess.headers["User-Agent"] = USER_AGENT
    try:
        r = sess.get(INAT_API, params=params, timeout=30)
    except requests.RequestException as exc:
        return {"_error": str(exc), "results": [], "total_results": 0}
    if r.status_code != 200:
        return {"_status": r.status_code, "results": [], "total_results": 0}
    try:
        return r.json()
    except ValueError:
        return {"_error": "bad json", "results": [], "total_results": 0}


def fetch_group(iconic: str, group: str, cn_label: str, max_count: int,
                per_page: int = 500, quality_grade: str | None = "research") -> dict:
    print(f"\n[{group} / iconic={iconic}] start (max_count={max_count}, "
          f"per_page={per_page}, quality_grade={quality_grade or 'any'})")
    all_entries: list[dict] = []
    total = None
    for page in range(1, 50):  # hard cap pagination
        payload = fetch_species_counts_page(iconic, page, per_page, quality_grade)
        if "_error" in payload:
            print(f"  [warn] page={page} error: {payload['_error']}")
            break
        if "_status" in payload:
            print(f"  [warn] page={page} HTTP {payload['_status']}")
            break
        results = payload.get("results", [])
        total = total if total is not None else int(payload.get("total_results", 0) or 0)
        if not results:
            break
        for item in results:
            taxon = item.get("taxon", {}) or {}
            sci = taxon.get("name", "")
            if not sci:
                continue
            inat_id = taxon.get("id")
            cn_name = taxon.get("preferred_common_name", "") or ""
            entry = {
                "internal_taxon_id": f"inat-{iconic.lower()}-{inat_id}",
                "scientific_name": sci,
                "simplified_chinese_name": cn_name,
                "english_common_name": "",  # iNat won't return both locales in one call
                "group": group,
                "inat_taxon_id": int(inat_id) if inat_id is not None else None,
                "inat_observation_count_china": int(item.get("count") or 0),
            }
            all_entries.append(entry)
            if len(all_entries) >= max_count:
                break
        print(f"  page={page} got {len(results)} entries (total so far {len(all_entries)} / api_total {total})")
        if len(all_entries) >= max_count or len(all_entries) >= total:
            break
        time.sleep(REQUEST_DELAY)
    return {
        "source": "inat_china_species_counts",
        "iconic_taxa": iconic,
        "group": group,
        "group_label_zh": cn_label,
        "place_id": CHINA_PLACE_ID,
        "place_name": "China",
        "quality_grade": quality_grade or "any",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "api_total_results": total or 0,
        "fetched_count": len(all_entries),
        "entries": all_entries,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--groups", nargs="+", default=None,
                    help="iconic taxa to fetch (default: all 8). e.g. --groups Aves Plantae")
    ap.add_argument("--max-per-group", type=int, default=2000)
    ap.add_argument("--per-page", type=int, default=500)
    ap.add_argument("--output-dir", default=str(OUT_DIR_DEFAULT))
    ap.add_argument("--quality-grade", default="research",
                    choices=["research", "needs_id", "casual", "any"],
                    help="iNat quality filter; default 'research'. Use 'any' to "
                         "include needs_id+casual and capture rarely-observed species "
                         "(closer to authoritative national checklist).")
    args = ap.parse_args()
    quality = None if args.quality_grade == "any" else args.quality_grade

    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.groups:
        wanted = set(args.groups)
        groups = [g for g in ICONIC_GROUPS if g[0] in wanted]
    else:
        groups = ICONIC_GROUPS

    print("=" * 72)
    print(" Algo-D :: fetch China taxonomy from iNaturalist")
    print(f"  output_dir    = {out_dir}")
    print(f"  groups        = {[g[0] for g in groups]}")
    print(f"  max_per_group = {args.max_per_group}")
    print("=" * 72)

    rollup = []
    for iconic, group, label in groups:
        result = fetch_group(iconic, group, label, args.max_per_group, args.per_page,
                             quality_grade=quality)
        out_path = out_dir / f"{group}.json"
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  -> wrote {out_path}  fetched={result['fetched_count']}  api_total={result['api_total_results']}")
        rollup.append({
            "group": group,
            "iconic_taxa": iconic,
            "api_total_results": result["api_total_results"],
            "fetched_count": result["fetched_count"],
            "out_path": str(out_path),
        })
        time.sleep(REQUEST_DELAY)

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "place_id": CHINA_PLACE_ID,
        "rollup": rollup,
        "total_entries": sum(r["fetched_count"] for r in rollup),
    }
    summary_path = out_dir / "_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=" * 72)
    print(f"  total entries fetched: {summary['total_entries']}")
    print(f"  rollup: {summary_path}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
