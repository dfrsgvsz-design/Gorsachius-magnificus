"""Soundscape index computation and ecosystem health scoring.

Computes standard ecoacoustic indices (ACI, NDSI, ADI, BIO, H) from audio
recordings and provides health scoring relative to site-specific baselines.
"""

import json
import logging
import math
from collections import defaultdict
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

_BASELINES_DIR = Path(__file__).parent / "data" / "soundscape_baselines"


def _safe_log(x: float) -> float:
    return math.log(x) if x > 0 else 0.0


class SoundscapeAnalyzer:
    def compute_indices(self, audio: np.ndarray, sr: int = 48000) -> dict:
        """Compute a suite of ecoacoustic indices from raw audio."""
        try:
            import librosa
        except ImportError:
            return {"error": "librosa not available"}

        S = np.abs(librosa.stft(audio, n_fft=2048, hop_length=512)) ** 2
        freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
        S_db = librosa.power_to_db(S, ref=np.max)

        return {
            "aci": self._acoustic_complexity_index(S_db),
            "ndsi": self._ndsi(S, freqs),
            "adi": self._acoustic_diversity_index(S, freqs),
            "bio": self._bioacoustic_index(S, freqs, fmin=2000, fmax=11000),
            "h": self._spectral_entropy(S),
            "evenness": self._acoustic_evenness(S, freqs),
        }

    def _acoustic_complexity_index(self, S_db: np.ndarray) -> float:
        if S_db.shape[1] < 2:
            return 0.0
        diff = np.abs(np.diff(S_db, axis=1))
        total = np.abs(S_db[:, 1:]).sum()
        return float(diff.sum() / total) if total > 0 else 0.0

    def _ndsi(self, S: np.ndarray, freqs: np.ndarray) -> float:
        bio_mask = (freqs >= 2000) & (freqs <= 11000)
        anthro_mask = (freqs >= 1000) & (freqs < 2000)
        bio_energy = float(S[bio_mask].sum())
        anthro_energy = float(S[anthro_mask].sum())
        denom = bio_energy + anthro_energy
        return (bio_energy - anthro_energy) / denom if denom > 0 else 0.0

    def _acoustic_diversity_index(self, S: np.ndarray, freqs: np.ndarray) -> float:
        n_bands = 10
        fmax = freqs[-1] if len(freqs) > 0 else 24000
        band_edges = np.linspace(0, fmax, n_bands + 1)
        proportions = []
        for i in range(n_bands):
            mask = (freqs >= band_edges[i]) & (freqs < band_edges[i + 1])
            proportions.append(float(S[mask].sum()))
        total = sum(proportions)
        if total == 0:
            return 0.0
        proportions = [p / total for p in proportions]
        return -sum(p * _safe_log(p) for p in proportions if p > 0)

    def _bioacoustic_index(
        self, S: np.ndarray, freqs: np.ndarray, fmin: float = 2000, fmax: float = 11000
    ) -> float:
        mask = (freqs >= fmin) & (freqs <= fmax)
        bio_band = S[mask]
        if bio_band.size == 0:
            return 0.0
        import librosa

        bio_db = librosa.power_to_db(bio_band, ref=np.max)
        min_val = bio_db.min()
        return float((bio_db - min_val).sum())

    def _spectral_entropy(self, S: np.ndarray) -> float:
        power = S.mean(axis=1)
        total = power.sum()
        if total == 0:
            return 0.0
        p = power / total
        return float(-np.sum(p * np.log2(p + 1e-12)))

    def _acoustic_evenness(self, S: np.ndarray, freqs: np.ndarray) -> float:
        n_bands = 10
        fmax = freqs[-1] if len(freqs) > 0 else 24000
        band_edges = np.linspace(0, fmax, n_bands + 1)
        band_energies = []
        for i in range(n_bands):
            mask = (freqs >= band_edges[i]) & (freqs < band_edges[i + 1])
            band_energies.append(float(S[mask].sum()))
        total = sum(band_energies)
        if total == 0:
            return 0.0
        proportions = [e / total for e in band_energies]
        gini = sum(
            abs(proportions[i] - proportions[j])
            for i in range(n_bands)
            for j in range(i + 1, n_bands)
        )
        return float(gini / (2 * n_bands * max(sum(proportions), 1e-12)))

    def compute_health_score(self, indices: dict, baseline: dict) -> dict:
        """Score current indices against a site-specific baseline (0-100 scale)."""
        scores = {}
        for key in ["aci", "ndsi", "bio", "adi", "h"]:
            if key not in indices or key not in baseline:
                continue
            ref = baseline[key]
            if not isinstance(ref, dict) or ref.get("std", 0) == 0:
                continue
            z = (indices[key] - ref["mean"]) / ref["std"]
            score = max(0.0, min(100.0, 50 + z * 15))
            scores[key] = round(score, 1)

        if not scores:
            return {"overall_score": None, "status": "no_baseline"}

        overall = round(sum(scores.values()) / len(scores), 1)
        return {
            "overall_score": overall,
            "index_scores": scores,
            "status": self._classify(overall),
        }

    @staticmethod
    def _classify(score: float) -> str:
        if score >= 75:
            return "healthy"
        if score >= 50:
            return "moderate"
        if score >= 25:
            return "degraded"
        return "severely_degraded"

    def save_baseline(self, site_name: str, recordings_indices: list[dict]):
        """Compute and persist a baseline from multiple reference recordings."""
        _BASELINES_DIR.mkdir(parents=True, exist_ok=True)
        agg: dict[str, list] = defaultdict(list)
        for idx in recordings_indices:
            for key in ["aci", "ndsi", "bio", "adi", "h", "evenness"]:
                if key in idx and isinstance(idx[key], (int, float)):
                    agg[key].append(idx[key])

        baseline = {}
        for key, vals in agg.items():
            arr = np.array(vals)
            baseline[key] = {
                "mean": round(float(arr.mean()), 6),
                "std": round(float(arr.std()), 6),
            }

        path = _BASELINES_DIR / f"{site_name}.json"
        path.write_text(json.dumps(baseline, indent=2), encoding="utf-8")
        return baseline

    def load_baseline(self, site_name: str) -> Optional[dict]:
        path = _BASELINES_DIR / f"{site_name}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
