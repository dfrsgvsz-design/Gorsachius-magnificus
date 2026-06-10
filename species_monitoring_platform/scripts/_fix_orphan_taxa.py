#!/usr/bin/env python3
"""Fix 22 orphan species with missing order by manual taxonomy mapping."""
import json
from pathlib import Path

f = Path(__file__).resolve().parent.parent / "backend" / "data" / "china_birds.json"
d = json.loads(f.read_text(encoding="utf-8"))
sp = d["species"]

# Manual fixes: scientific_name → (order, family)
FIXES = {
    "Anthropoides virgo": ("Gruiformes", "Gruidae"),
    "Chleuasicus atrosuperciliaris": ("Passeriformes", "Paradoxornithidae"),
    "Cholornis unicolor": ("Passeriformes", "Paradoxornithidae"),
    "Conostoma aemodium": ("Passeriformes", "Paradoxornithidae"),
    "Cristemberiza elegans": ("Passeriformes", "Emberizidae"),
    "Granativora koslowi": ("Passeriformes", "Emberizidae"),
    "Latoucheornis siemsseni": ("Passeriformes", "Emberizidae"),
    "Melophus lathami": ("Passeriformes", "Emberizidae"),
    "Rhyacornis fuliginosa": ("Passeriformes", "Muscicapidae"),
    "Rimator malacoptilus": ("Passeriformes", "Pellorneidae"),
    "Saxicoloides fulicatus": ("Passeriformes", "Muscicapidae"),
    "Seicercus affinis": ("Passeriformes", "Phylloscopidae"),
    "Seicercus burkii": ("Passeriformes", "Phylloscopidae"),
    "Seicercus castaniceps": ("Passeriformes", "Phylloscopidae"),
    "Seicercus omeiensis": ("Passeriformes", "Phylloscopidae"),
    "Seicercus soror": ("Passeriformes", "Phylloscopidae"),
    "Seicercus valentini": ("Passeriformes", "Phylloscopidae"),
    "Seicercus whistleri": ("Passeriformes", "Phylloscopidae"),
    "Sinosuthora conspicillata": ("Passeriformes", "Paradoxornithidae"),
    "Sinosuthora webbiana": ("Passeriformes", "Paradoxornithidae"),
    "Stachyridopsis ruficeps": ("Passeriformes", "Timaliidae"),
    "Stachyridopsis rufifrons": ("Passeriformes", "Timaliidae"),
}

ORDER_CN = {
    "Gruiformes":"鹤形目","Passeriformes":"雀形目",
}
FAMILY_CN = {
    "Gruidae":"鹤科","Paradoxornithidae":"鸦雀科","Emberizidae":"鹀科",
    "Muscicapidae":"鹟科","Pellorneidae":"幽鹛科","Phylloscopidae":"柳莺科",
    "Timaliidae":"雀鹛科",
}

fixed = 0
for s in sp:
    sci = s.get("scientific", "")
    if sci in FIXES:
        order, family = FIXES[sci]
        s["order"] = order
        s["family"] = family
        s["order_cn"] = ORDER_CN.get(order, order)
        s["family_cn"] = FAMILY_CN.get(family, family)
        fixed += 1

# Verify
no_order = sum(1 for s in sp if not s.get("order"))
print(f"Fixed: {fixed}")
print(f"Remaining without order: {no_order}")

d["species"] = sp
f.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Wrote: {f} ({f.stat().st_size // 1024}KB)")
