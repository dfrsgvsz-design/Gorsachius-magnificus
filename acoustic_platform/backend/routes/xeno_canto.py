"""Xeno-Canto search, download, and API key management."""

from fastapi import APIRouter, HTTPException

import main as _main
from models.schemas import XCSearchRequest, APIKeyRequest

router = APIRouter(tags=["Xeno-canto"])


@router.get("/api/xc-key-status")
async def xc_key_status():
    """Check if Xeno-canto API key is configured."""
    key = _main.get_api_key()
    return {"configured": bool(key)}


@router.post("/api/xc-key")
async def set_xc_key(req: APIKeyRequest):
    """Set Xeno-canto API key."""
    if not req.key.strip():
        raise HTTPException(status_code=400, detail="Key cannot be empty")
    _main.set_api_key(req.key)
    return {"status": "ok", "message": "API Key已保存"}


@router.post("/api/search-xc")
async def search_xeno_canto(req: XCSearchRequest):
    """Search xeno-canto database for bird recordings."""
    results = _main.search_recordings(
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
