"""
China Bird Species Database — 支持1505种完整中国鸟类名录扩展。

数据来源:
- 中国鸟类名录 v4.0 (郑光美, 2024)
- IOC World Bird List v14.2 (filtered for China)
- Xeno-canto recordings metadata

架构设计:
- JSON数据文件可独立更新 (data/china_birds.json)
- 支持按目/科/属/种四级分类查询
- 保护等级标注 (IUCN / 国家重点保护)
- 模糊搜索中文名、英文名、学名
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from functools import lru_cache

try:
    from runtime_paths import get_resource_data_dir
except ImportError:
    try:
        from shared.backend.utils.runtime_paths import get_resource_data_dir
    except ImportError:
        from ..utils.runtime_paths import get_resource_data_dir

# ──────────────────────────────────────────────
# Data paths
# ──────────────────────────────────────────────
_DB_DIR = get_resource_data_dir()
_DB_FILE = _DB_DIR / "china_birds.json"

# ──────────────────────────────────────────────
# Schema v2.0 — Enhanced per Sugai et al. (2026)
# ──────────────────────────────────────────────
# Each species entry (v2 adds functional traits, acoustic features, habitat):
# {
#   -- Core taxonomy --
#   "scientific": "Gorsachius magnificus",
#   "chinese":    "海南鳽",
#   "english":    "White-eared Night Heron",
#   "order":      "Pelecaniformes",
#   "order_cn":   "鹈形目",
#   "family":     "Ardeidae",
#   "family_cn":  "鹭科",
#   "genus":      "Gorsachius",
#
#   -- Conservation status --
#   "iucn":       "EN",           # CR/EN/VU/NT/LC/DD/NE
#   "protection": "II",           # I/II/None (国家重点保护等级)
#   "population_trend": "decreasing", # increasing/stable/decreasing/unknown
#   "endemic":    false,          # 中国特有种
#
#   -- Ecology --
#   "resident":   "resident",     # resident/summer/winter/passage
#   "regions":    ["华南", "华东"],  # 分布区域
#   "habitat":    ["forest", "wetland"],  # 主要栖息地类型
#   "foraging_guild": "carnivore",  # insectivore/granivore/omnivore/carnivore/nectarivore/frugivore
#   "nesting_type": "tree",       # ground/tree/cavity/cliff/reed
#
#   -- Functional traits (for functional diversity: Cadotte et al., 2011) --
#   "body_mass":      540.0,      # grams
#   "wing_length":    298.0,      # mm
#   "bill_length":    68.0,       # mm (culmen)
#   "tarsus_length":  78.0,       # mm
#
#   -- Acoustic features (for CNN/embedding analysis) --
#   "freq_range_low":  300,       # Hz, typical vocalization low frequency
#   "freq_range_high": 2500,      # Hz, typical vocalization high frequency
#   "peak_freq":       1200,      # Hz, dominant frequency
#   "call_duration":   1.5,       # seconds, typical call duration
#   "vocal_activity":  "nocturnal", # diurnal/nocturnal/crepuscular/all_day
#   "song_complexity": "simple",  # simple/moderate/complex
#
#   -- Data availability --
#   "has_audio":  true,           # 是否有可下载录音
#   "xc_count":   42,             # xeno-canto录音数量估计
#   "birdnet_supported": true,    # BirdNET是否支持该物种
# }


class SpeciesDB:
    """Chinese bird species database with search and query capabilities."""

    def __init__(self, db_path: Optional[str] = None):
        self._path = Path(db_path) if db_path else _DB_FILE
        self._species: List[Dict] = []
        self._by_scientific: Dict[str, Dict] = {}
        self._by_chinese: Dict[str, Dict] = {}
        self._by_order: Dict[str, List[Dict]] = {}
        self._by_family: Dict[str, List[Dict]] = {}
        self._load()

    def _load(self):
        """Load species database from JSON file."""
        if not self._path.exists():
            self._species = []
            return
        with open(self._path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._species = data.get("species", []) if isinstance(data, dict) else data
        self._build_indices()

    def _build_indices(self):
        """Build lookup indices for fast queries."""
        self._by_scientific = {}
        self._by_chinese = {}
        self._by_order = {}
        self._by_family = {}
        for sp in self._species:
            self._by_scientific[sp["scientific"]] = sp
            self._by_chinese[sp["chinese"]] = sp
            order = sp.get("order", "Unknown")
            family = sp.get("family", "Unknown")
            self._by_order.setdefault(order, []).append(sp)
            self._by_family.setdefault(family, []).append(sp)

    def save(self):
        """Persist current database to JSON."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1.0",
            "total": len(self._species),
            "species": self._species,
        }
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── Queries ──────────────────────────────

    @property
    def count(self) -> int:
        return len(self._species)

    @property
    def all_species(self) -> List[Dict]:
        return self._species

    def get(self, scientific_name: str) -> Optional[Dict]:
        """Lookup by scientific name."""
        return self._by_scientific.get(scientific_name)

    def get_by_chinese(self, chinese_name: str) -> Optional[Dict]:
        """Lookup by Chinese name."""
        return self._by_chinese.get(chinese_name)

    def search(self, query: str, limit: int = 50) -> List[Dict]:
        """Fuzzy search across Chinese, English, and scientific names."""
        q = query.lower().strip()
        if not q:
            return self._species[:limit]
        results = []
        for sp in self._species:
            score = 0
            if q in sp["scientific"].lower():
                score += 3
            if q in sp["chinese"]:
                score += 3
            if q in sp.get("english", "").lower():
                score += 2
            if q in sp.get("family", "").lower():
                score += 1
            if q in sp.get("order", "").lower():
                score += 1
            if score > 0:
                results.append((score, sp))
        results.sort(key=lambda x: -x[0])
        return [sp for _, sp in results[:limit]]

    def list_orders(self) -> List[Tuple[str, str, int]]:
        """List all orders with (order, order_cn, species_count)."""
        result = []
        for order, spp in sorted(self._by_order.items()):
            order_cn = spp[0].get("order_cn", "") if spp else ""
            result.append((order, order_cn, len(spp)))
        return result

    def list_families(self, order: Optional[str] = None) -> List[Tuple[str, str, int]]:
        """List families, optionally filtered by order."""
        if order:
            species = self._by_order.get(order, [])
            families = {}
            for sp in species:
                fam = sp.get("family", "Unknown")
                fam_cn = sp.get("family_cn", "")
                families.setdefault(fam, {"cn": fam_cn, "count": 0})
                families[fam]["count"] += 1
            return [(f, d["cn"], d["count"]) for f, d in sorted(families.items())]
        return [
            (f, spp[0].get("family_cn", ""), len(spp))
            for f, spp in sorted(self._by_family.items())
        ]

    def filter(
        self,
        order: Optional[str] = None,
        family: Optional[str] = None,
        protection: Optional[str] = None,
        iucn: Optional[str] = None,
        has_audio: Optional[bool] = None,
    ) -> List[Dict]:
        """Filter species by multiple criteria."""
        result = self._species
        if order:
            result = [sp for sp in result if sp.get("order") == order]
        if family:
            result = [sp for sp in result if sp.get("family") == family]
        if protection:
            result = [sp for sp in result if sp.get("protection") == protection]
        if iucn:
            result = [sp for sp in result if sp.get("iucn") == iucn]
        if has_audio is not None:
            result = [sp for sp in result if sp.get("has_audio", False) == has_audio]
        return result

    # ── Mutations ────────────────────────────

    def add_species(self, species_data: Dict) -> bool:
        """Add a species entry. Returns False if already exists."""
        if species_data["scientific"] in self._by_scientific:
            return False
        self._species.append(species_data)
        self._build_indices()
        return True

    def update_species(self, scientific_name: str, updates: Dict) -> bool:
        """Update fields of an existing species."""
        sp = self._by_scientific.get(scientific_name)
        if not sp:
            return False
        sp.update(updates)
        self._build_indices()
        return True

    def bulk_import(self, species_list: List[Dict], overwrite: bool = False) -> int:
        """Import a list of species. Returns count of newly added."""
        added = 0
        for sp in species_list:
            if sp["scientific"] in self._by_scientific:
                if overwrite:
                    self.update_species(sp["scientific"], sp)
                    added += 1
            else:
                self._species.append(sp)
                added += 1
        self._build_indices()
        return added

    def filter_by_habitat(self, habitat: str) -> List[Dict]:
        """Filter species by habitat type."""
        return [sp for sp in self._species if habitat in sp.get("habitat", [])]

    def filter_by_vocal_activity(self, activity: str) -> List[Dict]:
        """Filter species by vocal activity period (diurnal/nocturnal/crepuscular)."""
        return [sp for sp in self._species if sp.get("vocal_activity") == activity]

    def get_trait_matrix(self, species_list: Optional[List[str]] = None) -> Dict:
        """Get functional trait matrix for species (for functional diversity calculations).

        Returns dict mapping scientific_name -> {trait: value} for species with trait data.
        """
        trait_keys = [
            "body_mass",
            "wing_length",
            "bill_length",
            "tarsus_length",
            "freq_range_low",
            "freq_range_high",
        ]
        result = {}
        source = (
            (
                self._by_scientific[sp]
                for sp in species_list
                if sp in self._by_scientific
            )
            if species_list
            else self._species
        )
        for sp_data in source:
            sp = sp_data if isinstance(sp_data, dict) else sp_data
            traits = {}
            for key in trait_keys:
                val = sp.get(key)
                if val is not None:
                    traits[key] = float(val)
            if traits:
                result[sp["scientific"]] = traits
        return result

    def get_conservation_summary(self) -> Dict:
        """Get conservation-focused summary of the database."""
        iucn_counts = {}
        prot_counts = {"I": 0, "II": 0, "none": 0}
        endemic_count = 0
        trend_counts = {}
        for sp in self._species:
            iucn = sp.get("iucn", "NE")
            iucn_counts[iucn] = iucn_counts.get(iucn, 0) + 1
            prot = sp.get("protection")
            if prot == "I":
                prot_counts["I"] += 1
            elif prot == "II":
                prot_counts["II"] += 1
            else:
                prot_counts["none"] += 1
            if sp.get("endemic"):
                endemic_count += 1
            trend = sp.get("population_trend", "unknown")
            trend_counts[trend] = trend_counts.get(trend, 0) + 1

        threatened = sum(iucn_counts.get(s, 0) for s in ["CR", "EN", "VU"])
        return {
            "total_species": len(self._species),
            "threatened_species": threatened,
            "endemic_species": endemic_count,
            "iucn_breakdown": iucn_counts,
            "protection_breakdown": prot_counts,
            "population_trends": trend_counts,
        }

    def get_acoustic_profile(self, scientific_name: str) -> Optional[Dict]:
        """Get acoustic characteristics for a species."""
        sp = self._by_scientific.get(scientific_name)
        if not sp:
            return None
        return {
            "species": scientific_name,
            "freq_range_low": sp.get("freq_range_low"),
            "freq_range_high": sp.get("freq_range_high"),
            "peak_freq": sp.get("peak_freq"),
            "call_duration": sp.get("call_duration"),
            "vocal_activity": sp.get("vocal_activity"),
            "song_complexity": sp.get("song_complexity"),
        }

    # ── Compatibility with existing code ─────

    def to_legacy_list(self) -> List[Dict]:
        """Convert to legacy CHINA_BIRD_SPECIES format for backward compatibility."""
        return [
            {
                "scientific": sp["scientific"],
                "chinese": sp["chinese"],
                "english": sp.get("english", ""),
            }
            for sp in self._species
        ]

    def scientific_to_chinese(self) -> Dict[str, str]:
        """Map scientific -> Chinese name."""
        return {sp["scientific"]: sp["chinese"] for sp in self._species}

    def scientific_to_english(self) -> Dict[str, str]:
        """Map scientific -> English name."""
        return {sp["scientific"]: sp.get("english", "") for sp in self._species}


# ──────────────────────────────────────────────
# Singleton instance
# ──────────────────────────────────────────────
import threading

_db_instance: Optional[SpeciesDB] = None
_db_lock = threading.Lock()


def get_species_db(db_path: Optional[str] = None) -> SpeciesDB:
    """Get or create the singleton species database."""
    global _db_instance
    if _db_instance is None:
        with _db_lock:
            if _db_instance is None:
                _db_instance = SpeciesDB(db_path)
    return _db_instance


def reset_species_db():
    """Reset the singleton (useful for testing)."""
    global _db_instance
    _db_instance = None
