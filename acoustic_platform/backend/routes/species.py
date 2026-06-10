"""Species DB, SDM, expected species, GBIF, iNaturalist, eBird endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

import main as _main
from models.schemas import APIKeyRequest

router = APIRouter()


@router.get("/api/species", tags=["Species"])
async def list_species(
    query: Optional[str] = Query(default=None, description="Search by name"),
    order: Optional[str] = Query(default=None, description="Filter by taxonomic order"),
    family: Optional[str] = Query(default=None, description="Filter by family"),
    protection: Optional[str] = Query(
        default=None, description="Filter by protection level: I, II"
    ),
    iucn: Optional[str] = Query(
        default=None, description="Filter by IUCN status: CR,EN,VU,NT,LC"
    ),
    limit: int = Query(default=500, ge=1, le=2000),
):
    """List Chinese bird species with search and filter capabilities."""
    if _main.species_db and _main.species_db.count > 0:
        if query:
            results = _main.species_db.search(query, limit=limit)
        elif any([order, family, protection, iucn]):
            results = _main.species_db.filter(
                order=order, family=family, protection=protection, iucn=iucn
            )[:limit]
        else:
            results = _main.species_db.all_species[:limit]
        species = []
        for i, sp in enumerate(results):
            species.append(
                {
                    "id": i,
                    "scientific_name": sp["scientific"],
                    "chinese_name": sp["chinese"],
                    "english_name": sp.get("english", ""),
                    "order": sp.get("order", ""),
                    "order_cn": sp.get("order_cn", ""),
                    "family": sp.get("family", ""),
                    "family_cn": sp.get("family_cn", ""),
                    "iucn": sp.get("iucn", ""),
                    "protection": sp.get("protection"),
                    "resident": sp.get("resident", ""),
                    "has_audio": sp.get("has_audio", False),
                }
            )
    else:
        species = []
        for i, sp in enumerate(_main.CHINA_BIRD_SPECIES[:limit]):
            species.append(
                {
                    "id": i,
                    "scientific_name": sp["scientific"],
                    "chinese_name": sp["chinese"],
                    "english_name": sp["english"],
                }
            )
    return {"total": len(species), "species": species}


@router.get("/api/species/orders", tags=["Species"])
async def list_orders():
    """List all taxonomic orders with species count."""
    if not _main.species_db:
        raise HTTPException(status_code=503, detail="Species database not loaded")
    orders = _main.species_db.list_orders()
    return {
        "total": len(orders),
        "orders": [{"order": o, "order_cn": cn, "count": c} for o, cn, c in orders],
    }


@router.get("/api/species/families")
async def list_families(order: Optional[str] = Query(default=None)):
    """List families, optionally filtered by order."""
    if not _main.species_db:
        raise HTTPException(status_code=503, detail="Species database not loaded")
    families = _main.species_db.list_families(order=order)
    return {
        "total": len(families),
        "families": [
            {"family": f, "family_cn": cn, "count": c} for f, cn, c in families
        ],
    }


@router.get("/api/species/stats")
async def species_stats():
    """Get database statistics: total, by protection level, by IUCN status."""
    if not _main.species_db:
        raise HTTPException(status_code=503, detail="Species database not loaded")
    all_sp = _main.species_db.all_species
    iucn_counts = {}
    prot_counts = {"I": 0, "II": 0, "none": 0}
    for sp in all_sp:
        iucn = sp.get("iucn", "NE")
        iucn_counts[iucn] = iucn_counts.get(iucn, 0) + 1
        prot = sp.get("protection")
        if prot == "I":
            prot_counts["I"] += 1
        elif prot == "II":
            prot_counts["II"] += 1
        else:
            prot_counts["none"] += 1
    return {
        "total_species": len(all_sp),
        "orders": len(_main.species_db.list_orders()),
        "families": len(_main.species_db.list_families()),
        "iucn_breakdown": iucn_counts,
        "protection_breakdown": prot_counts,
        "with_audio": sum(1 for sp in all_sp if sp.get("has_audio")),
    }


@router.get("/api/species/{scientific_name}/recordings", tags=["Species"])
async def species_recordings(
    scientific_name: str,
    song_type: Optional[str] = Query(default=None),
    country: str = Query(default=""),
    max_results: int = Query(default=12, ge=1, le=50),
):
    """Fetch Xeno-Canto recordings for a species."""
    results = _main.search_recordings(
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


@router.get("/api/survey/pre-survey/{region_code}", tags=["Survey Planning"])
async def pre_survey_species(
    region_code: str,
    site_name: Optional[str] = Query(default=None),
):
    """Generate expected species checklist for a region using eBird + local data."""
    ebird_obs = _main.ebird_client.get_recent_observations(
        region_code, back=30, max_results=200
    )
    ebird_species = _main.ebird_client.get_region_species_list(region_code)

    local_species = []
    if _main.species_db:
        local_species = [
            {
                "scientific_name": sp["scientific"],
                "chinese_name": sp["chinese"],
                "english_name": sp.get("english", ""),
            }
            for sp in _main.species_db.all_species
        ]

    detection_history_data = []
    if _main.det_store and site_name:
        site_data = _main.det_store.get_site_detections(site_name)
        detection_history_data = site_data if isinstance(site_data, list) else []

    ebird_obs_list = ebird_obs if isinstance(ebird_obs, list) else []
    ebird_codes = ebird_species if isinstance(ebird_species, list) else []

    expected = _main.generate_expected_species(
        ebird_species_codes=ebird_codes,
        ebird_recent_obs=ebird_obs_list,
        local_db_species=local_species,
        detection_history=detection_history_data,
        region=region_code,
    )

    protocol = _main.generate_survey_protocol(expected, site_count=1)
    expected["recommended_protocol"] = protocol

    return expected


# ── GBIF ──

@router.get("/api/gbif/species/{name}", tags=["GBIF"])
async def gbif_species_search(name: str, limit: int = Query(default=10, ge=1, le=50)):
    """Search GBIF for species by name."""
    return _main.gbif_client.search_species(name, limit=limit)


@router.get("/api/gbif/match/{name}", tags=["GBIF"])
async def gbif_species_match(name: str):
    """Match a name to GBIF backbone taxonomy."""
    return _main.gbif_client.species_match(name)


@router.get("/api/gbif/occurrences", tags=["GBIF"])
async def gbif_occurrences(
    scientific_name: Optional[str] = Query(default=None),
    taxon_key: Optional[int] = Query(default=None),
    country: str = Query(default="CN"),
    limit: int = Query(default=50, ge=1, le=300),
):
    """Search GBIF occurrence records."""
    return _main.gbif_client.get_occurrences(
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
    return _main.gbif_client.get_occurrences_by_location(
        lat, lng, radius_km, taxon_key, limit
    )


# ── iNaturalist ──

@router.get("/api/inat/taxa/{query}", tags=["iNaturalist"])
async def inat_taxa_search(query: str, limit: int = Query(default=10)):
    """Search iNaturalist taxa."""
    return _main.inaturalist_client.search_taxa(query, limit=limit)


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
    return _main.inaturalist_client.get_observations(
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
    return _main.inaturalist_client.get_species_counts(
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        iconic_taxa=iconic_taxa,
        per_page=per_page,
    )


@router.get("/api/inat/places/{query}", tags=["iNaturalist"])
async def inat_places(query: str):
    """Search iNaturalist places."""
    return _main.inaturalist_client.get_places(query)


# ── eBird ──

@router.get("/api/ebird/key-status", tags=["eBird"])
async def ebird_key_status():
    """Check if eBird API key is configured."""
    key = _main.ebird_client.get_api_key()
    return {"configured": bool(key)}


@router.post("/api/ebird/key", tags=["eBird"])
async def set_ebird_key(req: APIKeyRequest):
    """Set eBird API key."""
    if not req.key.strip():
        raise HTTPException(status_code=400, detail="Key cannot be empty")
    _main.ebird_client.set_api_key(req.key)
    return {"status": "ok"}


@router.get("/api/ebird/recent/{region_code}", tags=["eBird"])
async def ebird_recent_obs(
    region_code: str,
    back: int = Query(default=14, ge=1, le=30),
    max_results: int = Query(default=50, ge=1, le=200),
):
    """Get recent bird observations from eBird for a region."""
    data = _main.ebird_client.get_recent_observations(
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
    data = _main.ebird_client.get_recent_notable(region_code, back=back)
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
    data = _main.ebird_client.get_nearby_observations(lat, lng, dist=dist, back=back)
    if isinstance(data, dict) and "error" in data:
        raise HTTPException(status_code=502, detail=data["error"])
    return {"total": len(data), "observations": data}


@router.get("/api/ebird/hotspots/{region_code}", tags=["eBird"])
async def ebird_hotspots(region_code: str):
    """List birding hotspots in a region from eBird."""
    data = _main.ebird_client.get_hotspots(region_code)
    if isinstance(data, dict) and "error" in data:
        raise HTTPException(status_code=502, detail=data["error"])
    return {"region": region_code, "total": len(data), "hotspots": data}


@router.get("/api/ebird/species-list/{region_code}", tags=["eBird"])
async def ebird_species_list(region_code: str):
    """Get the complete species list for a region from eBird."""
    data = _main.ebird_client.get_region_species_list(region_code)
    if isinstance(data, dict) and "error" in data:
        raise HTTPException(status_code=502, detail=data["error"])
    return {"region": region_code, "total": len(data), "species_codes": data}


@router.get("/api/ebird/regions", tags=["eBird"])
async def ebird_regions():
    """List available China region codes for eBird queries."""
    return {"regions": _main.ebird_client.CHINA_REGION_CODES}
