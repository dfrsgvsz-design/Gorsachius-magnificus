"""Quick probe: how many recordings does Xeno-canto actually have per species?"""
import os
import sys, time, requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
from species_db import get_species_db

API_KEY = os.environ.get("XC_API_KEY", "").strip()
BASE_URL = "https://xeno-canto.org/api/3/recordings"

if not API_KEY:
    raise SystemExit("XC_API_KEY is required to run this script.")

def probe(scientific_name):
    query = f'sp:"{scientific_name}" grp:birds'
    try:
        resp = requests.get(BASE_URL, params={"query": query, "key": API_KEY}, timeout=20)
        data = resp.json()
        total = int(data.get("numRecordings", 0))
        recs = data.get("recordings", [])
        downloadable = sum(1 for r in recs if r.get("file", ""))
        page_size = len(recs)
        num_pages = int(data.get("numPages", 1))
        return total, downloadable, page_size, num_pages
    except Exception as e:
        return 0, 0, 0, 0

# Test a mix of species
test_species = [
    "Pycnonotus sinensis",      # common, should have many
    "Turdus merula",            # very common globally
    "Gorsachius magnificus",    # rare, target species
    "Ciconia boyciana",         # rare
    "Zoothera dauma",           # moderate
    "Urocissa erythroryncha",   # common in China
    "Phoenicurus auroreus",     # common
    "Tragopan caboti",          # rare endemic
    "Nipponia nippon",          # critically endangered
    "Leiothrix lutea",          # common
]

print("Xeno-canto v3 API Capacity Probe")
print("=" * 70)
print(f"{'Species':<30} {'Total':>6} {'DL(p1)':>7} {'PageSz':>7} {'Pages':>6}")
print("-" * 70)

for sp in test_species:
    total, dl, ps, pages = probe(sp)
    print(f"{sp:<30} {total:>6} {dl:>7} {ps:>7} {pages:>6}")
    time.sleep(1.0)

# Also check: how many of the 251 species have >50 recordings on XC?
print("\n\nFull species scan (count only, no download)...")
print("=" * 70)

db = get_species_db()
all_sp = [s for s in db.all_species if s.get("has_audio", False)]

buckets = {"0": 0, "1-10": 0, "11-50": 0, "51-100": 0, "101-200": 0, "200+": 0}
species_totals = []

for i, sp in enumerate(all_sp):
    sci = sp["scientific"]
    total, dl, ps, pages = probe(sci)
    species_totals.append((sci, sp["chinese"], total, dl, pages))
    
    if total == 0: buckets["0"] += 1
    elif total <= 10: buckets["1-10"] += 1
    elif total <= 50: buckets["11-50"] += 1
    elif total <= 100: buckets["51-100"] += 1
    elif total <= 200: buckets["101-200"] += 1
    else: buckets["200+"] += 1
    
    if (i + 1) % 25 == 0:
        print(f"  Scanned {i+1}/{len(all_sp)}...")
    time.sleep(0.8)

print(f"\nXC Recording Distribution ({len(all_sp)} species):")
for k, v in buckets.items():
    print(f"  {k:>8} recordings: {v} species")

total_available = sum(t[2] for t in species_totals)
print(f"\nTotal recordings on XC: {total_available}")

# Show species with most recordings
species_totals.sort(key=lambda x: x[2], reverse=True)
print(f"\nTop 20 (most recordings):")
for sci, cn, total, dl, pages in species_totals[:20]:
    print(f"  {cn} ({sci}): {total} total, {dl} DL on page1, {pages} pages")

print(f"\nBottom 20 (fewest recordings):")
for sci, cn, total, dl, pages in species_totals[-20:]:
    print(f"  {cn} ({sci}): {total} total, {dl} DL on page1, {pages} pages")
