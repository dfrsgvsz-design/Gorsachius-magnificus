"""Soundscape analysis endpoints."""

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

router = APIRouter(tags=["Soundscape"])


@router.post("/api/soundscape/analyze")
async def analyze_soundscape(
    file: UploadFile = File(...),
    site_name: str = Query(default=""),
):
    """Compute ecoacoustic indices and optional health score for an audio file."""
    import io

    import librosa

    import main as _m

    content = await _m._read_upload(file)
    y, sr = librosa.load(io.BytesIO(content), sr=48000, mono=True)
    indices = _m.soundscape_analyzer.compute_indices(y, sr)
    result = {"indices": indices, "site_name": site_name}
    if site_name:
        baseline = _m.soundscape_analyzer.load_baseline(site_name)
        if baseline:
            result["health"] = _m.soundscape_analyzer.compute_health_score(
                indices, baseline
            )
    return result


@router.get("/api/soundscape/baseline/{site_name}")
async def get_soundscape_baseline(site_name: str):
    """Retrieve stored soundscape baseline for a site."""
    import main as _m

    baseline = _m.soundscape_analyzer.load_baseline(site_name)
    if not baseline:
        raise HTTPException(status_code=404, detail="No baseline found for this site")
    return baseline
