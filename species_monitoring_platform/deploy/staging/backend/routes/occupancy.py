"""Occupancy modeling and few-shot detector endpoints."""

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from models.schemas import OccupancyRequest

router = APIRouter(tags=["Occupancy"])


@router.get("/api/occupancy/{site_name}/{species}")
async def get_occupancy_data(site_name: str, species: str):
    """Get detection/non-detection history for occupancy modeling."""
    import main as _m

    data = _m.det_store.compute_occupancy_inputs(site_name, species)
    return data


@router.post("/api/occupancy/analyze")
async def analyze_occupancy(req: OccupancyRequest):
    """Run single-season occupancy model for a species."""
    import main as _m

    return _m.occupancy_engine.analyze(
        species=req.species,
        n_surveys=req.n_surveys,
        survey_duration_days=req.survey_duration_days,
        start_date=req.start_date,
        end_date=req.end_date,
    )


@router.get("/api/occupancy/verification-targets/{species}")
async def get_verification_targets(species: str):
    """Get recommended verification targets based on occupancy uncertainty."""
    import main as _m

    result = _m.occupancy_engine.analyze(species=species)
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    targets = _m.occupancy_engine.suggest_verification_targets(result)
    return {"species": species, "targets": targets}


@router.post("/api/fewshot/create-detector", tags=["Few-shot"])
async def create_fewshot_detector(
    name: str = Query(...),
    species: str = Query(...),
    files: list[UploadFile] = File(...),
):
    """Create a few-shot detector from 1-5 reference audio files."""
    import main as _m

    embeddings = []
    for f in files[:5]:
        content = await _m._read_upload(f)
        emb = _m.fewshot.extract_embedding_from_audio(content)
        if emb is not None:
            embeddings.append(emb)
    if not embeddings:
        raise HTTPException(
            status_code=422,
            detail="Could not extract embeddings from any reference file",
        )
    return _m.fewshot.create_detector(name, species, embeddings)


@router.get("/api/fewshot/detectors", tags=["Few-shot"])
async def list_fewshot_detectors():
    """List all saved few-shot detectors."""
    import main as _m

    return {"detectors": _m.fewshot.list_detectors()}


@router.delete("/api/fewshot/detectors/{detector_id}", tags=["Few-shot"])
async def delete_fewshot_detector(detector_id: str):
    """Delete a few-shot detector."""
    import main as _m

    if not _m.fewshot.delete_detector(detector_id):
        raise HTTPException(status_code=404, detail="Detector not found")
    return {"deleted": True}
