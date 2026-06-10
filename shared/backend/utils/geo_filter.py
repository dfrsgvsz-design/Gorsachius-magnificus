"""
Geographic & Seasonal Species Filter — 参考 BirdNET 的地理过滤设计

BirdNET 利用 eBird 分布数据，根据经纬度和日期缩小候选物种范围，
显著减少误报。我们基于 species_db 中的 regions 和 resident 字段实现类似功能。

用法:
    filter = GeoSeasonalFilter(species_db)
    candidates = filter.get_candidates(lat=23.1, lon=108.3, month=6)
    # → 返回该时间该地点可能出现的物种列表
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Set

logger = logging.getLogger("bird_platform")

CHINA_REGIONS = {
    "华南": {"lat_range": (18, 26.5), "lon_range": (104, 120)},
    "华东": {"lat_range": (25, 35), "lon_range": (115, 123)},
    "华中": {"lat_range": (26, 35), "lon_range": (108, 117)},
    "华北": {"lat_range": (34, 43), "lon_range": (110, 120)},
    "东北": {"lat_range": (38, 54), "lon_range": (118, 135)},
    "西南": {"lat_range": (21, 34), "lon_range": (97, 110)},
    "西北": {"lat_range": (32, 49), "lon_range": (73, 111)},
    "台湾": {"lat_range": (21.5, 25.5), "lon_range": (119.5, 122.5)},
    "海南": {"lat_range": (18, 20.2), "lon_range": (108.5, 111.5)},
    "青藏": {"lat_range": (26, 40), "lon_range": (73, 104)},
}

SEASON_MONTH_MAP = {
    "resident": set(range(1, 13)),
    "summer": {4, 5, 6, 7, 8, 9},
    "winter": {10, 11, 12, 1, 2, 3},
    "passage": {3, 4, 5, 9, 10, 11},
}


class GeoSeasonalFilter:
    """Filter candidate species by geographic location and season."""

    def __init__(self, species_db=None):
        self._species_db = species_db
        self._region_cache: Dict[str, Set[str]] = {}
        self._build_cache()

    def _build_cache(self):
        if not self._species_db:
            return
        for sp in self._species_db.all_species:
            regions = sp.get("regions", [])
            sci_name = sp["scientific"]
            for region in regions:
                if region not in self._region_cache:
                    self._region_cache[region] = set()
                self._region_cache[region].add(sci_name)

    def _lat_lon_to_regions(self, lat: float, lon: float) -> List[str]:
        """Map latitude/longitude to Chinese region names."""
        matched = []
        for region, bounds in CHINA_REGIONS.items():
            lat_min, lat_max = bounds["lat_range"]
            lon_min, lon_max = bounds["lon_range"]
            if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
                matched.append(region)
        return matched

    def get_candidates(
        self,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        month: Optional[int] = None,
        date: Optional[datetime] = None,
    ) -> Optional[List[str]]:
        """Get candidate species for a given location and time.

        Returns None if filtering cannot be applied (no species_db or no location).
        Returns a list of scientific names if filtering is possible.
        """
        if not self._species_db or self._species_db.count == 0:
            return None

        if month is None and date is not None:
            month = date.month

        all_species = self._species_db.all_species
        candidates = set()

        if lat is not None and lon is not None:
            regions = self._lat_lon_to_regions(lat, lon)
            if regions:
                for region in regions:
                    candidates |= self._region_cache.get(region, set())
                species_without_region = {
                    sp["scientific"] for sp in all_species if not sp.get("regions")
                }
                candidates |= species_without_region
            else:
                candidates = {sp["scientific"] for sp in all_species}
        else:
            candidates = {sp["scientific"] for sp in all_species}

        if month is not None:
            seasonal_candidates = set()
            for sp in all_species:
                if sp["scientific"] not in candidates:
                    continue
                resident_type = sp.get("resident", "resident")
                valid_months = SEASON_MONTH_MAP.get(resident_type, set(range(1, 13)))
                if month in valid_months:
                    seasonal_candidates.add(sp["scientific"])
            candidates = seasonal_candidates

        return sorted(candidates)

    def filter_predictions(
        self,
        predictions: List[Dict],
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        month: Optional[int] = None,
    ) -> List[Dict]:
        """Filter CNN predictions to only include geographically/seasonally plausible species.

        Predictions for species outside the candidate list get their confidence reduced
        but are not removed (to avoid masking genuine rare detections).
        """
        candidates = self.get_candidates(lat, lon, month)
        if candidates is None:
            return predictions

        candidate_set = set(candidates)
        filtered = []
        for pred in predictions:
            species = pred.get("species_scientific", pred.get("species", ""))
            if species in candidate_set:
                filtered.append(pred)
            else:
                reduced = dict(pred)
                reduced["confidence"] = round(pred["confidence"] * 0.3, 4)
                reduced["geo_filtered"] = True
                filtered.append(reduced)

        return filtered

    def get_info(self, lat: float, lon: float, month: Optional[int] = None) -> Dict:
        """Get filter info for a location."""
        regions = self._lat_lon_to_regions(lat, lon)
        candidates = self.get_candidates(lat, lon, month)
        return {
            "latitude": lat,
            "longitude": lon,
            "month": month,
            "regions": regions,
            "candidate_species_count": len(candidates) if candidates else 0,
            "total_species": self._species_db.count if self._species_db else 0,
            "reduction_ratio": (
                round(1 - len(candidates) / self._species_db.count, 3)
                if candidates and self._species_db and self._species_db.count > 0
                else 0
            ),
        }


_filter: Optional[GeoSeasonalFilter] = None


def get_geo_filter(species_db=None) -> GeoSeasonalFilter:
    global _filter
    if _filter is None:
        _filter = GeoSeasonalFilter(species_db)
    return _filter
