#!/usr/bin/env python3
"""
Build the complete china_birds.json by combining multiple data sources.

Strategy:
  Phase 1: Fetch eBird taxonomy (EN + ZH locale) — 790 species with Chinese names
  Phase 2: Merge with existing china_birds.json (preserve rich fields)
  Phase 3: Add supplementary China species from embedded knowledge base
  Phase 4: Write updated china_birds.json

Usage:
    python scripts/build_china_birds.py                    # Full build (network required)
    python scripts/build_china_birds.py --offline           # Offline mode (embedded data only)
    python scripts/build_china_birds.py --ebird-cache DIR   # Use cached eBird JSON files
"""

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BACKEND_DATA = Path(__file__).resolve().parent.parent / "backend" / "data"
OUTPUT_FILE = BACKEND_DATA / "china_birds.json"

IOC_URLS = [
    # v14.2 multilingual — matches project's stated source
    "https://worldbirdnames.org/Multiling%20IOC%2014.2_c.xlsx",
    # v15.1 multilingual — fallback
    "https://worldbirdnames.org/Multiling%20IOC%2015.1_d.xlsx",
    # v15.2 multilingual — latest
    "https://worldbirdnames.org/Multiling%20IOC%2015.2.xlsx",
]

# Range keywords that indicate presence in China (including Taiwan)
CHINA_RANGE_KEYWORDS = [
    "china", "se china", "s china", "c china", "n china", "e china",
    "sw china", "ne china", "nw china", "w china",
    "taiwan", "hainan",
    "tibet", "xizang", "yunnan", "sichuan", "guangdong", "guangxi",
    "fujian", "zhejiang", "jiangsu", "hubei", "hunan", "anhui",
    "jiangxi", "guizhou", "shanxi", "shaanxi", "gansu", "qinghai",
    "heilongjiang", "jilin", "liaoning", "hebei", "shandong",
    "henan", "inner mongolia", "xinjiang", "manchuria",
    "chinese", "hong kong",
]

# Broader East Asian range keywords (for species that might include China)
EAST_ASIA_KEYWORDS = [
    "e asia", "east asia", "se asia", "ne asia", "n asia",
    "asia", "eurasia", "palearctic", "e palearctic",
    "oriental", "indomalaya",
    "himalayas", "himalaya",
    "japan", "korea", "indochina", "myanmar", "burma",
]

# IUCN status mapping
IUCN_MAP = {
    "least concern": "LC", "lc": "LC",
    "near threatened": "NT", "nt": "NT",
    "vulnerable": "VU", "vu": "VU",
    "endangered": "EN", "en": "EN",
    "critically endangered": "CR", "cr": "CR",
    "data deficient": "DD", "dd": "DD",
    "not evaluated": "NE", "ne": "NE",
}

