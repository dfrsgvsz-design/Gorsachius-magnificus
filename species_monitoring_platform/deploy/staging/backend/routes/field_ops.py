"""Field operations: batch import, pre-survey planning, eBird/GBIF/iNaturalist integration."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from models.schemas import APIKeyRequest, BatchScanRequest

router = APIRouter()


@router.post("/api/batch/scan", tags=["Batch Import"])
async def batch_scan_directory(req: BatchScanRequest):
    """Scan a directory (e.g. SD card mount) and classify files for import."""
    import main as _m
    from batch_import import (
        create_import_manifest,
        group_by_camera,
        group_by_date,
        scan_directory,
    )

    _m._validate_scan_path(req.directory)
    result = scan_directory(req.directory, recursive=req.recursive)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    by_camera = group_by_camera(result.get("image_files", []))
    by_date = group_by_date(
        result.get("image_files", []) + result.get("audio_files", [])
    )
    manifest = create_import_manifest(
        result,
        device_id=req.device_id,
        site_name=req.site_name,
        camera_serial=req.camera_serial,
    )
    return {
        "scan": result["summary"],
        "total_size_mb": result["total_size_mb"],
        "by_camera": {k: len(v) for k, v in by_camera.items()},
        "by_date": {k: len(v) for k, v in by_date.items()},
        "manifest": manifest,
    }


@router.get("/api/survey/pre-survey/{region_code}", tags=["Survey Planning"])
async def pre_survey_species(
    region_code: str,
    site_name: Optional[str] = Query(default=None),
):
    """Generate expected species checklist for a region using eBird + local data."""
    import ebird_client

    import main as _m
    from species_survey_planner import generate_expected_species, generate_survey_protocol

    ebird_obs = ebird_client.get_recent_observations(
        region_code, back=30, max_results=200
    )
    ebird_species = ebird_client.get_region_species_list(region_code)

    local_species = []
    if _m.species_db:
        local_species = [
            {
                "scientific_name": sp["scientific"],
                "chinese_name": sp["chinese"],
                "english_name": sp.get("english", ""),
            }
            for sp in _m.species_db.all_species
        ]

    detection_history_data = []
    if _m.det_store and site_name:
        site_data = _m.det_store.get_site_detections(site_name)
        detection_history_data = site_data if isinstance(site_data, list) else []

    ebird_obs_list = ebird_obs if isinstance(ebird_obs, list) else []
    ebird_codes = ebird_species if isinstance(ebird_species, list) else []

    expected = generate_expected_species(
        ebird_species_codes=ebird_codes,
        ebird_recent_obs=ebird_obs_list,
        local_db_species=local_species,
        detection_history=detection_history_data,
        region=region_code,
    )

    protocol = generate_survey_protocol(expected, site_count=1)
    expected["recommended_protocol"] = protocol

    return expected


# ── GBIF ──


@router.get("/api/gbif/species/{name}", tags=["GBIF"])
async def gbif_species_search(name: str, limit: int = Query(default=10, ge=1, le=50)):
    """Search GBIF for species by name."""
    import gbif_client

    return gbif_client.search_species(name, limit=limit)


@router.get("/api/gbif/match/{name}", tags=["GBIF"])
async def gbif_species_match(name: str):
    """Match a name to GBIF backbone taxonomy."""
    import gbif_client

    return gbif_client.species_match(name)


@router.get("/api/gbif/occurrences", tags=["GBIF"])
async def gbif_occurrences(
    scientific_name: Optional[str] = Query(default=None),
    taxon_key: Optional[int] = Query(default=None),
    country: str = Query(default="CN"),
    limit: int = Query(default=50, ge=1, le=300),
):
    """Search GBIF occurrence records."""
    import gbif_client

    return gbif_client.get_occurrences(
        taxon_key=taxon_key,
        scientific_name=scientific_name,
        country=country,
        limit=limit,
    )


@router.get("/api/gbif/nearby", tags=["GBIF"])
async def gbif_nearby(
    lat: float = Query(...),
    lng: float = Query(...),
    radius_km: float = Query(default=10),
    taxon_key: Optional[int] = Query(default=None),
    limit: int = Query(default=50),
):
    """Search GBIF occurrences near a coordinate."""
    import gbif_client

    return gbif_client.get_occurrences_by_location(
        lat, lng, radius_km, taxon_key, limit
    )


# ── iNaturalist ──


@router.get("/api/inat/taxa/{query}", tags=["iNaturalist"])
async def inat_taxa_search(query: str, limit: int = Query(default=10)):
    """Search iNaturalist taxa."""
    import inaturalist_client

    return inaturalist_client.search_taxa(query, limit=limit)


@router.get("/api/inat/observations", tags=["iNaturalist"])
async def inat_observations(
    taxon_name: Optional[str] = Query(default=None),
    taxon_id: Optional[int] = Query(default=None),
    lat: Optional[float] = Query(default=None),
    lng: Optional[float] = Query(default=None),
    radius_km: int = Query(default=20),
    iconic_taxa: Optional[str] = Query(default=None),
    per_page: int = Query(default=30, ge=1, le=200),
):
    """Search iNaturalist observations."""
    import inaturalist_client

    return inaturalist_client.get_observations(
        taxon_id=taxon_id,
        taxon_name=taxon_name,
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        iconic_taxa=iconic_taxa,
        per_page=per_page,
    )


@router.get("/api/inat/species-counts", tags=["iNaturalist"])
async def inat_species_counts(
    lat: Optional[float] = Query(default=None),
    lng: Optional[float] = Query(default=None),
    radius_km: int = Query(default=50),
    iconic_taxa: Optional[str] = Query(default=None),
    per_page: int = Query(default=50),
):
    """Get most observed species counts from iNaturalist."""
    import inaturalist_client

    return inaturalist_client.get_species_counts(
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        iconic_taxa=iconic_taxa,
        per_page=per_page,
    )


@router.get("/api/inat/places/{query}", tags=["iNaturalist"])
async def inat_places(query: str):
    """Search iNaturalist places."""
    import inaturalist_client

    return inaturalist_client.get_places(query)


# ── eBird ──


@router.get("/api/ebird/key-status", tags=["eBird"])
async def ebird_key_status():
    """Check if eBird API key is configured."""
    import ebird_client

    key = ebird_client.get_api_key()
    return {"configured": bool(key)}


@router.post("/api/ebird/key", tags=["eBird"])
async def set_ebird_key(req: APIKeyRequest):
    """Set eBird API key."""
    import ebird_client

    if not req.key.strip():
        raise HTTPException(status_code=400, detail="Key cannot be empty")
    ebird_client.set_api_key(req.key)
    return {"status": "ok"}


@router.get("/api/ebird/recent/{region_code}", tags=["eBird"])
async def ebird_recent_obs(
    region_code: str,
    back: int = Query(default=14, ge=1, le=30),
    max_results: int = Query(default=50, ge=1, le=200),
):
    """Get recent bird observations from eBird for a region."""
    import ebird_client

    data = ebird_client.get_recent_observations(
        region_code, back=back, max_results=max_results
    )
    if isinstance(data, dict) and "error" in data:
        raise HTTPException(status_code=502, detail=data["error"])
    return {"region": region_code, "total": len(data), "observations": data}


@router.get("/api/ebird/notable/{region_code}", tags=["eBird"])
async def ebird_notable_obs(
    region_code: str, back: int = Query(default=14, ge=1, le=30)
):
    """Get recent notable/rare observations from eBird."""
    import ebird_client

    data = ebird_client.get_recent_notable(region_code, back=back)
    if isinstance(data, dict) and "error" in data:
        raise HTTPException(status_code=502, detail=data["error"])
    return {"region": region_code, "total": len(data), "observations": data}


@router.get("/api/ebird/nearby", tags=["eBird"])
async def ebird_nearby_obs(
    lat: float = Query(...),
    lng: float = Query(...),
    dist: int = Query(default=25, ge=1, le=50),
    back: int = Query(default=14, ge=1, le=30),
):
    """Get nearby bird observations from eBird."""
    import ebird_client

    data = ebird_client.get_nearby_observations(lat, lng, dist=dist, back=back)
    if isinstance(data, dict) and "error" in data:
        raise HTTPException(status_code=502, detail=data["error"])
    return {"total": len(data), "observations": data}


@router.get("/api/ebird/hotspots/{region_code}", tags=["eBird"])
async def ebird_hotspots(region_code: str):
    """List birding hotspots in a region from eBird."""
    import ebird_client

    data = ebird_client.get_hotspots(region_code)
    if isinstance(data, dict) and "error" in data:
        raise HTTPException(status_code=502, detail=data["error"])
    return {"region": region_code, "total": len(data), "hotspots": data}


@router.get("/api/ebird/species-list/{region_code}", tags=["eBird"])
async def ebird_species_list(region_code: str):
    """Get the complete species list for a region from eBird."""
    import ebird_client

    data = ebird_client.get_region_species_list(region_code)
    if isinstance(data, dict) and "error" in data:
        raise HTTPException(status_code=502, detail=data["error"])
    return {"region": region_code, "total": len(data), "species_codes": data}


@router.get("/api/ebird/regions", tags=["eBird"])
async def ebird_regions():
    """List available China region codes for eBird queries."""
    import ebird_client

    return {"regions": ebird_client.CHINA_REGION_CODES}
