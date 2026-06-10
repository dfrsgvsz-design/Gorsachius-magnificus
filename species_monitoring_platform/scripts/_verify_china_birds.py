#!/usr/bin/env python3
"""Verify china_birds.json after build."""
import json
from pathlib import Path

f = Path(__file__).resolve().parent.parent / "backend" / "data" / "china_birds.json"
d = json.loads(f.read_text(encoding="utf-8"))
sp = d["species"]

print(f"Version: {d['version']}")
print(f"Total field: {d['total']}")
print(f"Species count: {len(sp)}")

orders = set(s["order"] for s in sp if s.get("order"))
families = set(s["family"] for s in sp if s.get("family"))
print(f"Orders: {len(orders)}")
print(f"Families: {len(families)}")

prot1 = sum(1 for s in sp if s.get("protection") == "I")
prot2 = sum(1 for s in sp if s.get("protection") == "II")
print(f"Protection I: {prot1}, II: {prot2}")

nocn = sum(1 for s in sp if not s.get("chinese"))
noeng = sum(1 for s in sp if not s.get("english"))
print(f"Missing CN name: {nocn}")
print(f"Missing EN name: {noeng}")

# Order breakdown
from collections import Counter
order_counts = Counter(s.get("order", "?") for s in sp)
print("\n--- Order breakdown ---")
for o, c in order_counts.most_common():
    cn = next((s.get("order_cn", "") for s in sp if s.get("order") == o), "")
    print(f"  {o} ({cn}): {c}")

# Sample: Gorsachius
print("\n--- Gorsachius magnificus ---")
gm = [s for s in sp if "Gorsachius" in s.get("scientific", "")]
for s in gm:
    print(json.dumps(s, ensure_ascii=False, indent=2))

# Check for duplicates
sci_names = [s["scientific"] for s in sp]
dupes = [n for n in set(sci_names) if sci_names.count(n) > 1]
if dupes:
    print(f"\nWARNING: {len(dupes)} duplicate scientific names!")
    for d in dupes[:10]:
        print(f"  {d}")
else:
    print(f"\nNo duplicate scientific names.")