# China national protection mapping (known species)
# Level I and II nationally protected species
PROTECTION_MAP = {
    # Level I (一级保护)
    "Grus japonensis": "I", "Grus leucogeranus": "I", "Grus nigricollis": "I",
    "Nipponia nippon": "I", "Ciconia boyciana": "I",
    "Pavo muticus": "I", "Lophophorus lhuysii": "I", "Lophophorus sclateri": "I",
    "Lophophorus impejanus": "I", "Tragopan caboti": "I", "Tragopan blythii": "I",
    "Crossoptilon mantchuricum": "I", "Syrmaticus ellioti": "I", "Syrmaticus humiae": "I",
    "Syrmaticus mikado": "I", "Lophura swinhoii": "I",
    "Arborophila rufipectus": "I", "Arborophila ardens": "I",
    "Tetrastes sewerzowi": "I", "Tetrao urogalloides": "I",
    "Polyplectron bicalcaratum": "I",
    "Aquila chrysaetos": "I", "Haliaeetus albicilla": "I",
    "Aegypius monachus": "I", "Gypaetus barbatus": "I",
    "Gyps himalayensis": "I",
    "Pelecanus crispus": "I",
    "Gorsachius magnificus": "I",
    "Mycteria leucocephala": "I",
    "Platalea minor": "I",
    "Buceros bicornis": "I",
    "Indicator xanthonotus": "I",
    "Pitta nympha": "I",
    "Otis tarda": "I", "Tetrax tetrax": "I",
    "Grus monacha": "I", "Grus vipio": "I",
    "Anthropoides virgo": "I",
    # Level II (二级保护)
    "Tetraogallus tibetanus": "II", "Tetraogallus himalayensis": "II",
    "Tetraophasis obscurus": "II", "Tetraophasis szechenyii": "II",
    "Alectoris magna": "II",
    "Arborophila gingica": "II", "Arborophila crudigularis": "II",
    "Tragopan temminckii": "II",
    "Ithaginis cruentus": "II",
    "Gallus gallus": "II",
    "Lophura nycthemera": "II",
    "Crossoptilon crossoptilon": "II", "Crossoptilon auritum": "II",
    "Syrmaticus reevesii": "II",
    "Chrysolophus pictus": "II", "Chrysolophus amherstiae": "II",
    "Pucrasia macrolopha": "II",
    "Tetrastes bonasia": "II", "Lyrurus tetrix": "II",
    "Pandion haliaetus": "II",
    "Accipiter nisus": "II", "Accipiter virgatus": "II",
    "Accipiter gentilis": "II", "Accipiter soloensis": "II",
    "Buteo japonicus": "II", "Buteo lagopus": "II", "Buteo hemilasius": "II",
    "Milvus migrans": "II",
    "Circus cyaneus": "II", "Circus melanoleucos": "II",
    "Elanus caeruleus": "II",
    "Pernis ptilorhynchus": "II",
    "Spilornis cheela": "II", "Spizaetus nipalensis": "II",
    "Falco peregrinus": "II", "Falco subbuteo": "II", "Falco tinnunculus": "II",
    "Falco columbarius": "II", "Falco amurensis": "II",
    "Bubo bubo": "II", "Bubo scandiacus": "II",
    "Strix aluco": "II", "Strix leptogrammica": "II", "Strix uralensis": "II",
    "Asio otus": "II", "Asio flammeus": "II",
    "Otus lettia": "II", "Otus sunia": "II", "Otus spilocephalus": "II",
    "Glaucidium cuculoides": "II", "Glaucidium brodiei": "II",
    "Athene noctua": "II",
    "Ninox scutulata": "II",
    "Tyto longimembris": "II", "Tyto alba": "II",
    "Ketupa zeylonensis": "II",
    "Aix galericulata": "II",
    "Cygnus columbianus": "II", "Cygnus cygnus": "II",
    "Anser cygnoid": "II", "Anser indicus": "II",
    "Grus grus": "II",
    "Alcedo atthis": "II", "Halcyon smyrnensis": "II",
    "Upupa epops": "II",
    "Psittacula alexandri": "II", "Psittacula derbiana": "II",
    "Ibidorhyncha struthersii": "II",
    "Recurvirostra avosetta": "II",
    "Podiceps cristatus": "II",
}


def _range_mentions_china(breeding_range: str, nonbreeding_range: str) -> bool:
    """Check if the combined range text mentions China or nearby regions."""
    text = f"{breeding_range} {nonbreeding_range}".lower()
    # Direct China mentions
    for kw in CHINA_RANGE_KEYWORDS:
        if kw in text:
            return True
    return False


def _range_might_include_china(breeding_range: str, nonbreeding_range: str) -> bool:
    """Broader check for East Asian species that might occur in China."""
    text = f"{breeding_range} {nonbreeding_range}".lower()
    for kw in EAST_ASIA_KEYWORDS:
        if kw in text:
            return True
    return False


def _guess_resident_status(breeding_range: str, nonbreeding_range: str) -> str:
    """Guess resident status based on range columns."""
    br = breeding_range.lower()
    nbr = nonbreeding_range.lower()
    has_china_breeding = any(kw in br for kw in CHINA_RANGE_KEYWORDS)
    has_china_nonbreeding = any(kw in nbr for kw in CHINA_RANGE_KEYWORDS)
    if has_china_breeding and has_china_nonbreeding:
        return "resident"
    if has_china_breeding and not has_china_nonbreeding:
        return "summer"
    if not has_china_breeding and has_china_nonbreeding:
        return "winter"
    # Broad range — default to passage or resident
    return "resident"


