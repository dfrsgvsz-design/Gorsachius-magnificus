"""
Biodiversity Analysis Module.
Computes species-based diversity metrics from CNN detection results.

This directly addresses Sugai et al. (2026): use species-level detections
for biodiversity inference, NOT acoustic indices.

Supported metrics:
- Alpha diversity: species richness, Shannon, Simpson, Chao1, Fisher's alpha
- Beta diversity: Jaccard, Sørensen, Bray-Curtis, Whittaker, Turnover/Nestedness
- Functional diversity: based on trait data (Cadotte et al., 2011)
- Species accumulation curves with rarefaction
- Detection frequency and temporal patterns
- Community composition analysis for conservation prioritization

Refs:
- Moreno et al. (2017): Measuring biodiversity in the Anthropocene
- Socolar et al. (2016): Beta-diversity for regional conservation planning
- Cadotte et al. (2011): Functional diversity and ecological processes
"""

import numpy as np
from collections import Counter, defaultdict
from typing import Dict, List, Tuple, Optional

# ──────────────────────────────────────────────
# Alpha Diversity Metrics
# ──────────────────────────────────────────────


def species_richness(detections: List[str]) -> int:
    """Count unique species detected (S)."""
    return len(set(detections))


def shannon_index(detections: List[str]) -> float:
    """
    Shannon-Wiener diversity index (H').
    H' = -Σ(p_i * ln(p_i))
    Higher values indicate greater diversity.
    """
    if not detections:
        return 0.0
    counts = Counter(detections)
    total = sum(counts.values())
    h = 0.0
    for count in counts.values():
        p = count / total
        if p > 0:
            h -= p * np.log(p)
    return float(h)


def simpson_index(detections: List[str]) -> float:
    """
    Simpson's diversity index (1 - D).
    D = Σ(n_i * (n_i - 1)) / (N * (N - 1))
    Returns 1 - D so higher = more diverse.
    """
    if not detections:
        return 0.0
    counts = Counter(detections)
    N = sum(counts.values())
    if N <= 1:
        return 0.0
    D = sum(n * (n - 1) for n in counts.values()) / (N * (N - 1))
    return float(1 - D)


def pielou_evenness(detections: List[str]) -> float:
    """
    Pielou's evenness index (J').
    J' = H' / ln(S)
    Range [0, 1]; 1 = perfectly even distribution.
    """
    S = species_richness(detections)
    if S <= 1:
        return 1.0
    H = shannon_index(detections)
    return float(H / np.log(S))


def chao1_estimator(detections: List[str]) -> float:
    """
    Chao1 species richness estimator.
    Estimates true richness accounting for undetected species.
    Chao1 = S_obs + (f1^2 / (2 * f2))
    where f1 = singletons, f2 = doubletons.
    """
    counts = Counter(detections)
    S_obs = len(counts)
    f1 = sum(1 for c in counts.values() if c == 1)  # singletons
    f2 = sum(1 for c in counts.values() if c == 2)  # doubletons
    if f2 == 0:
        if f1 == 0:
            return float(S_obs)
        return float(S_obs + f1 * (f1 - 1) / 2)
    return float(S_obs + (f1**2) / (2 * f2))


def compute_alpha_diversity(detections: List[str]) -> Dict[str, float]:
    """Compute all alpha diversity metrics."""
    return {
        "species_richness": species_richness(detections),
        "shannon_index": round(shannon_index(detections), 4),
        "simpson_index": round(simpson_index(detections), 4),
        "pielou_evenness": round(pielou_evenness(detections), 4),
        "chao1_estimate": round(chao1_estimator(detections), 2),
        "total_detections": len(detections),
    }


# ──────────────────────────────────────────────
# Beta Diversity Metrics
# ──────────────────────────────────────────────


def jaccard_similarity(site_a: List[str], site_b: List[str]) -> float:
    """
    Jaccard similarity index.
    J = |A ∩ B| / |A ∪ B|
    """
    set_a = set(site_a)
    set_b = set(site_b)
    if not set_a and not set_b:
        return 1.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def sorensen_similarity(site_a: List[str], site_b: List[str]) -> float:
    """
    Sørensen similarity index.
    S = 2|A ∩ B| / (|A| + |B|)
    """
    set_a = set(site_a)
    set_b = set(site_b)
    if not set_a and not set_b:
        return 1.0
    intersection = set_a & set_b
    return 2 * len(intersection) / (len(set_a) + len(set_b))


