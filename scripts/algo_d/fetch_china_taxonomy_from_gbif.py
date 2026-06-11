"""Algo-D :: backfill China wildlife catalog from GBIF (no auth).

Complementary to ``fetch_china_taxonomy_from_inat.py``. iNaturalist only has
community-observed species; for the *full* authoritative China checklist
(Flora of China scale for plants, FishBase scale for fish) we read the
**Catalogue of Life China 2023 Annual Checklist** dataset hosted on GBIF.

Why the checklist dataset (not the occurrence-facet + per-key path the old
version used):
  - CoL China *is* the China species list, so everything in it is in-scope.
  - ``species/search`` returns the full classification + scientific name
    **inline in every page**, so we need ~N/1000 page calls instead of one
    ``/species/{key}`` detail call per species (31500 species -> ~32 page
    calls vs ~31500 detail calls / ~1 hour).

Two realities handled here:
  1. GBIF ``species/search`` paginates only up to offset+limit <= 100000, and
     the Tracheophyta (vascular plant) subtree is ~109k nodes. We therefore
     descend the taxonomy tree (``/children``) until every node we page is
     under a safe cap, then page each node.
  2. CoL China carries almost no Chinese vernacular names in the search index,
     so ``simplified_chinese_name`` is backfilled by matching scientific names
     against the iNat China pull we already have on disk.

Usage:

  # vascular plants (Flora of China scale, ~31.5k species)
  python scripts/algo_d/fetch_china_taxonomy_from_gbif.py --plants

  # ray-finned fish (FishBase scale)
  python scripts/algo_d/fetch_china_taxonomy_from_gbif.py --fish

  # arbitrary CoL China subtree
  python scripts/algo_d/fetch_china_taxonomy_from_gbif.py \
      --group reptiles --col-root-key 315103730

Requires only ``requests``; works on any machine, no GPU.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
RELEASE_DIR = SMP_DATA / "taxonomy_releases" / "taxonomy_full_release_2026_W2"
OUT_DIR_DEFAULT = RELEASE_DIR / "gbif_china_species"
INAT_DIR_DEFAULT = RELEASE_DIR / "inat_china_species"

GBIF_SPECIES_SEARCH = "https://api.gbif.org/v1/species/search"
GBIF_CHILDREN = "https://api.gbif.org/v1/species/{key}/children"
GBIF_DATASET_SEARCH = "https://api.gbif.org/v1/dataset/search"

# Catalogue of Life China 2023 Annual Checklist (discovered via dataset search).
COL_CHINA_2023 = "7e276a96-73ea-4efc-8ffb-e74ef573ef6c"
# Internal node keys inside that dataset (NOT GBIF backbone keys).
ROOT_TRACHEOPHYTA = 315117994   # vascular plants (Flora of China scope)
ROOT_ACTINOPTERYGII = 315103730  # ray-finned fish

USER_AGENT = "algo-d-research/1.0 (academic biodiversity catalog seeding)"
PAGE_LIMIT = 1000
OFFSET_CAP = 99000          # GBIF species/search hard limit is offset+limit <= 100000
SAFE_NODE_CAP = 90000       # page a node directly only if its subtree is <= this
RETRY_MAX = 6
RETRY_BASE_DELAY = 1.0
PAGE_WORKERS = 8
GLOBAL_PAGE_WORKERS = 12     # overlap slow/timeout calls across ALL nodes at once

ACCEPTED_STATUSES = {"ACCEPTED", "PROVISIONALLY_ACCEPTED"}


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def _get(sess: requests.Session, url: str, params: dict | None = None) -> dict | None:
    """GET with retries tolerant of GBIF's intermittent SSL/connection drops."""
    for attempt in range(1, RETRY_MAX + 1):
        try:
            r = sess.get(url, params=params, timeout=40)
        except requests.RequestException as exc:
            if attempt == RETRY_MAX:
                print(f"  [warn] giving up {url} after {attempt} tries: {type(exc).__name__}")
                return None
            time.sleep(RETRY_BASE_DELAY * attempt)
            continue
        if r.status_code == 200:
            try:
                return r.json()
            except ValueError:
                return None
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(RETRY_BASE_DELAY * attempt)
            continue
        print(f"  [warn] {url} HTTP {r.status_code}")
        return None
    return None


def col_count(sess: requests.Session, dataset: str, htk: int) -> int:
    j = _get(sess, GBIF_SPECIES_SEARCH,
             {"datasetKey": dataset, "highertaxonKey": htk, "limit": 0})
    return int((j or {}).get("count") or 0)


def col_children(sess: requests.Session, key: int) -> list[dict]:
    out: list[dict] = []
    offset = 0
    while True:
        j = _get(sess, GBIF_CHILDREN.format(key=key), {"limit": 100, "offset": offset})
        if not j:
            break
        out.extend(j.get("results", []))
        if j.get("endOfRecords", True):
            break
        offset += 100
    return out


