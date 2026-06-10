"""Xeno-Canto search, download, and API key management endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from models.schemas import APIKeyRequest, XCSearchRequest

router = APIRouter(tags=["Xeno-canto"])


@router.get("/api/xc-key-status")
async def xc_key_status():
    """Check if Xeno-canto API key is configured."""
    from xeno_canto_client import get_api_key

    key = get_api_key()
    return {"configured": bool(key)}


@router.post("/api/xc-key")
async def set_xc_key(req: APIKeyRequest):
    """Set Xeno-canto API key."""
    from xeno_canto_client import set_api_key

    if not req.key.strip():
        raise HTTPException(status_code=400, detail="Key cannot be empty")
    set_api_key(req.key)
    return {"status": "ok", "message": "API Key已保存"}


@router.post("/api/search-xc")
async def search_xeno_canto(req: XCSearchRequest):
    """Search xeno-canto database for bird recordings."""
    from xeno_canto_client import search_recordings

    results = search_recordings(
        req.species, country=req.country, max_results=req.max_results
    )
    if results and isinstance(results[0], dict) and "error" in results[0]:
        return {
            "query": req.species,
            "country": req.country,
            "total_results": 0,
            "recordings": [],
            "error": results[0]["error"],
        }
    return {
        "query": req.species,
        "country": req.country,
        "total_results": len(results),
        "recordings": results,
    }


@router.get("/api/species/{scientific_name}/recordings", tags=["Species"])
async def species_recordings(
    scientific_name: str,
    song_type: Optional[str] = Query(default=None),
    country: str = Query(default=""),
    max_results: int = Query(default=12, ge=1, le=50),
):
    """Fetch Xeno-Canto recordings for a species, optionally filtered by song type and region."""
    from xeno_canto_client import search_recordings

    results = search_recordings(
        scientific_name,
        country=country,
        quality="B",
        max_results=max_results * 3,
    )
    if results and isinstance(results[0], dict) and "error" in results[0]:
        return {
            "species": scientific_name,
            "recordings": [],
            "error": results[0]["error"],
        }

    if song_type:
        lowered = song_type.lower()
        results = [r for r in results if lowered in (r.get("type") or "").lower()]

    song_types = sorted({r.get("type", "unknown") for r in results if r.get("type")})
    regions = sorted({r.get("locality", "") for r in results if r.get("locality")})

    return {
        "species": scientific_name,
        "total": len(results),
        "recordings": results[:max_results],
        "available_types": song_types,
        "available_regions": regions,
    }