def bray_curtis_dissimilarity(site_a: List[str], site_b: List[str]) -> float:
    """
    Bray-Curtis dissimilarity index.
    BC = 1 - (2 * Σmin(n_ai, n_bi)) / (Σn_ai + Σn_bi)
    Uses abundance data.
    """
    counts_a = Counter(site_a)
    counts_b = Counter(site_b)
    all_species = set(counts_a.keys()) | set(counts_b.keys())
    if not all_species:
        return 0.0
    sum_min = sum(min(counts_a.get(sp, 0), counts_b.get(sp, 0)) for sp in all_species)
    sum_total = sum(counts_a.values()) + sum(counts_b.values())
    if sum_total == 0:
        return 0.0
    return float(1 - (2 * sum_min) / sum_total)


def compute_beta_diversity(sites: Dict[str, List[str]]) -> Dict:
    """
    Compute pairwise beta diversity between multiple sites.

    Args:
        sites: Dict mapping site_name -> list of species detections

    Returns:
        Dict with pairwise Jaccard, Sørensen, and Bray-Curtis matrices
    """
    site_names = list(sites.keys())
    n = len(site_names)
    jaccard_matrix = np.zeros((n, n))
    sorensen_matrix = np.zeros((n, n))
    bray_curtis_matrix = np.zeros((n, n))

    for i in range(n):
        for j in range(n):
            if i == j:
                jaccard_matrix[i][j] = 1.0
                sorensen_matrix[i][j] = 1.0
                bray_curtis_matrix[i][j] = 0.0
            else:
                jaccard_matrix[i][j] = jaccard_similarity(
                    sites[site_names[i]], sites[site_names[j]]
                )
                sorensen_matrix[i][j] = sorensen_similarity(
                    sites[site_names[i]], sites[site_names[j]]
                )
                bray_curtis_matrix[i][j] = bray_curtis_dissimilarity(
                    sites[site_names[i]], sites[site_names[j]]
                )

    return {
        "site_names": site_names,
        "jaccard": jaccard_matrix.tolist(),
        "sorensen": sorensen_matrix.tolist(),
        "bray_curtis": bray_curtis_matrix.tolist(),
    }


# ──────────────────────────────────────────────
# Species Accumulation Curve
# ──────────────────────────────────────────────


def species_accumulation_curve(
    detections: List[Tuple[float, str]], time_bins: int = 20
) -> Dict:
    """
    Compute species accumulation curve from time-stamped detections.

    Args:
        detections: List of (timestamp_seconds, species_name) tuples
        time_bins: Number of time bins for the curve

    Returns:
        Dict with time_points and cumulative_species arrays
    """
    if not detections:
        return {"time_points": [], "cumulative_species": []}

    sorted_dets = sorted(detections, key=lambda x: x[0])
    max_time = sorted_dets[-1][0]
    if max_time <= 0:
        return {
            "time_points": [0],
            "cumulative_species": [len(set(d[1] for d in detections))],
        }

    bin_width = max_time / time_bins
    time_points = []
    cumulative_species = []
    seen = set()

    for i in range(time_bins):
        t_end = (i + 1) * bin_width
        for ts, sp in sorted_dets:
            if ts <= t_end:
                seen.add(sp)
        time_points.append(round(t_end, 2))
        cumulative_species.append(len(seen))

    return {
        "time_points": time_points,
        "cumulative_species": cumulative_species,
    }


# ──────────────────────────────────────────────
# Detection Summary
# ──────────────────────────────────────────────


def fishers_alpha(detections: List[str], max_iter: int = 100) -> float:
    """Fisher's alpha — a diversity index robust to sample size.

    Solves: S = alpha * ln(1 + N/alpha) via Newton-Raphson.
    """
    counts = Counter(detections)
    S = len(counts)
    N = sum(counts.values())
    if S <= 1 or N <= 1:
        return 0.0
    alpha = S / np.log(N)
    for _ in range(max_iter):
        f = alpha * np.log(1 + N / alpha) - S
        df = np.log(1 + N / alpha) - N / (alpha + N)
        if abs(df) < 1e-12:
            break
        alpha_new = alpha - f / df
        if abs(alpha_new - alpha) < 1e-8:
            alpha = alpha_new
            break
        alpha = max(alpha_new, 0.01)
    return float(alpha)


