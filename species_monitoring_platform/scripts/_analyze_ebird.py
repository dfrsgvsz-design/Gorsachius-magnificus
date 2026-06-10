#!/usr/bin/env python3
"""Analyze eBird taxonomy data to understand China species coverage."""
import json
from pathlib import Path
from collections import Counter

base = Path(__file__).resolve().parent
en = json.loads((base / "_ebird_taxonomy.json").read_text(encoding="utf-8"))
zh = json.loads((base / "_ebird_taxonomy_zh.json").read_text(encoding="utf-8"))

# Build code->Chinese name map (only entries with actual Chinese chars)
cn_map = {}
for s in zh:
    name = s.get("comName", "")
    if any(ord(c) > 0x4E00 for c in name):
        cn_map[s["speciesCode"]] = name

# Show Galliformes species with Chinese names
print("=== Galliformes with CN names ===")
for s in en:
    if s.get("order") == "Galliformes" and s["speciesCode"] in cn_map:
        print(f"  {s['sciName']:40s} {cn_map[s['speciesCode']]}")

# Show Accipitriformes with CN names
print("\n=== Accipitriformes with CN names ===")
for s in en:
    if s.get("order") == "Accipitriformes" and s["speciesCode"] in cn_map:
        print(f"  {s['sciName']:40s} {cn_map[s['speciesCode']]}")

# Show Strigiformes with CN names
print("\n=== Strigiformes with CN names ===")
for s in en:
    if s.get("order") == "Strigiformes" and s["speciesCode"] in cn_map:
        print(f"  {s['sciName']:40s} {cn_map[s['speciesCode']]}")

# Passeriformes families with CN species count
print("\n=== Passeriformes families (CN/total) ===")
fam_total = Counter()
fam_cn = Counter()
for s in en:
    if s.get("order") != "Passeriformes":
        continue
    fam = s.get("familySciName", "?")
    fam_total[fam] += 1
    if s["speciesCode"] in cn_map:
        fam_cn[fam] += 1
for fam in sorted(fam_total.keys()):
    cn = fam_cn.get(fam, 0)
    tot = fam_total[fam]
    if cn > 0:
        print(f"  {fam:35s}: {cn:3d}/{tot:4d}")

# Summary: all CN species by order
print("\n=== All CN-named species by order ===")
cn_species_by_order = {}
for s in en:
    if s["speciesCode"] in cn_map:
        order = s.get("order", "?")
        cn_species_by_order.setdefault(order, []).append(s["sciName"])
for order in sorted(cn_species_by_order.keys()):
    print(f"  {order}: {len(cn_species_by_order[order])} species")

# Save all CN-named scientific names for reference
cn_sci_names = set()
for s in en:
    if s["speciesCode"] in cn_map:
        cn_sci_names.add(s["sciName"])
print(f"\nTotal unique CN-named species: {len(cn_sci_names)}")

# Save to file for reference
(base / "_ebird_china_base.txt").write_text(
    "\n".join(sorted(cn_sci_names)), encoding="utf-8"
)
print(f"Saved to _ebird_china_base.txt")