def _find_header_row(ws):
    """Find the header row in the worksheet by looking for 'Scientific Name' or 'Species' columns."""
    for row_idx in range(1, min(20, ws.max_row + 1)):
        cells = [str(ws.cell(row=row_idx, column=col).value or "").strip().lower()
                 for col in range(1, min(50, ws.max_column + 1))]
        # Look for key columns
        if any("species" in c or "scientific" in c for c in cells):
            if any("english" in c or "common" in c for c in cells):
                return row_idx, cells
    return None, None


def _find_column(headers, *keywords):
    """Find column index (0-based) matching any keyword."""
    for idx, h in enumerate(headers):
        for kw in keywords:
            if kw in h:
                return idx
    return None


def download_ioc_xlsx(target_path: Path) -> bool:
    """Try to download IOC multilingual XLSX from known URLs."""
    for url in IOC_URLS:
        print(f"  Trying: {url}")
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0 BirdPlatform/1.0"})
            urlretrieve(url, str(target_path))
            size_mb = target_path.stat().st_size / (1024 * 1024)
            if size_mb < 0.5:
                print(f"    File too small ({size_mb:.1f}MB), skipping")
                target_path.unlink(missing_ok=True)
                continue
            print(f"    Downloaded: {size_mb:.1f}MB")
            return True
        except (URLError, OSError) as e:
            print(f"    Failed: {e}")
            continue
    return False


def parse_ioc_xlsx(xlsx_path: Path) -> list[dict]:
    """Parse the IOC Multilingual Excel and extract China species."""
    print(f"Parsing: {xlsx_path.name}")
    wb = openpyxl.load_workbook(str(xlsx_path), read_only=True, data_only=True)

    # Try different sheet names
    target_sheet = None
    for name in wb.sheetnames:
        nl = name.lower()
        if "list" in nl or "master" in nl or "species" in nl or "vs" in nl:
            target_sheet = name
            break
    if not target_sheet:
        target_sheet = wb.sheetnames[0]

    ws = wb[target_sheet]
    print(f"  Sheet: {target_sheet} ({ws.max_row} rows x {ws.max_column} cols)")

    header_row, headers = _find_header_row(ws)
    if not header_row:
        print("  ERROR: Could not find header row")
        wb.close()
        return []

    print(f"  Header row: {header_row}")
    print(f"  Columns: {headers[:20]}...")

    # Find key columns
    col_order = _find_column(headers, "order")
    col_family = _find_column(headers, "family")
    col_genus = _find_column(headers, "genus")
    col_species = _find_column(headers, "species (scientific)", "scientific name", "species")
    col_english = _find_column(headers, "english name", "english", "common name")
    col_breeding = _find_column(headers, "breeding range", "breeding", "range")
    col_nonbreeding = _find_column(headers, "nonbreeding range", "non-breeding", "nonbreeding")
    col_chinese = _find_column(headers, "chinese", "中文", "mandarin")
    col_iucn = _find_column(headers, "iucn", "red list", "status")
    col_authority = _find_column(headers, "authority")

    print(f"  Column indices — order:{col_order} family:{col_family} genus:{col_genus} "
          f"species:{col_species} english:{col_english} breeding:{col_breeding} "
          f"nonbreeding:{col_nonbreeding} chinese:{col_chinese} iucn:{col_iucn}")

    if col_species is None and col_english is None:
        print("  ERROR: Cannot find species or english name columns")
        wb.close()
        return []

    species_list = []
    current_order = ""
    current_family = ""
    skipped = 0
    china_direct = 0
    china_broad = 0

    for row_idx in range(header_row + 1, ws.max_row + 1):
        def cell(col_idx):
            if col_idx is None:
                return ""
            val = ws.cell(row=row_idx, column=col_idx + 1).value
            return str(val).strip() if val else ""

        # Update current order/family from hierarchy rows
        order_val = cell(col_order)
        family_val = cell(col_family)
        if order_val:
            current_order = order_val
        if family_val:
            current_family = family_val

        scientific = cell(col_species)
        english = cell(col_english)

        # Skip non-species rows (headers, blanks, subspecies)
        if not scientific or not english:
            continue
        # Skip if it looks like a header or infraclass
        if scientific.lower() in ("species", "scientific name", "infraclass"):
            continue
        # Must have at least two words (Genus species)
        parts = scientific.split()
        if len(parts) < 2:
            continue

        breeding = cell(col_breeding)
        nonbreeding = cell(col_nonbreeding)
        chinese = cell(col_chinese)
        iucn_raw = cell(col_iucn)
        genus = cell(col_genus) or parts[0]

        # Determine if species occurs in China
        is_china = _range_mentions_china(breeding, nonbreeding)
        is_broad_asia = _range_might_include_china(breeding, nonbreeding)

        if not is_china and not is_broad_asia:
            skipped += 1
            continue

        if is_china:
            china_direct += 1
        else:
            china_broad += 1

        # Normalize IUCN
        iucn = IUCN_MAP.get(iucn_raw.lower().strip(), "LC") if iucn_raw else "LC"

        # Determine protection level
        protection = PROTECTION_MAP.get(scientific, None)

        # Determine resident status
        resident = _guess_resident_status(breeding, nonbreeding)

        # Parse order Chinese name
        order_cn = _order_chinese(current_order)
        family_cn = _family_chinese(current_family)

        entry = {
            "scientific": scientific,
            "chinese": chinese or "",
            "english": english,
            "order": current_order,
            "order_cn": order_cn,
            "family": current_family,
            "family_cn": family_cn,
            "genus": genus,
            "iucn": iucn,
            "protection": protection,
            "resident": resident,
            "has_audio": False,
        }
        species_list.append(entry)

    wb.close()
    print(f"  Parsed: {len(species_list)} China species "
          f"(direct:{china_direct}, broad:{china_broad}, skipped:{skipped})")
    return species_list


