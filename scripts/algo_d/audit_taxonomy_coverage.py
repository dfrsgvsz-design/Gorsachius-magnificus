"""Algo-D / P1-W2 audit: 9-group taxonomy coverage of the survey platform.

Originally scoped to 8 groups (鸟/哺乳/两栖/爬行/鱼/昆虫/植物/菌菇); expanded
to 9 in W2 round 2 after sponsor clarified the platform is nationwide (not
Hainan-only) and that marine biodiversity must be covered. The 9th group is
``marine_organisms`` (non-fish marine biota: invertebrates, algae, marine
mammals; based on Liu Ruiyu (2008) Checklist of Marine Biota of China Seas).

Backwards-compat: ``EIGHT_GROUPS`` is kept as an alias for ``NINE_GROUPS``.


Two layers of "expected":

  1. Seed manifest expected_count (what the package claims it ships).
  2. Survey-domain expected (independent reference; the realistic species count
     that mainland China / Taiwan biodiversity surveys are actually expected
     to encounter). Hard-coded below from authoritative checklists for the
     report; not loaded from any data file. Cite-and-update when refreshing.

For each of the 8 groups under each of the 2 jurisdictions, the script reports:
  - manifest_expected   (sum of submodule_expected_counts for that group from
                         taxonomy_packages.json)
  - seed_actual         (number of entries in the seed JSON for that group
                         under that jurisdiction)
  - domain_expected     (hard-coded reference; see DOMAIN_EXPECTED below)
  - manifest_vs_domain  (seed_actual / domain_expected, 0..1)
  - status              (OK / SEED_GAP / DOMAIN_GAP)

Writes a JSON report at scripts/algo_d/_artifacts/taxonomy_coverage_report.json
that drives docs/algo_d/taxonomy_coverage_report.md.

Exit code is always 0 unless inputs are missing (the gaps are surfaced in the
report; they are not test failures).
"""

from __future__ import annotations

import io
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

REPO_ROOT = Path(__file__).resolve().parents[2]
SMP_DATA = REPO_ROOT / "species_monitoring_platform" / "backend" / "data"
PKG_PATH = SMP_DATA / "taxonomy_packages.json"
PROTO_PATH = SMP_DATA / "survey_protocols.json"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "_artifacts"
REPORT_PATH = ARTIFACTS_DIR / "taxonomy_coverage_report.json"

# Nine groups -- covers the 8 列入工单 + marine_organisms (added W2 round 2
# after sponsor clarification that the platform is nationwide, not Hainan-
# specific, and must include marine biodiversity).
NINE_GROUPS = [
    ("birds",            "鸟",                  "terrestrial_vertebrates", "birds"),
    ("mammals",          "哺乳",                 "terrestrial_vertebrates", "mammals"),
    ("amphibians",       "两栖",                 "terrestrial_vertebrates", "amphibians"),
    ("reptiles",         "爬行",                 "terrestrial_vertebrates", "reptiles"),
    ("fish",             "鱼类",                 "aquatic_vertebrates", "freshwater_fish+estuarine_fish+marine_fish"),
    ("insects",          "昆虫",                 "insects", "insects"),
    ("plants",           "植物（维管）",          "plants", "plants"),
    ("fungi",            "菌菇+地衣",             "fungi", "macrofungi+lichens"),
    ("marine_organisms", "海洋生物（非鱼类）",     "marine_organisms", "marine_invertebrates+marine_algae+marine_mammals"),
]
# Back-compat alias for older importers.
EIGHT_GROUPS = NINE_GROUPS

