"""Quick audio quality check on expanded dataset."""
import json
import os
import sys
from pathlib import Path
from collections import Counter

MANIFEST = Path(__file__).parent.parent / "data" / "xc_expanded" / "manifest.json"

def main():
    data = json.load(open(MANIFEST, "r", encoding="utf-8"))
    print(f"Manifest entries: {len(data)}")

    missing = 0
    tiny = 0       # < 1KB
    small = 0      # < 10KB
    ok = 0
    sizes = []
    bad_entries = []

    for item in data:
        fp = item.get("file_path", "")
        if not fp or not os.path.exists(fp):
            missing += 1
            bad_entries.append(("MISSING", fp, item.get("species_scientific", "")))
            continue
        sz = os.path.getsize(fp)
        sizes.append(sz)
        if sz < 1000:
            tiny += 1
            bad_entries.append(("TINY", fp, item.get("species_scientific", ""), sz))
        elif sz < 10000:
            small += 1
        else:
            ok += 1

    print(f"\nFile status:")
    print(f"  OK (>=10KB):    {ok}")
    print(f"  Small (1-10KB): {small}")
    print(f"  Tiny (<1KB):    {tiny}")
    print(f"  Missing:        {missing}")

    if sizes:
        sizes.sort()
        total_mb = sum(sizes) / 1024 / 1024
        print(f"\nSize stats:")
        print(f"  Total:  {total_mb:.1f} MB")
        print(f"  Min:    {sizes[0]:,} bytes")
        print(f"  Max:    {sizes[-1]:,} bytes")
        print(f"  Median: {sizes[len(sizes)//2]:,} bytes")
        print(f"  Mean:   {sum(sizes)//len(sizes):,} bytes")

    if bad_entries:
        print(f"\nBad entries ({len(bad_entries)}):")
        for entry in bad_entries[:20]:
            print(f"  {entry}")

    # Check for duplicates
    paths = [item.get("file_path", "") for item in data]
    dupes = [p for p, c in Counter(paths).items() if c > 1]
    if dupes:
        print(f"\nDuplicate paths: {len(dupes)}")
        for d in dupes[:10]:
            print(f"  {d}")

    # Try loading a few with librosa
    try:
        import librosa
        print("\nLibrosa load test (5 random samples)...")
        import random
        valid = [item for item in data if os.path.exists(item.get("file_path", "")) and os.path.getsize(item.get("file_path", "")) > 10000]
        samples = random.sample(valid, min(5, len(valid)))
        for item in samples:
            fp = item["file_path"]
            try:
                y, sr = librosa.load(fp, sr=22050, duration=5.0)
                dur = len(y) / sr
                print(f"  OK: {Path(fp).name} ({dur:.1f}s, sr={sr})")
            except Exception as e:
                print(f"  FAIL: {Path(fp).name} — {e}")
    except ImportError:
        print("\nlibrosa not available for load test")

    # Species distribution after removing bad entries
    sp_counts = Counter()
    for item in data:
        fp = item.get("file_path", "")
        if fp and os.path.exists(fp) and os.path.getsize(fp) >= 1000:
            sp_counts[item["species_scientific"]] += 1
    
    usable = sum(sp_counts.values())
    print(f"\nUsable recordings (>=1KB, exists): {usable}")
    print(f"Usable species: {len(sp_counts)}")
    
    counts = sorted(sp_counts.values())
    if counts:
        print(f"Per-species min/max/mean: {counts[0]}/{counts[-1]}/{sum(counts)/len(counts):.1f}")

if __name__ == "__main__":
    main()
