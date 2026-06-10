#!/usr/bin/env python3
"""
Build china_birds.json from eBird taxonomy + embedded supplementary data.

Usage:
    python scripts/build_china_birds_v2.py
    python scripts/build_china_birds_v2.py --ebird-cache scripts/
"""
import argparse, json, sys
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

BACKEND_DATA = Path(__file__).resolve().parent.parent / "backend" / "data"
OUTPUT_FILE = BACKEND_DATA / "china_birds.json"
SCRIPTS_DIR = Path(__file__).resolve().parent

# Import supplementary data
sys.path.insert(0, str(SCRIPTS_DIR))
from _china_supp_data import SUPP_SPECIES, CHINESE_NAMES_MAP, PROTECTION_MAP

ORDER_CN = {
    "Galliformes":"鸡形目","Anseriformes":"雁形目","Podicipediformes":"鸊鷉目",
    "Phoenicopteriformes":"火烈鸟目","Columbiformes":"鸽形目","Pterocliformes":"沙鸡目",
    "Otidiformes":"鸨目","Cuculiformes":"鹃形目","Caprimulgiformes":"夜鹰目",
    "Apodiformes":"雨燕目","Gruiformes":"鹤形目","Charadriiformes":"鸻形目",
    "Gaviiformes":"潜鸟目","Procellariiformes":"鹱形目","Phaethontiformes":"鹲目",
    "Ciconiiformes":"鹳形目","Suliformes":"鲣鸟目","Pelecaniformes":"鹈形目",
    "Accipitriformes":"鹰形目","Strigiformes":"鸮形目","Bucerotiformes":"犀鸟目",
    "Trogoniformes":"咬鹃目","Coraciiformes":"佛法僧目","Piciformes":"鴷形目",
    "Falconiformes":"隼形目","Psittaciformes":"鹦鹉目","Passeriformes":"雀形目",
}

FAMILY_CN = {
    "Phasianidae":"雉科","Anatidae":"鸭科","Podicipedidae":"鸊鷉科",
    "Phoenicopteridae":"火烈鸟科","Columbidae":"鸠鸽科","Pteroclidae":"沙鸡科",
    "Otididae":"鸨科","Cuculidae":"杜鹃科","Caprimulgidae":"夜鹰科",
    "Apodidae":"雨燕科","Hemiprocnidae":"凤头雨燕科","Rallidae":"秧鸡科",
    "Gruidae":"鹤科","Burhinidae":"石鸻科","Haematopodidae":"蛎鹬科",
    "Ibidorhynchidae":"鹮嘴鹬科","Recurvirostridae":"反嘴鹬科","Charadriidae":"鸻科",
    "Scolopacidae":"鹬科","Turnicidae":"三趾鹑科","Glareolidae":"燕鸻科",
    "Laridae":"鸥科","Stercorariidae":"贼鸥科","Alcidae":"海雀科",
    "Gaviidae":"潜鸟科","Diomedeidae":"信天翁科","Procellariidae":"鹱科",
    "Hydrobatidae":"海燕科","Oceanitidae":"洋海燕科","Phaethontidae":"鹲科",
    "Ciconiidae":"鹳科","Fregatidae":"军舰鸟科","Sulidae":"鲣鸟科",
    "Anhingidae":"蛇鹈科","Phalacrocoracidae":"鸬鹚科","Pelecanidae":"鹈鹕科",
    "Ardeidae":"鹭科","Threskiornithidae":"鹮科","Pandionidae":"鹗科",
    "Accipitridae":"鹰科","Tytonidae":"草鸮科","Strigidae":"鸱鸮科",
    "Bucerotidae":"犀鸟科","Upupidae":"戴胜科","Trogonidae":"咬鹃科",
    "Coraciidae":"佛法僧科","Alcedinidae":"翠鸟科","Meropidae":"蜂虎科",
    "Indicatoridae":"响蜜鴷科","Picidae":"啄木鸟科","Megalaimidae":"拟啄木鸟科",
    "Falconidae":"隼科","Psittaculidae":"鹦鹉科","Psittacidae":"鹦鹉科",
    "Pittidae":"八色鸫科","Eurylaimidae":"阔嘴鸟科","Campephagidae":"山椒鸟科",
    "Oriolidae":"黄鹂科","Artamidae":"燕鵙科","Aegithinidae":"雀鹎科",
    "Vangidae":"钩嘴鵙科","Tephrodornithidae":"钩嘴鵙科","Laniidae":"伯劳科",
    "Corvidae":"鸦科","Stenostiridae":"仙鹟科","Dicruridae":"卷尾科",
    "Monarchidae":"王鹟科","Rhipiduridae":"扇尾鹟科","Paridae":"山雀科",
    "Remizidae":"攀雀科","Alaudidae":"百灵科","Pycnonotidae":"鹎科",
    "Hirundinidae":"燕科","Cettiidae":"树莺科","Aegithalidae":"长尾山雀科",
    "Phylloscopidae":"柳莺科","Acrocephalidae":"苇莺科","Locustellidae":"蝗莺科",
    "Cisticolidae":"扇尾莺科","Sylviidae":"莺科","Paradoxornithidae":"鸦雀科",
    "Zosteropidae":"绣眼鸟科","Timaliidae":"雀鹛科","Leiothrichidae":"噪鹛科",
    "Pellorneidae":"幽鹛科","Alcippeidae":"雀鹛科","Elachuridae":"丽鹛科",
    "Sittidae":"鳾科","Tichodromidae":"旋壁雀科","Certhiidae":"旋木雀科",
    "Troglodytidae":"鹪鹩科","Cinclidae":"河乌科","Sturnidae":"椋鸟科",
    "Turdidae":"鸫科","Muscicapidae":"鹟科","Regulidae":"戴菊科",
    "Bombycillidae":"太平鸟科","Prunellidae":"岩鹨科","Passeridae":"麻雀科",
    "Ploceidae":"织雀科","Estrildidae":"梅花雀科","Motacillidae":"鹡鸰科",
    "Fringillidae":"雀科","Emberizidae":"鹀科","Calcariidae":"铁爪鹀科",
    "Nectariniidae":"太阳鸟科","Dicaeidae":"啄花鸟科","Chloropseidae":"叶鹎科",
    "Irenidae":"和平鸟科","Vireonidae":"绿鹃科","Scotocercidae":"鹟莺科",
    "Pnoepygidae":"鳞胸鹪鹛科","Pachycephalidae":"啸鹟科",
}

