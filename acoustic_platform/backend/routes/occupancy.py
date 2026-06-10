"""Occupancy modeling endpoints."""

from fastapi import APIRouter, HTTPException

import main as _main
from models.schemas import OccupancyRequest

router = APIRouter(tags=["Occupancy"])


@router.get("/api/occupancy/{site_name}/{species}")
async def get_occupancy_data(site_name: str, species: str):
    """Get detection/non-detection history for occupancy modeling."""
    data = _main.det_store.compute_occupancy_inputs(site_name, species)
    return data


@router.post("/api/occupancy/analyze")
async def analyze_occupancy(req: OccupancyRequest):
    """Run single-season occupancy model for a species."""
    return _main.occupancy_engine.analyze(
        species=req.species,
        n_surveys=req.n_surveys,
        survey_duration_days=req.survey_duration_days,
        start_date=req.start_date,
        end_date=req.end_date,
    )


@router.get("/api/occupancy/verification-targets/{species}")
async def get_verification_targets(species: str):
    """Get recommended verification targets based on occupancy uncertainty."""
    result = _main.occupancy_engine.analyze(species=species)
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    targets = _main.occupancy_engine.suggest_verification_targets(result)
    return {"species": species, "targets": targets}
