"""Single-season occupancy model engine.

Implements the MacKenzie et al. (2002) occupancy model via EM algorithm
to estimate true occupancy probability (psi) corrected for imperfect
detection probability (p).
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class OccupancyEngine:
    def __init__(self, detection_store=None):
        self.store = detection_store

    def build_detection_history(
        self,
        species: str,
        sites: list[str],
        n_surveys: int = 6,
        survey_duration_days: int = 7,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> np.ndarray:
        """Construct a site × survey detection history matrix.

        Each cell is 1 if species was detected at the site during that
        survey window, 0 otherwise.
        """
        if not self.store:
            return np.zeros((len(sites), n_surveys), dtype=int)

        all_dets = self.store.get_all_detections()

        site_dets: dict[str, list[datetime]] = defaultdict(list)
        for det in all_dets:
            sp = det.get("species_scientific") or det.get("species", "")
            if sp != species:
                continue
            site = det.get("site_name", "")
            ts = det.get("detected_at", "")
            if not site or not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            if start_date and ts < start_date:
                continue
            if end_date and ts > end_date:
                continue
            site_dets[site].append(dt)

        if not site_dets and not start_date:
            return np.zeros((len(sites), n_surveys), dtype=int)

        all_dates = [dt for dts in site_dets.values() for dt in dts]
        if start_date:
            global_start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        elif all_dates:
            global_start = min(all_dates)
        else:
            global_start = datetime.now()

        history = np.zeros((len(sites), n_surveys), dtype=int)
        for i, site in enumerate(sites):
            dets = site_dets.get(site, [])
            for j in range(n_surveys):
                window_start = global_start + timedelta(days=j * survey_duration_days)
                window_end = window_start + timedelta(days=survey_duration_days)
                if any(window_start <= d < window_end for d in dets):
                    history[i, j] = 1

        return history

    def fit_single_season(
        self,
        detection_history: np.ndarray,
        max_iter: int = 300,
        tol: float = 1e-7,
    ) -> dict:
        """Fit a single-season occupancy model using the EM algorithm."""
        n_sites, n_surveys = detection_history.shape
        if n_sites == 0 or n_surveys == 0:
            return {"error": "Empty detection history"}

        psi = 0.5
        p = 0.3

        for iteration in range(max_iter):
            posterior = np.zeros(n_sites)
            for i in range(n_sites):
                n_det = int(detection_history[i].sum())
                if n_det > 0:
                    posterior[i] = 1.0
                else:
                    prob_present = psi * (1 - p) ** n_surveys
                    prob_absent = 1 - psi
                    denom = prob_present + prob_absent
                    posterior[i] = prob_present / denom if denom > 0 else 0.0

            psi_new = float(posterior.mean())
            total_posterior_surveys = posterior.sum() * n_surveys
            p_new = (
                float(detection_history.sum() / total_posterior_surveys)
                if total_posterior_surveys > 0
                else 0.0
            )
            p_new = max(0.001, min(0.999, p_new))
            psi_new = max(0.001, min(0.999, psi_new))

            if abs(psi_new - psi) < tol and abs(p_new - p) < tol:
                psi, p = psi_new, p_new
                break
            psi, p = psi_new, p_new

        naive = float((detection_history.sum(axis=1) > 0).mean())

        return {
            "psi": round(psi, 4),
            "p": round(p, 4),
            "n_sites": n_sites,
            "n_surveys": n_surveys,
            "naive_occupancy": round(naive, 4),
            "occupancy_corrected": round(psi, 4),
            "detection_probability": round(p, 4),
            "convergence_iterations": iteration + 1,
        }

    def analyze(
        self,
        species: str,
        n_surveys: int = 6,
        survey_duration_days: int = 7,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict:
        """Full occupancy analysis pipeline for a given species."""
        if not self.store:
            return {"error": "No detection store available"}

        sites_data = self.store.get_all_detections()
        site_names = sorted(
            {d.get("site_name", "") for d in sites_data if d.get("site_name")}
        )

        if len(site_names) < 2:
            return {
                "error": "Need at least 2 survey sites for occupancy modeling",
                "sites_found": len(site_names),
            }

        history = self.build_detection_history(
            species,
            site_names,
            n_surveys,
            survey_duration_days,
            start_date,
            end_date,
        )

        result = self.fit_single_season(history)
        if "error" in result:
            return result

        site_results = []
        for i, site in enumerate(site_names):
            n_det = int(history[i].sum())
            if n_det > 0:
                occ_prob = 1.0
            else:
                prob_present = result["psi"] * (1 - result["p"]) ** n_surveys
                prob_absent = 1 - result["psi"]
                denom = prob_present + prob_absent
                occ_prob = prob_present / denom if denom > 0 else 0.0

            site_results.append(
                {
                    "site": site,
                    "occupancy_probability": round(occ_prob, 4),
                    "n_detections": n_det,
                    "detected": n_det > 0,
                }
            )

        result["species"] = species
        result["sites"] = site_results
        return result

    def suggest_verification_targets(
        self, analysis_result: dict, n_targets: int = 10
    ) -> list:
        """Recommend sites/detections for priority human verification."""
        sites = analysis_result.get("sites", [])
        uncertain = sorted(sites, key=lambda s: abs(s["occupancy_probability"] - 0.5))
        targets = []
        for site in uncertain[:n_targets]:
            targets.append(
                {
                    "site": site["site"],
                    "occupancy_probability": site["occupancy_probability"],
                    "priority": (
                        "high"
                        if abs(site["occupancy_probability"] - 0.5) < 0.2
                        else "medium"
                    ),
                    "reason": "Uncertain occupancy status — verification would be most informative here",
                }
            )
        return targets
