#!/usr/bin/env python3
"""Fix empty order/english fields in china_birds.json by genus lookup."""
import json
from pathlib import Path

f = Path(__file__).resolve().parent.parent / "backend" / "data" / "china_birds.json"
d = json.loads(f.read_text(encoding="utf-8"))
sp = d["species"]

# Build genus→(order, family, order_cn, family_cn) from species that HAVE order
genus_map = {}
for s in sp:
    g = s.get("genus", "")
    o = s.get("order", "")
    if g and o:
        genus_map[g] = (o, s.get("family",""), s.get("order_cn",""), s.get("family_cn",""))

# Fix empty orders
fixed_order = 0
for s in sp:
    if not s.get("order") and s.get("genus") in genus_map:
        o, fam, ocn, fcn = genus_map[s["genus"]]
        s["order"] = o
        s["family"] = s.get("family") or fam
        s["order_cn"] = s.get("order_cn") or ocn
        s["family_cn"] = s.get("family_cn") or fcn
        fixed_order += 1

# Count remaining issues
no_order = sum(1 for s in sp if not s.get("order"))
no_eng = sum(1 for s in sp if not s.get("english"))
print(f"Fixed order: {fixed_order}")
print(f"Still no order: {no_order}")
print(f"Still no english: {no_eng}")

if no_order:
    for s in sp:
        if not s.get("order"):
            print(f"  {s['scientific']} ({s.get('chinese','')})")

d["species"] = sp
f.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\nWrote: {f} ({f.stat().st_size // 1024}KB)")