# Survey-domain expected species counts -- NATIONAL-SCOPE references, not
# Hainan-only. Sources for each row are cited in
# docs/algo_d/taxonomy_coverage_report.md \xa76. The platform is used nationwide
# so these counts reflect what a field team anywhere in mainland_china or
# taiwan might reasonably need to look up.
DOMAIN_EXPECTED = {
    # Birds: Zheng (2017) Bird Checklist of China 3rd ed = ~1500;
    # Sanyou 2023 lists 1028 birds; National key protection 2021 lists
    # ~394 birds; merged catalog target ~1505 per release_builder check.
    ("birds",            "mainland_china"): 1505,
    ("birds",            "taiwan"):          674,
    ("mammals",          "mainland_china"):  700,
    ("mammals",          "taiwan"):           85,
    ("amphibians",       "mainland_china"):  430,
    ("amphibians",       "taiwan"):           42,
    ("reptiles",         "mainland_china"):  450,
    ("reptiles",         "taiwan"):           96,
    # Fish: combined freshwater + marine; China seas + inland waters
    # together ~3000 species per Fauna Sinica + FishBase China.
    ("fish",             "mainland_china"): 3000,
    ("fish",             "taiwan"):         3200,
    # Insects: practical survey-target subset (Sanyou 2023 lists 96
    # protected insects + ~700 commonly-surveyed butterflies/odonates).
    ("insects",          "mainland_china"): 1000,
    ("insects",          "taiwan"):          800,
    # Plants: Flora of China = 31500 vascular plant species.
    ("plants",           "mainland_china"):31500,
    ("plants",           "taiwan"):         4500,
    # Fungi: macrofungi ~3000 per Flora Fungorum Sinicorum; not microfungi.
    ("fungi",            "mainland_china"): 3000,
    ("fungi",            "taiwan"):         1000,
    # Marine organisms (non-fish): Liu Ruiyu (2008) Checklist of Marine
    # Biota of China Seas = 22629 species across 46 phyla; we subtract
    # the ~3000 marine fish (already in `fish`) to avoid double-counting.
    ("marine_organisms", "mainland_china"):20000,
    ("marine_organisms", "taiwan"):         8000,
}

# Map (jurisdiction, taxon_group) -> seed JSON file basename (under SMP_DATA)
SEED_FILES = {
    ("mainland_china", "birds"):         "terrestrial_vertebrates_taxonomy_seed.json",
    ("mainland_china", "mammals"):       "terrestrial_vertebrates_taxonomy_seed.json",
    ("mainland_china", "amphibians"):    "terrestrial_vertebrates_taxonomy_seed.json",
    ("mainland_china", "reptiles"):      "terrestrial_vertebrates_taxonomy_seed.json",
    ("mainland_china", "fish"):          "mainland_fish_taxonomy_seed.json",
    ("mainland_china", "insects"):       "mainland_insects_taxonomy_seed.json",
    ("mainland_china", "plants"):        "mainland_plants_taxonomy_seed.json",
    ("mainland_china", "fungi"):         "mainland_fungi_taxonomy_seed.json",
    ("taiwan",         "birds"):         "terrestrial_vertebrates_taxonomy_seed.json",
    ("taiwan",         "mammals"):       "terrestrial_vertebrates_taxonomy_seed.json",
    ("taiwan",         "amphibians"):    "terrestrial_vertebrates_taxonomy_seed.json",
    ("taiwan",         "reptiles"):      "terrestrial_vertebrates_taxonomy_seed.json",
    ("taiwan",         "fish"):          "taiwan_fish_taxonomy_seed.json",
    ("taiwan",         "insects"):       "taiwan_insects_taxonomy_seed.json",
    ("taiwan",         "plants"):        "taiwan_plants_taxonomy_seed.json",
    ("taiwan",         "fungi"):         "taiwan_fungi_taxonomy_seed.json",
}

