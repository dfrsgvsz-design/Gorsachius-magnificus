"""Taxonomy search, catalog, releases, and packages."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

import main as _main

router = APIRouter()


@router.get("/api/surveys/taxonomy/packages", tags=["Field Survey"])
async def list_taxonomy_packages(
    jurisdiction: str = Query(default=""),
    region: str = Query(default=""),
    program: str = Query(default=""),
    protocol: str = Query(default=""),
):
    if not _main.survey_store:
        return {"total": 0, "packages": []}
    packages = _main.survey_store.list_taxonomy_packages(
        jurisdiction=jurisdiction,
        region=region,
        program=program,
        protocol=protocol,
    )
    return {"total": len(packages), "packages": packages}


@router.get("/api/surveys/taxonomy/search", tags=["Field Survey"])
async def search_survey_taxonomy(
    program: str = Query(default=""),
    submodule: str = Query(default=""),
    protocol: str = Query(default=""),
    jurisdiction: str = Query(default=""),
    q: str = Query(default=""),
    limit: int = Query(default=25, ge=1, le=200),
):
    if not _main.taxonomy_catalog:
        return {
            "total": 0,
            "results": [],
            "filters": {
                "program": program,
                "submodule": submodule,
                "protocol": protocol,
                "jurisdiction": jurisdiction,
                "q": q,
                "limit": limit,
            },
        }
    package_ids = _main._resolve_taxonomy_search_package_ids(
        program=program,
        protocol=protocol,
        jurisdiction=jurisdiction,
    )
    if (program or protocol or jurisdiction) and _main.survey_store and not package_ids:
        return {
            "total": 0,
            "results": [],
            "filters": {
                "program": program,
                "submodule": submodule,
                "protocol": protocol,
                "jurisdiction": jurisdiction,
                "q": q,
                "limit": limit,
            },
        }
    results = _main.taxonomy_catalog.search(
        program=program,
        submodule=submodule,
        jurisdiction=jurisdiction,
        q=q,
        limit=limit,
        package_ids=package_ids or None,
    )
    return {
        "total": len(results),
        "results": results,
        "filters": {
            "program": program,
            "submodule": submodule,
            "protocol": protocol,
            "jurisdiction": jurisdiction,
            "q": q,
            "limit": limit,
            "package_ids": package_ids,
        },
    }


@router.get("/api/admin/taxonomy/releases", tags=["Health"])
async def list_taxonomy_release_admin():
    catalog = _main._require_taxonomy_catalog()
    releases = (
        catalog.list_releases() if getattr(catalog, "list_releases", None) else []
    )
    current_release = (
        catalog.current_release_summary()
        if getattr(catalog, "current_release_summary", None)
        else {}
    )
    return {
        "total": len(releases),
        "current_taxonomy_release_id": str(
            current_release.get("taxonomy_release_id")
            or current_release.get("release_id")
            or ""
        ),
        "current_release": current_release,
        "releases": releases,
    }


@router.get("/api/admin/taxonomy/releases/current", tags=["Health"])
async def get_current_taxonomy_release_admin():
    catalog = _main._require_taxonomy_catalog()
    release = (
        catalog.current_release_summary()
        if getattr(catalog, "current_release_summary", None)
        else {}
    )
    if not release:
        raise HTTPException(status_code=404, detail="No current taxonomy release")
    return release


@router.post("/api/admin/taxonomy/releases/rebuild", tags=["Health"])
async def rebuild_taxonomy_release_admin(
    force: bool = Query(default=True),
    activate: Optional[bool] = Query(default=None),
):
    catalog = _main._require_taxonomy_catalog()
    if not getattr(catalog, "rebuild_release", None):
        raise HTTPException(status_code=501, detail="Taxonomy rebuild unavailable")
    try:
        release = catalog.rebuild_release(force=force, activate=activate)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "ok", "release": release}


@router.post("/api/admin/taxonomy/releases/{release_id}/activate", tags=["Health"])
async def activate_taxonomy_release_admin(release_id: str):
    catalog = _main._require_taxonomy_catalog()
    if not getattr(catalog, "activate_release", None):
        raise HTTPException(status_code=501, detail="Taxonomy activation unavailable")
    try:
        release = catalog.activate_release(release_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "ok", "release": release}


@router.get("/api/admin/taxonomy/discrepancy-report", tags=["Health"])
async def get_taxonomy_discrepancy_report_admin(release_id: str = Query(default="")):
    catalog = _main._require_taxonomy_catalog()
    if not getattr(catalog, "export_discrepancy_report", None):
        raise HTTPException(
            status_code=501, detail="Taxonomy discrepancy report unavailable"
        )
    return catalog.export_discrepancy_report(release_id)