def whittaker_beta(sites: Dict[str, List[str]]) -> float:
    """Whittaker's beta diversity: gamma / mean_alpha - 1."""
    if len(sites) < 2:
        return 0.0
    all_species = set()
    alpha_values = []
    for sp_list in sites.values():
        sp_set = set(sp_list)
        all_species |= sp_set
        alpha_values.append(len(sp_set))
    gamma = len(all_species)
    mean_alpha = np.mean(alpha_values)
    if mean_alpha == 0:
        return 0.0
    return float(gamma / mean_alpha - 1)


def turnover_nestedness(site_a: List[str], site_b: List[str]) -> Dict[str, float]:
    """Decompose beta diversity into turnover and nestedness components.

    Per Socolar et al. (2016) — important for regional conservation planning.
    """
    a = set(site_a)
    b = set(site_b)
    shared = len(a & b)
    only_a = len(a - b)
    only_b = len(b - a)
    total_beta = (
        1 - (2 * shared) / (2 * shared + only_a + only_b)
        if (shared + only_a + only_b) > 0
        else 0
    )
    min_unshared = min(only_a, only_b)
    turnover = (
        min_unshared / (shared + min_unshared) if (shared + min_unshared) > 0 else 0
    )
    nestedness = total_beta - turnover
    return {
        "total_beta": round(total_beta, 4),
        "turnover": round(turnover, 4),
        "nestedness": round(max(0, nestedness), 4),
    }


def rarefaction_curve(detections: List[str], steps: int = 20) -> Dict:
    """Individual-based rarefaction curve for comparing sites with different effort."""
    if not detections:
        return {"sample_sizes": [], "expected_richness": []}
    N = len(detections)
    counts = Counter(detections)
    S_obs = len(counts)
    sample_sizes = [int(N * (i + 1) / steps) for i in range(steps)]
    sample_sizes = [s for s in sample_sizes if 0 < s <= N]

    expected = []
    for n in sample_sizes:
        if n >= N:
            expected.append(S_obs)
        else:
            E_S = 0
            for ni in counts.values():
                from scipy.special import comb

                E_S += (
                    1 - comb(N - ni, n, exact=False) / comb(N, n, exact=False)
                    if N >= n
                    else S_obs
                )
            expected.append(round(float(E_S), 2))

    return {
        "sample_sizes": sample_sizes,
        "expected_richness": expected,
    }


def functional_diversity(
    detections: List[str], trait_data: Optional[Dict[str, Dict]] = None
) -> Dict:
    """Compute functional diversity metrics from species trait data.

    Per Cadotte et al. (2011) and Moreno et al. (2017), functional diversity
    is a priority for conservation assessment.
    """
    if not trait_data or not detections:
        return {"available": False, "message": "Trait data required"}

    detected_species = list(set(detections))
    species_with_traits = [sp for sp in detected_species if sp in trait_data]

    if len(species_with_traits) < 2:
        return {"available": False, "message": "Need ≥2 species with trait data"}

    trait_keys = list(trait_data[species_with_traits[0]].keys())
    numeric_traits = []
    for sp in species_with_traits:
        vals = []
        for k in trait_keys:
            v = trait_data[sp].get(k, 0)
            vals.append(float(v) if isinstance(v, (int, float)) else 0.0)
        numeric_traits.append(vals)

    trait_matrix = np.array(numeric_traits)
    if trait_matrix.shape[1] == 0:
        return {"available": False, "message": "No numeric traits found"}

    col_std = trait_matrix.std(axis=0)
    col_std[col_std == 0] = 1
    normed = (trait_matrix - trait_matrix.mean(axis=0)) / col_std

    from scipy.spatial.distance import pdist, squareform

    dists = squareform(pdist(normed, metric="euclidean"))

    fric = float(np.sum(np.max(normed, axis=0) - np.min(normed, axis=0)))
    n = len(species_with_traits)
    feve = 0.0
    if n > 1:
        min_spanning_dists = []
        visited = {0}
        for _ in range(n - 1):
            min_d = float("inf")
            for v in visited:
                for u in range(n):
                    if u not in visited and dists[v][u] < min_d:
                        min_d = dists[v][u]
                        next_u = u
            visited.add(next_u)
            min_spanning_dists.append(min_d)
        total = sum(min_spanning_dists)
        if total > 0:
            pew = [d / total for d in min_spanning_dists]
            S = len(pew)
            feve = (
                float((sum(min(p, 1 / S) for p in pew) - 1 / S) / (1 - 1 / S))
                if S > 1
                else 1.0
            )

    weights = np.array(
        [Counter(detections)[sp] for sp in species_with_traits], dtype=float
    )
    weights /= weights.sum()
    fdis = float(np.sum(weights[:, None] * weights[None, :] * dists))

    return {
        "available": True,
        "n_species_with_traits": len(species_with_traits),
        "trait_dimensions": trait_keys,
        "functional_richness": round(fric, 4),
        "functional_evenness": round(feve, 4),
        "functional_dispersion": round(fdis, 4),
    }