# Map (jurisdiction, group_short) -> manifest package_id
PACKAGE_BY_J_G = {
    ("mainland_china", "birds"):         "cn_mainland_terrestrial_vertebrates_seed",
    ("mainland_china", "mammals"):       "cn_mainland_terrestrial_vertebrates_seed",
    ("mainland_china", "amphibians"):    "cn_mainland_terrestrial_vertebrates_seed",
    ("mainland_china", "reptiles"):      "cn_mainland_terrestrial_vertebrates_seed",
    ("mainland_china", "fish"):          "cn_mainland_aquatic_vertebrates_seed",
    ("mainland_china", "insects"):       "cn_mainland_insects_seed",
    ("mainland_china", "plants"):        "cn_mainland_plants_seed",
    ("mainland_china", "fungi"):         "cn_mainland_fungi_seed",
    ("taiwan",         "birds"):         "tw_terrestrial_vertebrates_seed",
    ("taiwan",         "mammals"):       "tw_terrestrial_vertebrates_seed",
    ("taiwan",         "amphibians"):    "tw_terrestrial_vertebrates_seed",
    ("taiwan",         "reptiles"):      "tw_terrestrial_vertebrates_seed",
    ("taiwan",         "fish"):          "tw_aquatic_vertebrates_seed",
    ("taiwan",         "insects"):       "tw_insects_seed",
    ("taiwan",         "plants"):        "tw_plants_seed",
    ("taiwan",         "fungi"):         "tw_fungi_seed",
}

# china_birds.json carries an additional 1300+ birds (display/search only,
# not yet promoted into the taxonomy_catalog seed). Count them separately.
CHINA_BIRDS_FILE = SMP_DATA / "china_birds.json"


def _load_json(p: Path):
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _count_china_birds() -> int:
    data = _load_json(CHINA_BIRDS_FILE)
    if not isinstance(data, dict):
        return 0
    species = data.get("species", data.get("entries", []))
    return len(species) if isinstance(species, list) else 0


def _count_seed_for(jurisdiction: str, group_short: str) -> int:
    """How many entries in the seed file actually belong to (jurisdiction, group)."""
    fname = SEED_FILES.get((jurisdiction, group_short))
    if not fname:
        return 0
    data = _load_json(SMP_DATA / fname)
    if data is None:
        return 0
    entries = data.get("entries", []) if isinstance(data, dict) else []
    if group_short in {"birds", "mammals", "amphibians", "reptiles"}:
        # vertebrate seed is jurisdiction-aware
        return sum(
            1
            for e in entries
            if e.get("taxon_group") == group_short
            and (e.get("jurisdictions") or {}).get(jurisdiction, {}).get("present", False)
        )
    if group_short == "fish":
        return sum(1 for e in entries
                   if e.get("group", "").endswith("fish"))
    if group_short == "fungi":
        return sum(1 for e in entries
                   if e.get("group", "") in {"macrofungi", "lichens"})
    if group_short == "insects":
        return sum(1 for e in entries
                   if e.get("group", "") in {"butterflies", "moths", "beetles",
                                              "odonates", "other_insects"})
    if group_short == "plants":
        return sum(1 for e in entries
                   if e.get("group", "") in {"vascular_plants", "shrubs", "trees", "herbs"})
    return len(entries)


def _manifest_expected_for(jurisdiction: str, group_short: str, packages: list[dict]) -> int:
    """Sum of submodule_expected_counts for the group within the package."""
    pkg_id = PACKAGE_BY_J_G.get((jurisdiction, group_short))
    if not pkg_id:
        return 0
    pkg = next((p for p in packages if p.get("package_id") == pkg_id), None)
    if pkg is None:
        return 0
    counts = pkg.get("submodule_expected_counts", {}) or {}
    if group_short in {"birds", "mammals", "amphibians", "reptiles"}:
        return int(counts.get(group_short, 0) or 0)
    if group_short == "fish":
        return sum(int(counts.get(k, 0) or 0)
                   for k in ("freshwater_fish", "estuarine_fish", "marine_fish"))
    if group_short == "fungi":
        return sum(int(counts.get(k, 0) or 0) for k in ("macrofungi", "lichens"))
    if group_short == "insects":
        return sum(int(counts.get(k, 0) or 0)
                   for k in ("butterflies", "moths", "beetles", "odonates", "other_insects"))
    if group_short == "plants":
        return sum(int(counts.get(k, 0) or 0)
                   for k in ("vascular_plants", "shrubs", "trees", "herbs"))
    return sum(int(v or 0) for v in counts.values())


