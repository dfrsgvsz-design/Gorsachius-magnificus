#!/usr/bin/env python3
"""Fetch eBird taxonomy and save locally for analysis + china_birds.json building."""
import json, urllib.request, sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "_ebird_taxonomy.json"
OUT_ZH = Path(__file__).resolve().parent / "_ebird_taxonomy_zh.json"

def fetch(locale="en"):
    url = f"https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json&cat=species&locale={locale}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 BirdPlatform/1.0"})
    resp = urllib.request.urlopen(req, timeout=60)
    return json.loads(resp.read())

print("Fetching eBird taxonomy (English)...")
data_en = fetch("en")
print(f"  Got {len(data_en)} species")
OUT.write_text(json.dumps(data_en, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"  Saved to {OUT}")

print("Fetching eBird taxonomy (Chinese)...")
data_zh = fetch("zh")
print(f"  Got {len(data_zh)} species")
OUT_ZH.write_text(json.dumps(data_zh, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"  Saved to {OUT_ZH}")

# Build mapping: speciesCode -> Chinese name
cn_map = {}
for sp in data_zh:
    code = sp.get("speciesCode", "")
    name = sp.get("comName", "")
    # Check if name has Chinese characters
    if any(ord(c) > 0x4e00 for c in name):
        cn_map[code] = name

print(f"\nSpecies with Chinese names: {len(cn_map)}")

# Analyze by order
from collections import Counter
order_counts = Counter()
order_cn_counts = Counter()
for sp in data_en:
    order = sp.get("order", "?")
    code = sp.get("speciesCode", "")
    order_counts[order] += 1
    if code in cn_map:
        order_cn_counts[order] += 1

print(f"\nOrder analysis (total / with Chinese name):")
for order in sorted(order_counts.keys()):
    total = order_counts[order]
    cn = order_cn_counts.get(order, 0)
    pct = cn / total * 100 if total else 0
    if cn > 0:
        print(f"  {order:30s}: {total:5d} total, {cn:4d} CN ({pct:.0f}%)")

# Save CN mapping
cn_map_path = Path(__file__).resolve().parent / "_ebird_cn_names.json"
cn_map_path.write_text(json.dumps(cn_map, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\nSaved CN name mapping to {cn_map_path}")
