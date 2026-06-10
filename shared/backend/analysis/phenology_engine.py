"""Acoustic phenology analysis engine.

Extracts seasonal vocal activity patterns from long-term detection data:
  - First/last detection dates
  - Peak activity periods
  - Hourly activity patterns
  - Cross-year phenological shift detection
"""

import logging
from collections import defaultdict
from datetime import datetime
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


def _smooth(values: list, window: int = 7) -> list:
    if len(values) < window:
        return values
    arr = np.array(values, dtype=float)
    kernel = np.ones(window) / window
    padded = np.pad(arr, window // 2, mode="edge")
    return np.convolve(padded, kernel, mode="valid")[: len(values)].tolist()


class PhenologyEngine:
    def __init__(self, detection_store=None):
        self.store = detection_store

    def compute_phenometrics(
        self, species: str, year: int, detections: Optional[list] = None
    ) -> dict:
        """Extract phenology metrics for one species in one year."""
        if detections is None and self.store:
            detections = self.store.get_all_detections()

        daily: dict[int, int] = defaultdict(int)
        hourly: dict[int, int] = defaultdict(int)

        for det in detections or []:
            sp = det.get("species_scientific") or det.get("species", "")
            if sp != species:
                continue
            ts = det.get("detected_at", "")
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            if dt.year != year:
                continue
            doy = dt.timetuple().tm_yday
            daily[doy] += 1
            hourly[dt.hour] += 1

        if not daily:
            return {"species": species, "year": year, "status": "no_data"}

        days_sorted = sorted(daily.keys())
        counts = [daily[d] for d in days_sorted]
        smoothed = _smooth(counts)

        peak_idx = int(np.argmax(smoothed))
        threshold = max(smoothed) * 0.1
        active = [d for d, c in zip(days_sorted, smoothed) if c >= threshold]

        return {
            "species": species,
            "year": year,
            "status": "ok",
            "first_detection_doy": active[0] if active else days_sorted[0],
            "last_detection_doy": active[-1] if active else days_sorted[-1],
            "peak_doy": days_sorted[peak_idx],
            "season_length_days": (active[-1] - active[0]) if len(active) >= 2 else 0,
            "total_detections": sum(counts),
            "daily_curve": {str(d): round(c, 2) for d, c in zip(days_sorted, smoothed)},
            "hourly_pattern": dict(hourly),
        }

    def detect_phenological_shift(
        self, species: str, years: list, detections: Optional[list] = None
    ) -> dict:
        """Detect multi-year trend in vocal onset / peak timing."""
        metrics = []
        for y in sorted(years):
            m = self.compute_phenometrics(species, y, detections)
            if m.get("status") == "ok":
                metrics.append(m)

        if len(metrics) < 2:
            return {
                "species": species,
                "trend": "insufficient_data",
                "years_available": len(metrics),
            }

        yrs = np.array([m["year"] for m in metrics], dtype=float)
        first_doys = np.array([m["first_detection_doy"] for m in metrics], dtype=float)
        peak_doys = np.array([m["peak_doy"] for m in metrics], dtype=float)

        slope_first, p_first = self._linear_trend(yrs, first_doys)
        slope_peak, p_peak = self._linear_trend(yrs, peak_doys)

        interpretation = "stable"
        if p_first < 0.1:
            interpretation = "advancing" if slope_first < 0 else "delaying"

        return {
            "species": species,
            "years_analyzed": [int(y) for y in yrs],
            "first_detection_trend_days_per_year": round(slope_first, 2),
            "first_detection_p_value": round(p_first, 4),
            "peak_trend_days_per_year": round(slope_peak, 2),
            "peak_p_value": round(p_peak, 4),
            "interpretation": interpretation,
            "per_year": metrics,
        }

    @staticmethod
    def _linear_trend(x: np.ndarray, y: np.ndarray) -> tuple:
        if len(x) < 2:
            return 0.0, 1.0
        try:
            from scipy.stats import linregress

            res = linregress(x, y)
            return float(res.slope), float(res.pvalue)
        except Exception:
            n = len(x)
            mx, my = x.mean(), y.mean()
            ss_xy = ((x - mx) * (y - my)).sum()
            ss_xx = ((x - mx) ** 2).sum()
            if ss_xx == 0:
                return 0.0, 1.0
            slope = ss_xy / ss_xx
            y_pred = mx + slope * (x - mx) + my
            ss_res = ((y - y_pred) ** 2).sum()
            ss_tot = ((y - my) ** 2).sum()
            if ss_tot == 0:
                return float(slope), 1.0
            r2 = 1 - ss_res / ss_tot
            return float(slope), 1.0 - abs(r2)

    def get_species_overview(
        self, year: int, detections: Optional[list] = None
    ) -> list:
        """Summary phenometrics for all detected species in a given year."""
        if detections is None and self.store:
            detections = self.store.get_all_detections()

        species_set: set = set()
        for det in detections or []:
            sp = det.get("species_scientific") or det.get("species", "")
            ts = det.get("detected_at", "")
            if sp and ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if dt.year == year:
                        species_set.add(sp)
                except (ValueError, TypeError):
                    pass

        results = []
        for sp in sorted(species_set):
            m = self.compute_phenometrics(sp, year, detections)
            if m.get("status") == "ok":
                results.append(m)
        return results
