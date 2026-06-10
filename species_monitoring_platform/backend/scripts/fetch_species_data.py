"""
Species data fetcher for the Biodiversity Field Survey Platform.

Downloads and converts species data from public sources into platform format.
Supports: sp2000.org.cn API, GBIF, and local CSV/Excel files.

Usage:
    python scripts/fetch_species_data.py --source sp2000 --api-key YOUR_KEY --taxon-group birds
    python scripts/fetch_species_data.py --source gbif --country CN --class Aves --limit 5000
    python scripts/fetch_species_data.py --source csv --file mammals.csv
    python scripts/fetch_species_data.py --source col-china --year 2025

Environment variables:
    SP2000_API_KEY   - API key for sp2000.org.cn
    GBIF_USER        - GBIF username
    GBIF_PWD         - GBIF password

Output is written to backend/data/ in platform taxonomy format.
"""

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"

TAXON_GROUP_MAP = {
    "aves": "birds",
    "birds": "birds",
    "mammalia": "mammals",
    "mammals": "mammals",
    "amphibia": "amphibians",
    "amphibians": "amphibians",
    "reptilia": "reptiles",
    "reptiles": "reptiles",
}

IUCN_STATUS_MAP = {
    "LC": "LC", "NT": "NT", "VU": "VU", "EN": "EN",
    "CR": "CR", "EW": "EW", "EX": "EX", "DD": "DD",
    "NE": "NE", "Least Concern": "LC", "Near Threatened": "NT",
    "Vulnerable": "VU", "Endangered": "EN", "Critically Endangered": "CR",
}

CHINA_PROTECTION_MAP = {
    "I": "first_class", "1": "first_class", "一级": "first_class",
    "II": "second_class", "2": "second_class", "二级": "second_class",
}


def normalize_protection(raw):
    if not raw:
        return None
    return CHINA_PROTECTION_MAP.get(str(raw).strip(), None)


def normalize_iucn(raw):
    if not raw:
        return None
    return IUCN_STATUS_MAP.get(str(raw).strip(), None)


def build_taxon_entry(
    taxon_group, scientific_name, chinese_name="", english_name="",
    traditional_chinese_name="", protection=None, iucn=None,
    present_mainland=True, present_taiwan=False,
    order="", family="", genus="",
):
    group_key = TAXON_GROUP_MAP.get(taxon_group.lower(), taxon_group.lower())
    slug = scientific_name.lower().replace(" ", "-")
    taxon_id = f"vert-{group_key[:4]}-{slug}"

    sensitivity = "public"
    if protection == "first_class" or iucn in ("CR", "EN"):
        sensitivity = "masked_10km"
    elif protection == "second_class" or iucn in ("VU", "NT"):
        sensitivity = "masked_1km"

    return {
        "internal_taxon_id": taxon_id,
        "taxon_group": group_key,
        "scientific_name": scientific_name,
        "simplified_chinese_name": chinese_name or "",
        "traditional_chinese_name": traditional_chinese_name or chinese_name or "",
        "english_common_name": english_name or "",
        "order": order,
        "family": family,
        "genus": genus,
        "jurisdictions": {
            "mainland_china": {
                "present": present_mainland,
                "national_protection_status": protection if present_mainland else None,
                "red_list_status": iucn if present_mainland else None,
                "sensitive_coordinate_policy": sensitivity if present_mainland else "not_applicable",
            },
            "taiwan": {
                "present": present_taiwan,
                "taiwan_protection_status": None,
                "red_list_status": iucn if present_taiwan else None,
                "sensitive_coordinate_policy": sensitivity if present_taiwan else "not_applicable",
            },
        },
    }