# ---------------------------------------------------------------------------
# Chinese names for orders and families
# ---------------------------------------------------------------------------
ORDER_CN = {
    "Galliformes": "鸡形目", "Anseriformes": "雁形目",
    "Podicipediformes": "鸊鷉目", "Phoenicopteriformes": "火烈鸟目",
    "Columbiformes": "鸽形目", "Pterocliformes": "沙鸡目",
    "Otidiformes": "鸨目", "Cuculiformes": "鹃形目",
    "Caprimulgiformes": "夜鹰目", "Apodiformes": "雨燕目",
    "Gruiformes": "鹤形目", "Charadriiformes": "鸻形目",
    "Gaviiformes": "潜鸟目", "Procellariiformes": "鹱形目",
    "Phaethontiformes": "鹲目", "Ciconiiformes": "鹳形目",
    "Suliformes": "鲣鸟目", "Pelecaniformes": "鹈形目",
    "Accipitriformes": "鹰形目", "Strigiformes": "鸮形目",
    "Bucerotiformes": "犀鸟目", "Trogoniformes": "咬鹃目",
    "Coraciiformes": "佛法僧目", "Piciformes": "鴷形目",
    "Falconiformes": "隼形目", "Psittaciformes": "鹦鹉目",
    "Passeriformes": "雀形目",
}

