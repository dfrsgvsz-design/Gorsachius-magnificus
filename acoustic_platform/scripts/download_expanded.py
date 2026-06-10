"""
Expanded Bird Sound Download — 从Xeno-canto下载中国鸟类录音用于训练。

策略:
1. 先扫描所有物种，识别哪些在API中有下载链接
2. 批量下载有链接的物种录音 (每种最多50条)
3. 合并现有 xc_china/ 数据集
4. 输出统一manifest.json用于训练

已知限制: v3 API约50%物种返回file URL，其余返回空串。
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
from species_db import get_species_db

# ──────────────────── Config ────────────────────
API_KEY = os.environ.get("XC_API_KEY", "").strip()
BASE_URL = "https://xeno-canto.org/api/3/recordings"
DATA_DIR = Path(__file__).parent.parent / "data" / "xc_expanded"
OLD_DATA_DIR = Path(__file__).parent.parent / "data" / "xc_china"
MAX_PER_SPECIES = 100
REQUEST_DELAY = 0.8
DOWNLOAD_DELAY = 0.2

if not API_KEY:
    raise SystemExit("XC_API_KEY is required to run this script.")


def search_species(scientific_name: str, page: int = 1) -> dict:
    """Search Xeno-canto v3 API. Returns raw response data."""
    query = f'sp:"{scientific_name}" grp:birds'
    params = {"query": query, "key": API_KEY, "page": page}
    try:
        resp = requests.get(BASE_URL, params=params, timeout=30)
        if resp.status_code != 200:
            return {"recordings": [], "numRecordings": "0"}
        return resp.json()
    except Exception as e:
        print(f"    API error: {e}")
        return {"recordings": [], "numRecordings": "0"}


def get_downloadable(scientific_name: str, max_results: int = 150) -> list:
    """Get recordings with valid file URLs, trying multiple pages."""
    results = []
    for page in range(1, 7):  # try up to 6 pages
        data = search_species(scientific_name, page=page)
        recs = data.get("recordings", [])
        if not recs:
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

        # If first page has 0 file URLs, don't bother with more pages
        if page == 1 and len(results) == 0:
            break
        if len(results) >= max_results:
            break
        time.sleep(REQUEST_DELAY)

    # Sort by quality
    quality_order = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}
    results.sort(key=lambda r: quality_order.get(r["quality"], 5))
    return results[:max_results]


def download_file(url: str, filepath: Path) -> bool:
    """Download a recording file."""
    try:
        resp = requests.get(url, params={"key": API_KEY}, timeout=60, stream=True)
        if resp.status_code != 200:
            return False
        ct = resp.headers.get("content-type", "")
        if "html" in ct.lower():
            return False
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return filepath.stat().st_size > 1000
    except Exception:
        if filepath.exists():
            filepath.unlink()
        return False


def merge_old_data(manifest: list, manifest_set: set) -> int:
    """Merge existing xc_china/ recordings into manifest."""
    old_manifest = OLD_DATA_DIR / "manifest.json"
    if not old_manifest.exists():
        return 0
    added = 0
    old_items = json.load(open(old_manifest, "r", encoding="utf-8"))
    for item in old_items:
        fp = item.get("file_path", "")
        if fp and fp not in manifest_set and Path(fp).exists():
            manifest.append(item)
            manifest_set.add(fp)
            added += 1
    return added


def main():
    db = get_species_db()
    all_species = [sp for sp in db.all_species if sp.get("has_audio", False)]
    print(f"Target species: {len(all_species)}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing expanded manifest
    manifest_path = DATA_DIR / "manifest.json"
    manifest = []
    manifest_set = set()  # file_path dedup
    species_counts = defaultdict(int)

    if manifest_path.exists():
        try:
            manifest = json.load(open(manifest_path, "r", encoding="utf-8"))
            for item in manifest:
                manifest_set.add(item.get("file_path", ""))
                species_counts[item["species_scientific"]] += 1
            print(f"Existing: {len(manifest)} recordings, {len(species_counts)} species")
        except Exception:
            manifest = []

    # Merge old xc_china/ data first
    old_count_before = len(manifest)
    merged = merge_old_data(manifest, manifest_set)
    if merged > 0:
        for item in manifest[old_count_before:]:
            species_counts[item["species_scientific"]] += 1
        print(f"Merged {merged} recordings from xc_china/")

    stats = {"downloaded": 0, "failed": 0, "no_api_files": 0, "skipped": 0, "success": 0}

    for idx, sp in enumerate(all_species):
        scientific = sp["scientific"]
        chinese = sp["chinese"]
        have = species_counts.get(scientific, 0)
        needed = MAX_PER_SPECIES - have

        if needed <= 0:
            stats["skipped"] += 1
            continue

        print(f"[{idx+1}/{len(all_species)}] {chinese} ({scientific}) "
              f"— have {have}, need {needed}")

        recordings = get_downloadable(scientific, max_results=needed * 2)
        time.sleep(REQUEST_DELAY)

        if not recordings:
            stats["no_api_files"] += 1
            print(f"  ✗ No file URLs from API")
            continue

        sp_dir = DATA_DIR / scientific.replace(" ", "_")
        sp_dir.mkdir(parents=True, exist_ok=True)

        downloaded = 0
        for rec in recordings:
            if downloaded >= needed:
                break
            rec_id = rec["id"]
            file_url = rec["file_url"]
            ext = ".mp3"
            filepath = sp_dir / f"XC{rec_id}{ext}"

            if str(filepath) in manifest_set:
                downloaded += 1
                continue

            if filepath.exists() and filepath.stat().st_size > 1000:
                # File exists but not in manifest — add it
                manifest.append({
                    "file_path": str(filepath),
                    "species_scientific": scientific,
                    "species_chinese": chinese,
                    "species_english": sp.get("english", ""),
                    "xc_id": rec_id,
                    "quality": rec.get("quality", ""),
                    "country": rec.get("country", ""),
                })
                manifest_set.add(str(filepath))
                species_counts[scientific] += 1
                downloaded += 1
                continue

            ok = download_file(file_url, filepath)
            time.sleep(DOWNLOAD_DELAY)

            if ok:
                downloaded += 1
                stats["downloaded"] += 1
                manifest.append({
                    "file_path": str(filepath),
                    "species_scientific": scientific,
                    "species_chinese": chinese,
                    "species_english": sp.get("english", ""),
                    "xc_id": rec_id,
                    "quality": rec.get("quality", ""),
                    "country": rec.get("country", ""),
                })
                manifest_set.add(str(filepath))
                species_counts[scientific] += 1
            else:
                stats["failed"] += 1

        if downloaded > 0:
            stats["success"] += 1
            print(f"  ✓ {downloaded} recordings")
        else:
            print(f"  ✗ All downloads failed")

        # Checkpoint every 10 species
        if (idx + 1) % 10 == 0:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            sp_done = len([c for c in species_counts.values() if c > 0])
            print(f"  📦 Checkpoint: {len(manifest)} recordings, {sp_done} species")

    # Final save
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    # Summary
    final_counts = sorted(species_counts.values())
    sp_with_data = len([c for c in final_counts if c > 0])

    print(f"\n{'='*60}")
    print(f"Download Complete!")
    print(f"{'='*60}")
    print(f"Total recordings:    {len(manifest)}")
    print(f"Species with data:   {sp_with_data}")
    print(f"New downloads:       {stats['downloaded']}")
    print(f"Download failures:   {stats['failed']}")
    print(f"No API file URLs:    {stats['no_api_files']}")
    print(f"Already sufficient:  {stats['skipped']}")
    if final_counts:
        print(f"Per-species:  min={final_counts[0]} max={final_counts[-1]} "
              f"median={final_counts[len(final_counts)//2]} "
              f"mean={sum(final_counts)/len(final_counts):.1f}")
    print(f"\nManifest: {manifest_path}")


if __name__ == "__main__":
    main()