# Traditional → Simplified Chinese character mapping for bird names
T2S = str.maketrans(
    "鷲鶹鴞鷹鷗鷺鷦鷯鶇鶲鶯鸝鵑鵜鶘鴿鶴鷸鴨鵝鶺鴒鵐鶚鷂鵟鴴鸕鶿鳽鵯鶥鵖鶻鷿鸊鷉鵰鴝鶪鵙鶖鶓鷥鴉鶩鷊鸌鷄鷓鶉鶡鷴鶤鷳鸇鷂鶎鵂鴗鵑鶬鸜鵲鴃鶺鶼鵪鶆鴷鸋鶠鸏鵀鶵鷳鸂鶒鷦鷯鸒鸑鴝鶙鷳鷂鷳鶻",
    "鹫鹠鸮鹰鸥鹭鹪鹩鸫鹟莺鹂鹃鹈鹕鸽鹤鹬鸭鹅鹡鸰鹀鹗鹞鵟鸻鸬鹚鳽鹎鶥鹇鹘鷿鸊鷉雕鸲鶪鵙鹮鸵鹭鸦鹜鸬鸌鸡鹧鹑鸮鹇鹍鹇鹯鹞鹎鸺鴗鹃鸧鸜鹊鴃鹡鹣鹌鹆鴷鸋鹠鸏鹁鹱鹇鸂鶒鹪鹩鸒鸑鸲鹪鹇鹞鹇鹘"
)

def t2s(text):
    """Convert Traditional Chinese to Simplified (best-effort for bird names)."""
    if not text:
        return text
    # Use mapping for known characters, pass through unknown
    result = text.translate(T2S)
    return result


def fetch_ebird(locale="en", cache_dir=None):
    """Fetch eBird taxonomy, with optional caching."""
    cache_file = None
    if cache_dir:
        cache_file = Path(cache_dir) / f"_ebird_taxonomy_{locale}.json"
        if cache_file.exists():
            print(f"  Loading cached {locale}: {cache_file}")
            return json.loads(cache_file.read_text(encoding="utf-8"))

    url = f"https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json&cat=species&locale={locale}"
    print(f"  Fetching eBird taxonomy ({locale})...")
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 BirdPlatform/1.0"})
    resp = urlopen(req, timeout=60)
    data = json.loads(resp.read())
    print(f"    Got {len(data)} species")

    if cache_file:
        cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def build_ebird_china_set(ebird_en, ebird_zh):
    """Extract China species from eBird using Chinese name presence."""
    # Build code→Chinese name map (only real Chinese characters)
    cn_map = {}
    for s in ebird_zh:
        name = s.get("comName", "")
        if any(ord(c) > 0x4E00 for c in name):
            cn_map[s["speciesCode"]] = name

    # Build code→full entry map
    en_map = {s["speciesCode"]: s for s in ebird_en}

    china_species = []
    for code, cn_name in cn_map.items():
        if code not in en_map:
            continue
        sp = en_map[code]
        sci = sp.get("sciName", "")
        eng = sp.get("comName", "")
        order = sp.get("order", "")
        family = sp.get("familySciName", "")
        genus = sci.split()[0] if sci else ""

        # Convert Traditional Chinese to Simplified
        cn_simplified = t2s(cn_name)
        # Check if we have a better name in our mapping
        if sci in CHINESE_NAMES_MAP:
            cn_simplified = CHINESE_NAMES_MAP[sci]

        entry = {
            "scientific": sci,
            "chinese": cn_simplified,
            "english": eng,
            "order": order,
            "order_cn": ORDER_CN.get(order, order),
            "family": family,
            "family_cn": FAMILY_CN.get(family, family),
            "genus": genus,
            "iucn": "LC",
            "protection": PROTECTION_MAP.get(sci),
            "resident": "resident",
            "has_audio": False,
        }
        china_species.append(entry)

    print(f"  eBird China species (with CN names): {len(china_species)}")
    return china_species