def fetch_from_sp2000(api_key, taxon_group="birds", page_limit=100):
    """Fetch species list from sp2000.org.cn (Catalogue of Life China)."""
    if not requests:
        print("ERROR: 'requests' package is required. Install with: pip install requests")
        return []

    base_url = "http://www.sp2000.org.cn/api/v2"
    entries = []
    page = 1

    group_families = {
        "birds": "Aves",
        "mammals": "Mammalia",
        "amphibians": "Amphibia",
        "reptiles": "Reptilia",
    }

    class_name = group_families.get(taxon_group, taxon_group)
    print(f"Fetching {class_name} from sp2000.org.cn...")

    while page <= page_limit:
        try:
            resp = requests.get(
                f"{base_url}/getSpeciesByFamilyId",
                params={"apiKey": api_key, "familyName": class_name, "page": page},
                timeout=30,
            )
            data = resp.json()

            if data.get("code") != 200:
                print(f"  API error: {data.get('message', 'Unknown')}")
                break

            records = data.get("data", {}).get("record", [])
            if not records:
                break

            for rec in records:
                entry = build_taxon_entry(
                    taxon_group=taxon_group,
                    scientific_name=rec.get("scientificName", ""),
                    chinese_name=rec.get("chineseName", ""),
                    english_name=rec.get("commonName", ""),
                    family=rec.get("family", ""),
                )
                entries.append(entry)

            print(f"  Page {page}: {len(records)} records (total: {len(entries)})")
            page += 1
            time.sleep(0.5)

        except Exception as e:
            print(f"  Error on page {page}: {e}")
            break

    return entries


def fetch_from_gbif(country="CN", class_name="Aves", limit=5000):
    """Fetch species checklist from GBIF."""
    if not requests:
        print("ERROR: 'requests' package is required. Install with: pip install requests")
        return []

    entries = []
    offset = 0
    batch_size = 300

    print(f"Fetching {class_name} from GBIF (country={country})...")

    while offset < limit:
        try:
            resp = requests.get(
                "https://api.gbif.org/v1/species/search",
                params={
                    "rank": "SPECIES",
                    "class": class_name,
                    "status": "ACCEPTED",
                    "limit": min(batch_size, limit - offset),
                    "offset": offset,
                    "habitat": "TERRESTRIAL",
                },
                timeout=30,
            )
            data = resp.json()
            results = data.get("results", [])

            if not results:
                break

            for rec in results:
                scientific = rec.get("canonicalName") or rec.get("scientificName", "")
                if not scientific:
                    continue

                entry = build_taxon_entry(
                    taxon_group=class_name,
                    scientific_name=scientific,
                    chinese_name=rec.get("vernacularName", ""),
                    english_name=rec.get("vernacularName", ""),
                    family=rec.get("family", ""),
                    genus=rec.get("genus", ""),
                    order=rec.get("order", ""),
                    iucn=normalize_iucn(rec.get("threatStatus")),
                )
                entries.append(entry)

            print(f"  Offset {offset}: {len(results)} records (total: {len(entries)})")
            offset += batch_size
            time.sleep(0.3)

        except Exception as e:
            print(f"  Error at offset {offset}: {e}")
            break

    return entries


def import_from_csv(filepath, taxon_group="birds"):
    """Import species from a CSV file.

    Expected columns (flexible matching):
        scientific_name | 学名
        chinese_name | 中文名 | simplified_chinese_name
        english_name | 英文名 | english_common_name
        protection | 保护等级 | national_protection_status
        iucn | IUCN | red_list_status
        order | 目
        family | 科
    """
    entries = []
    col_map = {
        "scientific_name": ["scientific_name", "学名", "scientificname", "species"],
        "chinese_name": ["chinese_name", "中文名", "simplified_chinese_name", "chinesename", "中文学名"],
        "english_name": ["english_name", "英文名", "english_common_name", "englishname", "common_name"],
        "protection": ["protection", "保护等级", "national_protection_status", "保护级别"],
        "iucn": ["iucn", "IUCN", "red_list_status", "iucn_status", "红色名录"],
        "order": ["order", "目", "order_name"],
        "family": ["family", "科", "family_name"],
    }

    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = {h.strip().lower(): h for h in (reader.fieldnames or [])}

            def find_col(key):
                for candidate in col_map.get(key, []):
                    for h_lower, h_orig in headers.items():
                        if h_lower == candidate.lower():
                            return h_orig
                return None

            sci_col = find_col("scientific_name")
            cn_col = find_col("chinese_name")
            en_col = find_col("english_name")
            prot_col = find_col("protection")
            iucn_col = find_col("iucn")
            order_col = find_col("order")
            family_col = find_col("family")

            if not sci_col:
                print(f"ERROR: Could not find 'scientific_name' column in {filepath}")
                print(f"  Available columns: {list(headers.values())}")
                return []

            for row in reader:
                scientific = (row.get(sci_col) or "").strip()
                if not scientific:
                    continue

                entry = build_taxon_entry(
                    taxon_group=taxon_group,
                    scientific_name=scientific,
                    chinese_name=(row.get(cn_col) or "").strip() if cn_col else "",
                    english_name=(row.get(en_col) or "").strip() if en_col else "",
                    protection=normalize_protection(row.get(prot_col)) if prot_col else None,
                    iucn=normalize_iucn(row.get(iucn_col)) if iucn_col else None,
                    order=(row.get(order_col) or "").strip() if order_col else "",
                    family=(row.get(family_col) or "").strip() if family_col else "",
                )
                entries.append(entry)

        print(f"Imported {len(entries)} entries from {filepath}")

    except Exception as e:
        print(f"ERROR reading {filepath}: {e}")

    return entries