def _status_label(seed_actual: int, manifest_expected: int, domain_expected: int) -> str:
    if seed_actual < manifest_expected:
        return "SEED_GAP"        # manifest claims more than the seed actually delivers
    pct = (seed_actual / domain_expected) if domain_expected > 0 else 1.0
    if pct < 0.001:
        return "DOMAIN_GAP_CRITICAL"   # < 0.1% of survey-domain expected
    if pct < 0.01:
        return "DOMAIN_GAP_HIGH"
    if pct < 0.1:
        return "DOMAIN_GAP_MEDIUM"
    if pct < 0.5:
        return "DOMAIN_GAP_LOW"
    return "OK"


def main() -> int:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    pkgs_doc = _load_json(PKG_PATH)
    if pkgs_doc is None:
        print(f"[FATAL] taxonomy_packages.json missing at {PKG_PATH}")
        return 3
    packages = pkgs_doc.get("packages", [])
    china_birds_count = _count_china_birds()

    print("=" * 72)
    print(" Algo-D / P1-W2 :: 9-group nationwide taxonomy coverage audit")
    print(f"  release_id    = {pkgs_doc.get('taxonomy_release_id')}")
    print(f"  packages      = {len(packages)}")
    print(f"  china_birds.json (extra display-only) = {china_birds_count} species")
    print("=" * 72)

    rows: list[dict] = []
    by_group: dict[str, list[dict]] = defaultdict(list)
    for short, cn, program, sub in NINE_GROUPS:
        for jurisdiction in ("mainland_china", "taiwan"):
            manifest_expected = _manifest_expected_for(jurisdiction, short, packages)
            seed_actual = _count_seed_for(jurisdiction, short)
            # Bird extra: china_birds.json is mainland_china birds display-side only
            extra_display = (china_birds_count if (short == "birds" and jurisdiction == "mainland_china") else 0)
            seed_plus_extra = seed_actual + extra_display
            domain_expected = DOMAIN_EXPECTED.get((short, jurisdiction), 0)
            status = _status_label(seed_plus_extra, manifest_expected, domain_expected)
            row = {
                "group": short,
                "group_cn": cn,
                "program": program,
                "submodule_set": sub,
                "jurisdiction": jurisdiction,
                "manifest_expected": manifest_expected,
                "seed_actual": seed_actual,
                "china_birds_extra_display_only": extra_display,
                "seed_plus_extra": seed_plus_extra,
                "domain_expected_reference": domain_expected,
                "coverage_pct_of_domain": round((seed_plus_extra / domain_expected) * 100, 3)
                                          if domain_expected > 0 else None,
                "status": status,
            }
            rows.append(row)
            by_group[short].append(row)

    # Print summary table
    print(f"  {'group':<11} {'jur':<14} {'expected':>9} {'seed':>5} {'+disp':>6} {'plus':>5} {'domain':>7} {'cov%':>7}  status")
    for row in rows:
        cov = f"{row['coverage_pct_of_domain']:.3f}" if row['coverage_pct_of_domain'] is not None else "n/a"
        print(f"  {row['group']:<11} {row['jurisdiction']:<14} "
              f"{row['manifest_expected']:>9} {row['seed_actual']:>5} "
              f"{row['china_birds_extra_display_only']:>6} {row['seed_plus_extra']:>5} "
              f"{row['domain_expected_reference']:>7} {cov:>6}%   {row['status']}")
    print("=" * 72)

    out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "ticket": "Algo-D / P1-W2 8-group taxonomy coverage report",
        "release_id": pkgs_doc.get("taxonomy_release_id"),
        "registry_packages": len(packages),
        "china_birds_display_only_count": china_birds_count,
        "rows": rows,
    }
    REPORT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  report: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