def conservation_priority_score(detections: List[Dict], species_db_lookup=None) -> Dict:
    """Score detected species for conservation relevance.

    Prioritizes: IUCN threat level, national protection status,
    endemism, and detection reliability.
    """
    iucn_weights = {"CR": 5, "EN": 4, "VU": 3, "NT": 2, "LC": 1, "DD": 1, "NE": 0}
    protection_weights = {"I": 5, "II": 3}

    species_list = list(
        set(d.get("species", d.get("species_scientific", "")) for d in detections)
    )
    scored = []
    for sp in species_list:
        info = species_db_lookup(sp) if species_db_lookup else None
        iucn = info.get("iucn", "NE") if info else "NE"
        prot = info.get("protection") if info else None
        sp_dets = [
            d
            for d in detections
            if d.get("species", d.get("species_scientific", "")) == sp
        ]
        avg_conf = np.mean([d["confidence"] for d in sp_dets])
        reliable_count = sum(1 for d in sp_dets if d.get("reliable", True))

        priority = (
            iucn_weights.get(iucn, 0) * 2
            + protection_weights.get(prot, 0) * 2
            + min(reliable_count, 5)
        )
        scored.append(
            {
                "species": sp,
                "iucn": iucn,
                "protection": prot,
                "detections": len(sp_dets),
                "avg_confidence": round(float(avg_conf), 4),
                "reliable_detections": reliable_count,
                "conservation_score": priority,
            }
        )

    scored.sort(key=lambda x: -x["conservation_score"])
    return {
        "total_species": len(scored),
        "high_priority": [s for s in scored if s["conservation_score"] >= 8],
        "all_scores": scored,
    }


def detection_summary(detections: List[Dict]) -> Dict:
    """
    Summarize detection results from CNN predictions.

    Enhanced with functional diversity readiness and conservation scoring.

    Args:
        detections: List of {species, confidence, time_offset} dicts

    Returns:
        Summary statistics and per-species breakdown
    """
    if not detections:
        return {
            "total_detections": 0,
            "unique_species": 0,
            "species_breakdown": [],
            "alpha_diversity": compute_alpha_diversity([]),
        }

    species_list = [d["species"] for d in detections]
    species_counts = Counter(species_list)

    species_stats = []
    for sp, count in species_counts.most_common():
        sp_dets = [d for d in detections if d["species"] == sp]
        confidences = [d["confidence"] for d in sp_dets]
        reliable_dets = [d for d in sp_dets if d.get("reliable", True)]
        species_stats.append(
            {
                "species": sp,
                "count": count,
                "reliable_count": len(reliable_dets),
                "avg_confidence": round(np.mean(confidences), 4),
                "max_confidence": round(max(confidences), 4),
                "min_confidence": round(min(confidences), 4),
                "first_detection_time": round(
                    min(d["time_offset"] for d in sp_dets), 2
                ),
            }
        )

    timed = [(d["time_offset"], d["species"]) for d in detections]
    acc_curve = species_accumulation_curve(timed)
    alpha = compute_alpha_diversity(species_list)
    alpha["fishers_alpha"] = round(fishers_alpha(species_list), 4)

    return {
        "total_detections": len(detections),
        "unique_species": len(species_counts),
        "reliable_detections": sum(1 for d in detections if d.get("reliable", True)),
        "species_breakdown": species_stats,
        "alpha_diversity": alpha,
        "accumulation_curve": acc_curve,
        "rarefaction": rarefaction_curve(species_list),
    }