def build_worklist(sess: requests.Session, dataset: str, root_key: int,
                   cap: int) -> list[tuple[int, int]]:
    """Descend the tree until every node is <= cap; return [(node_key, count)]."""
    worklist: list[tuple[int, int]] = []
    stack = [root_key]
    seen: set[int] = set()
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        cnt = col_count(sess, dataset, node)
        if cnt == 0:
            continue
        if cnt <= cap:
            worklist.append((node, cnt))
            print(f"  [pageable] node={node} count={cnt}")
            continue
        kids = col_children(sess, node)
        if not kids:
            # cannot descend further; page what we can (capped at OFFSET_CAP)
            worklist.append((node, min(cnt, OFFSET_CAP)))
            print(f"  [leaf>{cap}] node={node} count={cnt} (capped at {OFFSET_CAP})")
            continue
        print(f"  [descend ] node={node} count={cnt} -> {len(kids)} children")
        for k in kids:
            if k.get("key") is not None:
                stack.append(int(k["key"]))
    return worklist


def _fetch_page(sess: requests.Session, dataset: str, htk: int, offset: int) -> list[dict]:
    j = _get(sess, GBIF_SPECIES_SEARCH, {
        "datasetKey": dataset, "highertaxonKey": htk,
        "limit": PAGE_LIMIT, "offset": offset,
    })
    return (j or {}).get("results", []) or []


def page_node(sess: requests.Session, dataset: str, htk: int, count: int) -> list[dict]:
    total = min(count, OFFSET_CAP)
    pages = math.ceil(total / PAGE_LIMIT)
    offsets = [p * PAGE_LIMIT for p in range(pages) if p * PAGE_LIMIT < OFFSET_CAP]
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=PAGE_WORKERS) as ex:
        futs = {ex.submit(_fetch_page, sess, dataset, htk, off): off for off in offsets}
        for fut in as_completed(futs):
            results.extend(fut.result())
    return results