def save_entries(entries, taxon_group, output_name=None):
    """Save entries to platform taxonomy JSON format."""
    if not entries:
        print("No entries to save.")
        return

    seen = set()
    unique = []
    for e in entries:
        if e["scientific_name"] not in seen:
            seen.add(e["scientific_name"])
            unique.append(e)

    filename = output_name or f"{taxon_group}_species_imported.json"
    output_path = DATA_DIR / filename

    doc = {
        "schema_version": "1.0",
        "asset_version": f"imported-{time.strftime('%Y%m%d')}",
        "description": f"Imported {taxon_group} species list ({len(unique)} taxa)",
        "shared_taxon_key": "internal_taxon_id",
        "seed_only": False,
        "exhaustive_species_content": False,
        "taxon_groups": [TAXON_GROUP_MAP.get(taxon_group.lower(), taxon_group)],
        "total": len(unique),
        "entries": unique,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    print(f"\nSaved {len(unique)} unique entries to {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Fetch species data for the platform")
    parser.add_argument("--source", choices=["sp2000", "gbif", "csv", "col-china"],
                        required=True, help="Data source")
    parser.add_argument("--taxon-group", default="birds",
                        choices=["birds", "mammals", "amphibians", "reptiles"],
                        help="Taxonomic group to fetch")
    parser.add_argument("--api-key", default=os.environ.get("SP2000_API_KEY"),
                        help="API key (for sp2000)")
    parser.add_argument("--country", default="CN", help="Country code (for GBIF)")
    parser.add_argument("--limit", type=int, default=5000, help="Max records to fetch")
    parser.add_argument("--file", help="Input CSV file path")
    parser.add_argument("--output", help="Output filename (default: auto-generated)")

    args = parser.parse_args()

    if args.source == "sp2000":
        if not args.api_key:
            print("ERROR: --api-key or SP2000_API_KEY env var required for sp2000 source")
            sys.exit(1)
        entries = fetch_from_sp2000(args.api_key, args.taxon_group, page_limit=args.limit)

    elif args.source == "gbif":
        class_map = {
            "birds": "Aves", "mammals": "Mammalia",
            "amphibians": "Amphibia", "reptiles": "Reptilia",
        }
        entries = fetch_from_gbif(args.country, class_map[args.taxon_group], args.limit)

    elif args.source == "csv":
        if not args.file:
            print("ERROR: --file required for csv source")
            sys.exit(1)
        entries = import_from_csv(args.file, args.taxon_group)

    elif args.source == "col-china":
        print("Catalogue of Life China download: visit http://www.sp2000.org.cn")
        print("Download the annual checklist, then use --source csv to import.")
        sys.exit(0)

    else:
        print(f"Unknown source: {args.source}")
        sys.exit(1)

    save_entries(entries, args.taxon_group, args.output)


if __name__ == "__main__":
    main()
