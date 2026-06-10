"""
Comprehensive Biodiversity Index Calculator.
Computes diversity indices from multi-modal detection sources:
acoustic detections, image records, and camera trap events.
"""

import math
from collections import Counter
from typing import Dict, List, Optional


def shannon_index(species_counts: Dict[str, int]) -> float:
    """Shannon-Wiener diversity index H'."""
    total = sum(species_counts.values())
    if total == 0:
        return 0.0
    h = 0.0
    for count in species_counts.values():
        if count > 0:
            p = count / total
            h -= p * math.log(p)
    return round(h, 4)


def simpson_index(species_counts: Dict[str, int]) -> float:
    """Simpson's diversity index (1 - D)."""
    total = sum(species_counts.values())
    if total <= 1:
        return 0.0
    d = sum(n * (n - 1) for n in species_counts.values()) / (total * (total - 1))
    return round(1 - d, 4)


def pielou_evenness(species_counts: Dict[str, int]) -> float:
    """Pielou's evenness index J'."""
    s = len([c for c in species_counts.values() if c > 0])
    if s <= 1:
        return 0.0
    h = shannon_index(species_counts)
    return round(h / math.log(s), 4) if math.log(s) > 0 else 0.0


def chao1_estimate(species_counts: Dict[str, int]) -> float:
    """Chao1 species richness estimator."""
    s_obs = len([c for c in species_counts.values() if c > 0])
    f1 = len([c for c in species_counts.values() if c == 1])
    f2 = len([c for c in species_counts.values() if c == 2])
    if f2 == 0:
        return round(s_obs + f1 * (f1 - 1) / 2, 2) if f1 > 0 else float(s_obs)
    return round(s_obs + f1 * f1 / (2 * f2), 2)


def margalef_richness(species_counts: Dict[str, int]) -> float:
    """Margalef richness index."""
    s = len([c for c in species_counts.values() if c > 0])
    n = sum(species_counts.values())
    if n <= 1:
        return 0.0
    return round((s - 1) / math.log(n), 4)


def berger_parker_dominance(species_counts: Dict[str, int]) -> float:
    """Berger-Parker dominance index (proportion of most abundant species)."""
    total = sum(species_counts.values())
    if total == 0:
        return 0.0
    return round(max(species_counts.values()) / total, 4)


def sorensen_similarity(site_a: set, site_b: set) -> float:
    """Sorensen similarity between two sites (beta diversity)."""
    if not site_a and not site_b:
        return 0.0
    shared = len(site_a & site_b)
    return round(2 * shared / (len(site_a) + len(site_b)), 4)


def jaccard_similarity(site_a: set, site_b: set) -> float:
    """Jaccard similarity between two sites."""
    union = site_a | site_b
    if not union:
        return 0.0
    return round(len(site_a & site_b) / len(union), 4)


def compute_comprehensive_indices(
    acoustic_detections: List[dict] = None,
    image_records: List[dict] = None,
    camera_trap_events: List[dict] = None,
    site_name: Optional[str] = None,
) -> dict:
    """Compute biodiversity indices from all available data sources.

    Each input is a list of records with at least a 'species' or 'top_classification' field.
    """
    species_counter = Counter()
    source_counts = {"acoustic": 0, "image": 0, "camera_trap": 0}

    for det in acoustic_detections or []:
        sp = det.get("species") or det.get("species_scientific")
        if sp:
            species_counter[sp] += 1
            source_counts["acoustic"] += 1

    for rec in image_records or []:
        for pred in rec.get("bird_predictions", []):
            label = pred.get("label")
            if label and pred.get("confidence", 0) >= 0.3:
                species_counter[label] += 1
                source_counts["image"] += 1

    for evt in camera_trap_events or []:
        for det in evt.get("detections", []):
            cat = det.get("category")
            if cat:
                species_counter[cat] += 1
                source_counts["camera_trap"] += 1

    counts = dict(species_counter)
    total_individuals = sum(counts.values())
    species_richness = len([c for c in counts.values() if c > 0])

    result = {
        "site_name": site_name,
        "total_species": species_richness,
        "total_individuals": total_individuals,
        "species_counts": counts,
        "source_breakdown": source_counts,
        "alpha_diversity": {
            "species_richness": species_richness,
            "shannon_index": shannon_index(counts),
            "simpson_index": simpson_index(counts),
            "pielou_evenness": pielou_evenness(counts),
            "chao1_estimate": chao1_estimate(counts),
            "margalef_richness": margalef_richness(counts),
            "berger_parker_dominance": berger_parker_dominance(counts),
        },
        "dominant_species": sorted(counts.items(), key=lambda x: x[1], reverse=True)[
            :10
        ],
    }

    return result


def compute_multi_site_beta(site_data: Dict[str, set]) -> dict:
    """Compute beta diversity (Sorensen & Jaccard) between all pairs of sites."""
    sites = list(site_data.keys())
    pairwise = []
    for i in range(len(sites)):
        for j in range(i + 1, len(sites)):
            a, b = sites[i], sites[j]
            pairwise.append(
                {
                    "site_a": a,
                    "site_b": b,
                    "shared_species": len(site_data[a] & site_data[b]),
                    "unique_to_a": len(site_data[a] - site_data[b]),
                    "unique_to_b": len(site_data[b] - site_data[a]),
                    "sorensen": sorensen_similarity(site_data[a], site_data[b]),
                    "jaccard": jaccard_similarity(site_data[a], site_data[b]),
                }
            )

    all_species = set()
    for sp_set in site_data.values():
        all_species |= sp_set

    return {
        "total_sites": len(sites),
        "gamma_diversity": len(all_species),
        "mean_alpha": round(
            sum(len(s) for s in site_data.values()) / max(len(sites), 1), 1
        ),
        "pairwise_comparisons": pairwise,
    }