def build_supp_species(ebird_en):
    """Build entries for supplementary species not covered by eBird Chinese names."""
    en_map = {s["sciName"]: s for s in ebird_en}
    supp_entries = []
    found_in_ebird = 0
    not_in_ebird = 0

    for sci, cn in SUPP_SPECIES:
        entry_data = en_map.get(sci)
        if entry_data:
            found_in_ebird += 1
            order = entry_data.get("order", "")
            family = entry_data.get("familySciName", "")
            eng = entry_data.get("comName", "")
        else:
            not_in_ebird += 1
            genus = sci.split()[0] if sci else ""
            # Try to infer order/family from genus in ebird data
            order, family, eng = "", "", ""
            for s in ebird_en:
                if s["sciName"].startswith(genus + " "):
                    order = s.get("order", "")
                    family = s.get("familySciName", "")
                    break

        genus = sci.split()[0] if sci else ""
        supp_entries.append({
            "scientific": sci,
            "chinese": cn,
            "english": eng,
            "order": order,
            "order_cn": ORDER_CN.get(order, order),
            "family": family,
            "family_cn": FAMILY_CN.get(family, family),
            "genus": genus,
            "iucn": "LC",
            "protection": PROTECTION_MAP.get(sci),
            "resident": "resident",
            "has_audio": False,
        })

    print(f"  Supplementary: {len(supp_entries)} ({found_in_ebird} in eBird, {not_in_ebird} not)")
    return supp_entries


def merge_all(existing, ebird_china, supp):
    """Merge all sources. Existing entries take priority for field values."""
    by_sci = {}
    # 1. Supplementary (lowest priority)
    for e in supp:
        sci = e.get("scientific", "")
        if sci:
            by_sci[sci] = e
    # 2. eBird (medium priority)
    for e in ebird_china:
        sci = e.get("scientific", "")
        if not sci:
            continue
        if sci in by_sci:
            base = by_sci[sci]
            for k, v in e.items():
                if v not in (None, "", [], False) and (k not in base or base[k] in (None, "", [])):
                    base[k] = v
        else:
            by_sci[sci] = e
    # 3. Existing (highest priority)
    for e in existing:
        sci = e.get("scientific", "")
        if not sci:
            continue
        if sci in by_sci:
            base = by_sci[sci]
            for k, v in e.items():
                if v not in (None, "", []):
                    base[k] = v
        else:
            by_sci[sci] = e

    result = sorted(by_sci.values(),
                    key=lambda s: (s.get("order",""), s.get("family",""),
                                   s.get("genus",""), s.get("scientific","")))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ebird-cache", default=str(SCRIPTS_DIR))
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--output", default=str(OUTPUT_FILE))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    output = Path(args.output)

    # Load existing
    existing = []
    if output.exists():
        try:
            data = json.loads(output.read_text(encoding="utf-8"))
            existing = data.get("species", [])
            print(f"Existing: {len(existing)} species")
        except Exception as e:
            print(f"Warning: {e}")

    # Phase 1: eBird data
    ebird_china = []
    ebird_en = []
    if not args.offline:
        try:
            ebird_en = fetch_ebird("en", args.ebird_cache)
            ebird_zh = fetch_ebird("zh", args.ebird_cache)
            ebird_china = build_ebird_china_set(ebird_en, ebird_zh)
        except Exception as e:
            print(f"eBird fetch failed: {e}")

    # Phase 2: Supplementary species
    supp = build_supp_species(ebird_en) if ebird_en else [
        {"scientific": sci, "chinese": cn, "english": "", "order": "", "order_cn": "",
         "family": "", "family_cn": "", "genus": sci.split()[0], "iucn": "LC",
         "protection": PROTECTION_MAP.get(sci), "resident": "resident", "has_audio": False}
        for sci, cn in SUPP_SPECIES
    ]

    # Phase 3: Merge
    merged = merge_all(existing, ebird_china, supp)

    # Stats
    orders = set(s.get("order","") for s in merged if s.get("order"))
    families = set(s.get("family","") for s in merged if s.get("family"))
    with_cn = sum(1 for s in merged if s.get("chinese"))
    protected = sum(1 for s in merged if s.get("protection"))
    print(f"\nFinal: {len(merged)} species, {len(orders)} orders, {len(families)} families")
    print(f"  With Chinese names: {with_cn}")
    print(f"  Protected (I/II): {protected}")

    if args.dry_run:
        print("[DRY RUN]")
        return

    result = {
        "version": "3.0",
        "source": "eBird/Clements taxonomy + 中国鸟类名录 v4.0 (郑光美, 2024)",
        "schema_version": "2.0",
        "note": "v3.0: Expanded via eBird API + supplementary China species data",
        "total": len(merged),
        "species": merged,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote: {output} ({output.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()
