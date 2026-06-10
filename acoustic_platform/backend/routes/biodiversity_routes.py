"""Biodiversity indices, diversity calculations, and conservation priority endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

import main as _main
from models.schemas import CompareSitesRequest

router = APIRouter()


@router.get("/api/biodiversity/comprehensive", tags=["Biodiversity"])
async def comprehensive_biodiversity(
    site_name: Optional[str] = Query(default=None),
):
    """Compute comprehensive biodiversity indices from all data sources."""
    acoustic = _main.det_store.get_all_detections() if _main.det_store else []
    if site_name and acoustic:
        acoustic = [d for d in acoustic if d.get("site_name") == site_name]

    images = [
        r for r in _main._image_records if not site_name or r.get("site_name") == site_name
    ]
    traps = [
        r for r in _main._trap_records if not site_name or r.get("site_name") == site_name
    ]

    result = _main.compute_comprehensive_indices(
        acoustic_detections=acoustic,
        image_records=images,
        camera_trap_events=traps,
        site_name=site_name,
    )
    return result


@router.get("/api/biodiversity/multi-site", tags=["Biodiversity"])
async def multi_site_biodiversity():
    """Compute beta diversity across all survey sites."""
    all_detections = _main.det_store.get_all_detections() if _main.det_store else []
    site_species: dict = {}
    for det in all_detections:
        site = det.get("site_name", "unknown")
        sp = det.get("species") or det.get("species_scientific")
        if sp:
            site_species.setdefault(site, set()).add(sp)

    for rec in _main._image_records:
        site = rec.get("site_name", "unknown")
        for pred in rec.get("bird_predictions", []):
            if pred.get("label"):
                site_species.setdefault(site, set()).add(pred["label"])

    for rec in _main._trap_records:
        site = rec.get("site_name", "unknown")
        for det in rec.get("detections", []):
            if det.get("category"):
                site_species.setdefault(site, set()).add(det["category"])

    if len(site_species) < 2:
        raise HTTPException(
            status_code=422,
            detail="Need at least 2 sites with detections for beta diversity",
        )

    return _main.compute_multi_site_beta(site_species)


@router.post("/api/compare-sites", tags=["Diversity"])
async def compare_sites(req: CompareSitesRequest):
    """Compute beta diversity between multiple monitoring sites."""
    if len(req.sites) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 sites")

    sites = {s.site_name: s.species for s in req.sites}

    alpha = {}
    for name, species in sites.items():
        alpha[name] = _main.compute_alpha_diversity(species)

    beta = _main.compute_beta_diversity(sites)

    return {
        "num_sites": len(sites),
        "alpha_diversity": alpha,
        "beta_diversity": beta,
    }


@router.get("/api/diversity/{session_id}")
async def get_diversity_metrics(session_id: str):
    """Get biodiversity metrics for a detection session."""
    if session_id not in _main.detection_history:
        raise HTTPException(status_code=404, detail="Session not found")

    detections = _main.detection_history[session_id]
    summary = _main.detection_summary(detections)
    return {"session_id": session_id, **summary}


@router.post("/api/diversity/functional", tags=["Diversity"])
async def compute_functional_diversity(req: CompareSitesRequest):
    """Compute functional diversity from species trait data."""
    from shared.backend.analysis.biodiversity import functional_diversity as fd_compute

    trait_lookup = {}
    if _main.species_db:
        for sp in _main.species_db.all_species:
            traits = {}
            if sp.get("body_mass"):
                traits["body_mass"] = sp["body_mass"]
            if sp.get("wing_length"):
                traits["wing_length"] = sp["wing_length"]
            if sp.get("bill_length"):
                traits["bill_length"] = sp["bill_length"]
            if sp.get("tarsus_length"):
                traits["tarsus_length"] = sp["tarsus_length"]
            if sp.get("freq_range_low"):
                traits["freq_range_low"] = sp["freq_range_low"]
            if sp.get("freq_range_high"):
                traits["freq_range_high"] = sp["freq_range_high"]
            if traits:
                trait_lookup[sp["scientific"]] = traits

    results = {}
    for site in req.sites:
        results[site.site_name] = fd_compute(site.species, trait_lookup)
    return {"sites": results}


@router.post("/api/diversity/beta-decomposition", tags=["Diversity"])
async def beta_diversity_decomposition(req: CompareSitesRequest):
    """Decompose beta diversity into turnover and nestedness components."""
    from shared.backend.analysis.biodiversity import turnover_nestedness, whittaker_beta

    site_names = [s.site_name for s in req.sites]
    pairwise = []
    for i in range(len(req.sites)):
        for j in range(i + 1, len(req.sites)):
            tn = turnover_nestedness(req.sites[i].species, req.sites[j].species)
            pairwise.append(
                {
                    "site_a": site_names[i],
                    "site_b": site_names[j],
                    **tn,
                }
            )

    sites_dict = {s.site_name: s.species for s in req.sites}
    return {
        "whittaker_beta": round(whittaker_beta(sites_dict), 4),
        "pairwise_decomposition": pairwise,
    }


@router.post("/api/diversity/conservation-priority", tags=["Diversity"])
async def compute_conservation_priority(req: CompareSitesRequest):
    """Score detected species by conservation priority."""
    from shared.backend.analysis.biodiversity import conservation_priority_score

    all_detections = []
    for site in req.sites:
        for sp in site.species:
            all_detections.append(
                {
                    "species": sp,
                    "confidence": 0.9,
                    "reliable": True,
                    "site": site.site_name,
                }
            )

    lookup_fn = _main.species_db.get if _main.species_db else lambda x: None
    return conservation_priority_score(all_detections, species_db_lookup=lookup_fn)