FAMILY_CN = {
    "Phasianidae": "雉科", "Anatidae": "鸭科",
    "Podicipedidae": "鸊鷉科", "Phoenicopteridae": "火烈鸟科",
    "Columbidae": "鸠鸽科", "Pteroclidae": "沙鸡科",
    "Otididae": "鸨科", "Cuculidae": "杜鹃科",
    "Caprimulgidae": "夜鹰科", "Apodidae": "雨燕科",
    "Hemiprocnidae": "凤头雨燕科", "Rallidae": "秧鸡科",
    "Gruidae": "鹤科", "Burhinidae": "石鸻科",
    "Haematopodidae": "蛎鹬科", "Ibidorhynchidae": "鹮嘴鹬科",
    "Recurvirostridae": "反嘴鹬科", "Charadriidae": "鸻科",
    "Scolopacidae": "鹬科", "Turnicidae": "三趾鹑科",
    "Glareolidae": "燕鸻科", "Laridae": "鸥科",
    "Stercorariidae": "贼鸥科", "Alcidae": "海雀科",
    "Gaviidae": "潜鸟科", "Diomedeidae": "信天翁科",
    "Procellariidae": "鹱科", "Hydrobatidae": "海燕科",
    "Oceanitidae": "洋海燕科",
    "Phaethontidae": "鹲科", "Ciconiidae": "鹳科",
    "Fregatidae": "军舰鸟科", "Sulidae": "鲣鸟科",
    "Anhingidae": "蛇鹈科", "Phalacrocoracidae": "鸬鹚科",
    "Pelecanidae": "鹈鹕科", "Ardeidae": "鹭科",
    "Threskiornithidae": "鹮科",
    "Pandionidae": "鹗科", "Accipitridae": "鹰科",
    "Tytonidae": "草鸮科", "Strigidae": "鸱鸮科",
    "Bucerotidae": "犀鸟科", "Upupidae": "戴胜科",
    "Trogonidae": "咬鹃科", "Coraciidae": "佛法僧科",
    "Alcedinidae": "翠鸟科", "Meropidae": "蜂虎科",
    "Indicatoridae": "响蜜鴷科",
    "Picidae": "啄木鸟科", "Megalaimidae": "拟啄木鸟科",
    "Ramphastidae": "巨嘴鸟科",
    "Falconidae": "隼科",
    "Psittaculidae": "鹦鹉科", "Psittacidae": "鹦鹉科",
    # Passerine families
    "Pittidae": "八色鸫科", "Eurylaimidae": "阔嘴鸟科",
    "Campephagidae": "山椒鸟科",
    "Oriolidae": "黄鹂科", "Artamidae": "燕鵙科",
    "Aegithinidae": "雀鹎科",
    "Vangidae": "钩嘴鵙科", "Tephrodornithidae": "钩嘴鵙科",
    "Laniidae": "伯劳科", "Corvidae": "鸦科",
    "Stenostiridae": "仙鹟科",
    "Dicruridae": "卷尾科", "Monarchidae": "王鹟科",
    "Rhipiduridae": "扇尾鹟科",
    "Paridae": "山雀科", "Remizidae": "攀雀科",
    "Alaudidae": "百灵科", "Pycnonotidae": "鹎科",
    "Hirundinidae": "燕科",
    "Cettidae": "树莺科", "Aegithalidae": "长尾山雀科",
    "Phylloscopidae": "柳莺科",
    "Acrocephalidae": "苇莺科", "Locustellidae": "蝗莺科",
    "Cisticolidae": "扇尾莺科",
    "Sylviidae": "莺科",
    "Paradoxornithidae": "鸦雀科",
    "Zosteropidae": "绣眼鸟科",
    "Timaliidae": "雀鹛科",
    "Leiothrichidae": "噪鹛科",
    "Pellorneidae": "幽鹛科",
    "Alcippeidae": "雀鹛科",
    "Elachuridae": "丽鹛科",
    "Sittidae": "鳾科", "Tichodromidae": "旋壁雀科",
    "Certhiidae": "旋木雀科",
    "Troglodytidae": "鹪鹩科", "Cinclidae": "河乌科",
    "Sturnidae": "椋鸟科",
    "Turdidae": "鸫科", "Muscicapidae": "鹟科",
    "Regulidae": "戴菊科",
    "Bombycillidae": "太平鸟科",
    "Prunellidae": "岩鹨科",
    "Passeridae": "麻雀科", "Ploceidae": "织雀科",
    "Estrildidae": "梅花雀科",
    "Motacillidae": "鹡鸰科",
    "Fringillidae": "雀科",
    "Emberizidae": "鹀科", "Calcariidae": "铁爪鹀科",
    "Nectariniidae": "太阳鸟科",
    "Dicaeidae": "啄花鸟科",
    "Chloropseidae": "叶鹎科", "Irenidae": "和平鸟科",
    "Vireonidae": "绿鹃科",
    "Pachycephalidae": "啸鹟科",
    "Scotocercidae": "鹟莺科",
    "Erythrocercidae": "红尾鹟科",
}


def _order_chinese(order: str) -> str:
    return ORDER_CN.get(order, order)


def _family_chinese(family: str) -> str:
    return FAMILY_CN.get(family, family)


