"""Species database query endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(tags=["Species"])


@router.get("/api/species")
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
    import main as _m

    if _m.species_db and _m.species_db.count > 0:
        if query:
            results = _m.species_db.search(query, limit=limit)
        elif any([order, family, protection, iucn]):
            results = _m.species_db.filter(
                order=order, family=family, protection=protection, iucn=iucn
            )[:limit]
        else:
            results = _m.species_db.all_species[:limit]
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
        from xeno_canto_client import CHINA_BIRD_SPECIES

        species = []
        for i, sp in enumerate(CHINA_BIRD_SPECIES[:limit]):
            species.append(
                {
                    "id": i,
                    "scientific_name": sp["scientific"],
                    "chinese_name": sp["chinese"],
                    "english_name": sp["english"],
                }
            )
    return {"total": len(species), "species": species}


@router.get("/api/species/orders")
async def list_orders():
    """List all taxonomic orders with species count."""
    import main as _m

    if not _m.species_db:
        raise HTTPException(status_code=503, detail="Species database not loaded")
    orders = _m.species_db.list_orders()
    return {
        "total": len(orders),
        "orders": [{"order": o, "order_cn": cn, "count": c} for o, cn, c in orders],
    }


@router.get("/api/species/families")
async def list_families(order: Optional[str] = Query(default=None)):
    """List families, optionally filtered by order."""
    import main as _m

    if not _m.species_db:
        raise HTTPException(status_code=503, detail="Species database not loaded")
    families = _m.species_db.list_families(order=order)
    return {
        "total": len(families),
        "families": [
            {"family": f, "family_cn": cn, "count": c} for f, cn, c in families
        ],
    }


@router.get("/api/species/stats")
async def species_stats():
    """Get database statistics: total, by protection level, by IUCN status."""
    import main as _m

    if not _m.species_db:
        raise HTTPException(status_code=503, detail="Species database not loaded")
    all_sp = _m.species_db.all_species
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
        "orders": len(_m.species_db.list_orders()),
        "families": len(_m.species_db.list_families()),
        "iucn_breakdown": iucn_counts,
        "protection_breakdown": prot_counts,
        "with_audio": sum(1 for sp in all_sp if sp.get("has_audio")),
    }