def build_page_tasks(worklist: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Flatten the worklist into individual (node_key, offset) page calls so a
    single global pool can overlap GBIF's slow/timeout responses across nodes."""
    tasks: list[tuple[int, int]] = []
    for node, cnt in worklist:
        total = min(cnt, OFFSET_CAP)
        for p in range(math.ceil(total / PAGE_LIMIT)):
            off = p * PAGE_LIMIT
            if off < OFFSET_CAP:
                tasks.append((node, off))
    return tasks


def is_species(rec: dict) -> bool:
    if rec.get("taxonomicStatus") not in ACCEPTED_STATUSES:
        return False
    canonical = (rec.get("canonicalName") or "").strip()
    parts = canonical.split()
    # accepted binomial = species rank (genus + specific epithet); drop genus,
    # higher ranks (1 token) and infraspecific (3+ tokens / hybrids).
    return len(parts) == 2 and parts[0][:1].isupper() and parts[1].islower()


def load_inat_zh(inat_dir: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not inat_dir.exists():
        return mapping
    for jf in inat_dir.glob("*.json"):
        if jf.name.startswith("_"):
            continue
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        for e in data.get("entries", []):
            sci = (e.get("scientific_name") or "").strip().lower()
            zh = (e.get("simplified_chinese_name") or "").strip()
            if sci and zh and sci not in mapping:
                mapping[sci] = zh
    return mapping


def resolve_dataset(sess: requests.Session, title_q: str) -> str | None:
    j = _get(sess, GBIF_DATASET_SEARCH, {"q": title_q, "type": "CHECKLIST", "limit": 5})
    for d in (j or {}).get("results", []):
        if "catalogue of life china" in (d.get("title") or "").lower():
            return d.get("key")
    res = (j or {}).get("results") or []
    return res[0].get("key") if res else None


def write_summary(out_dir: Path) -> None:
    rollup = []
    for jf in sorted(out_dir.glob("*.json")):
        if jf.name.startswith("_"):
            continue
        try:
            d = json.loads(jf.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        rollup.append({
            "group": d.get("group"),
            "fetched_count": d.get("fetched_count"),
            "zh_filled": d.get("zh_filled"),
            "out_path": str(jf),
        })
    summary = {
        "source": "gbif_col_china_2023_checklist",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "rollup": rollup,
    }
    (out_dir / "_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plants", action="store_true",
                    help="shortcut: vascular plants (Tracheophyta) -> vascular_plants_gbif")
    ap.add_argument("--fish", action="store_true",
                    help="shortcut: ray-finned fish (Actinopterygii) -> fish_gbif")
    ap.add_argument("--group", default=None, help="output group label / filename stem")
    ap.add_argument("--col-root-key", type=int, default=None,
                    help="CoL China internal node key to descend from")
    ap.add_argument("--dataset-key", default=COL_CHINA_2023)
    ap.add_argument("--cap", type=int, default=SAFE_NODE_CAP)
    ap.add_argument("--max-species", type=int, default=0,
                    help="optional cap on emitted species (0 = all)")
    ap.add_argument("--output-dir", default=str(OUT_DIR_DEFAULT))
    ap.add_argument("--inat-dir", default=str(INAT_DIR_DEFAULT))
    args = ap.parse_args()

    if args.plants:
        group = args.group or "vascular_plants_gbif"
        root_key = args.col_root_key or ROOT_TRACHEOPHYTA
    elif args.fish:
        group = args.group or "fish_gbif"
        root_key = args.col_root_key or ROOT_ACTINOPTERYGII
    else:
        if args.group is None or args.col_root_key is None:
            print("[FATAL] pass --plants / --fish, or both --group and --col-root-key")
            return 3
        group = args.group
        root_key = args.col_root_key

    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{group}.json"
    inat_dir = Path(args.inat_dir).resolve()

    sess = _session()

    print("=" * 72)
    print(" Algo-D :: fetch China taxonomy from GBIF (CoL China 2023 checklist)")
    print(f"  group        = {group}")
    print(f"  dataset      = {args.dataset_key}")
    print(f"  root_key     = {root_key}")
    print(f"  node cap     = {args.cap}")
    print(f"  output       = {out_path}")
    print("=" * 72)

    # Safety: if the hardcoded dataset key is stale, re-resolve by title.
    if col_count(sess, args.dataset_key, root_key) == 0 and not args.col_root_key:
        print("\n[!] root subtree empty; attempting dataset re-resolve by title...")
        dk = resolve_dataset(sess, "Catalogue of Life China")
        if dk and dk != args.dataset_key:
            print(f"    re-resolved dataset -> {dk} (was {args.dataset_key})")
            args.dataset_key = dk

    print("\n[1/4] building pageable worklist (descending tree under cap)...")
    worklist = build_worklist(sess, args.dataset_key, root_key, args.cap)
    total_nodes = sum(c for _, c in worklist)
    print(f"  -> {len(worklist)} pageable nodes, ~{total_nodes} raw records to scan")

    print("\n[2/4] paging all nodes via one global pool + filtering to species...")
    page_tasks = build_page_tasks(worklist)
    print(f"  -> {len(page_tasks)} page calls across {len(worklist)} nodes "
          f"(workers={GLOBAL_PAGE_WORKERS})")
    seen_names: set[str] = set()
    entries: list[dict] = []
    started = time.time()
    done_pages = 0
    with ThreadPoolExecutor(max_workers=GLOBAL_PAGE_WORKERS) as ex:
        futs = {
            ex.submit(_fetch_page, sess, args.dataset_key, node, off): (node, off)
            for (node, off) in page_tasks
        }
        for fut in as_completed(futs):
            done_pages += 1
            for rec in fut.result():
                if not is_species(rec):
                    continue
                canonical = rec["canonicalName"].strip()
                key = canonical.lower()
                if key in seen_names:
                    continue
                seen_names.add(key)
                entries.append({
                    "internal_taxon_id": f"gbif-{group}-{rec.get('key')}",
                    "scientific_name": canonical,
                    "simplified_chinese_name": "",
                    "english_common_name": "",
                    "group": group,
                    "gbif_species_key": rec.get("key"),
                    "gbif_kingdom": rec.get("kingdom", ""),
                    "gbif_phylum": rec.get("phylum", ""),
                    "gbif_class": rec.get("class", ""),
                    "gbif_order": rec.get("order", ""),
                    "gbif_family": rec.get("family", ""),
                    "gbif_taxonomic_status": rec.get("taxonomicStatus", ""),
                    "source": "col_china_2023",
                })
            if done_pages % 10 == 0 or done_pages == len(page_tasks):
                elapsed = time.time() - started
                print(f"  [pages {done_pages:>4}/{len(page_tasks)}] "
                      f"species={len(entries)} ({elapsed:.0f}s)")

    if args.max_species and len(entries) > args.max_species:
        entries = entries[: args.max_species]
        print(f"  trimmed to --max-species cap = {args.max_species}")

    print("\n[3/4] backfilling Chinese names from iNat China pull...")
    zh_map = load_inat_zh(inat_dir)
    zh_filled = 0
    for e in entries:
        zh = zh_map.get(e["scientific_name"].lower())
        if zh:
            e["simplified_chinese_name"] = zh
            zh_filled += 1
    print(f"  iNat zh dictionary = {len(zh_map)} names; filled {zh_filled}/{len(entries)}")

    print("\n[4/4] writing output...")
    out = {
        "source": "gbif_col_china_2023_checklist",
        "group": group,
        "dataset_key": args.dataset_key,
        "col_root_key": root_key,
        "country_scope": "China (CoL China 2023 national checklist)",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "fetched_count": len(entries),
        "zh_filled": zh_filled,
        "entries": entries,
    }
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    write_summary(out_dir)
    print("\nDONE.")
    print(f"  species written : {len(entries)}")
    print(f"  zh names filled : {zh_filled}")
    print(f"  output          : {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