def merge_species(existing: list[dict], new_entries: list[dict]) -> list[dict]:
    """Merge new species into existing list. Existing entries take priority."""
    by_sci = {}
    # Index existing by scientific name
    for entry in existing:
        sci = entry.get("scientific", "")
        if sci:
            by_sci[sci] = entry

    added = 0
    updated = 0
    for entry in new_entries:
        sci = entry.get("scientific", "")
        if not sci:
            continue
        if sci in by_sci:
            # Update only missing fields in existing entry
            ex = by_sci[sci]
            for key, val in entry.items():
                if key not in ex or ex[key] in (None, "", []):
                    if val not in (None, "", []):
                        ex[key] = val
                        updated += 1
        else:
            by_sci[sci] = entry
            added += 1

    print(f"  Merge: {added} new species added, {updated} fields updated in existing entries")

    # Sort by order, family, genus, species
    result = sorted(by_sci.values(),
                    key=lambda s: (s.get("order", ""), s.get("family", ""),
                                   s.get("genus", ""), s.get("scientific", "")))
    return result


def write_china_birds(species: list[dict], output_path: Path):
    """Write the final china_birds.json."""
    data = {
        "version": "3.0",
        "source": "IOC World Bird List v14.2 / 中国鸟类名录 v4.0 (郑光美, 2024)",
        "schema_version": "2.0",
        "note": "v3.0: Expanded from IOC Multilingual Excel. Merged with existing v2.0 data.",
        "total": len(species),
        "species": species,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    size_kb = output_path.stat().st_size // 1024
    print(f"\nWrote: {output_path}")
    print(f"  Total species: {len(species)}")
    print(f"  File size: {size_kb}KB")


def main():
    parser = argparse.ArgumentParser(description="Build china_birds.json from IOC data")
    parser.add_argument("--xlsx", type=str, default=None,
                        help="Path to local IOC Multilingual Excel file")
    parser.add_argument("--output", type=str, default=str(OUTPUT_FILE),
                        help="Output path for china_birds.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and show stats without writing")
    args = parser.parse_args()

    output_path = Path(args.output)

    # Load existing data
    existing_species = []
    if output_path.exists():
        try:
            data = json.loads(output_path.read_text(encoding="utf-8"))
            existing_species = data.get("species", [])
            print(f"Existing: {len(existing_species)} species in {output_path.name}")
        except Exception as e:
            print(f"Warning: Could not read existing file: {e}")

    # Get IOC Excel
    xlsx_path = None
    if args.xlsx:
        xlsx_path = Path(args.xlsx)
        if not xlsx_path.exists():
            print(f"ERROR: File not found: {xlsx_path}")
            sys.exit(1)
    else:
        # Try to download
        tmp_dir = Path(tempfile.mkdtemp(prefix="ioc_"))
        xlsx_path = tmp_dir / "ioc_multilingual.xlsx"
        print("Downloading IOC Multilingual Excel...")
        if not download_ioc_xlsx(xlsx_path):
            print("\nERROR: Could not download IOC Excel.")
            print("Please download manually from:")
            print("  https://worldbirdnames.org/Multiling%20IOC%2014.2_c.xlsx")
            print("Then run: python scripts/build_china_birds.py --xlsx path/to/file.xlsx")
            sys.exit(1)

    # Parse
    new_species = parse_ioc_xlsx(xlsx_path)
    if not new_species:
        print("ERROR: No species parsed from Excel file")
        sys.exit(1)

    # Merge
    print("\nMerging...")
    merged = merge_species(existing_species, new_species)

    # Stats
    orders = set(s.get("order", "") for s in merged)
    families = set(s.get("family", "") for s in merged)
    with_chinese = sum(1 for s in merged if s.get("chinese"))
    protected = sum(1 for s in merged if s.get("protection"))
    print(f"\nFinal stats:")
    print(f"  Species: {len(merged)}")
    print(f"  Orders: {len(orders)}")
    print(f"  Families: {len(families)}")
    print(f"  With Chinese names: {with_chinese}")
    print(f"  Protected (I/II): {protected}")

    if args.dry_run:
        print("\n[DRY RUN] Not writing output.")
        return

    write_china_birds(merged, output_path)
    print("\nDone!")


if __name__ == "__main__":
    main()
