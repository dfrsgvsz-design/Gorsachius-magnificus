"""Taxonomy search, catalog, and release management endpoints."""

import json
import os
import time as _time
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

router = APIRouter(tags=["Field Survey"])


@router.get("/api/surveys/protocols")
async def list_survey_protocols(
    program: str = Query(default=""),
    protocol: str = Query(default=""),
):
    import main as _m

    if not _m.survey_store:
        return {"total": 0, "protocols": []}
    protocols = _m.survey_store.list_protocol_definitions(
        program=program, protocol=protocol
    )
    return {"total": len(protocols), "protocols": protocols}


@router.get("/api/surveys/taxonomy/packages")
async def list_taxonomy_packages(
    jurisdiction: str = Query(default=""),
    region: str = Query(default=""),
    program: str = Query(default=""),
    protocol: str = Query(default=""),
):
    import main as _m

    if not _m.survey_store:
        return {"total": 0, "packages": []}
    packages = _m.survey_store.list_taxonomy_packages(
        jurisdiction=jurisdiction,
        region=region,
        program=program,
        protocol=protocol,
    )
    return {"total": len(packages), "packages": packages}


@router.get("/api/surveys/taxonomy/search")
async def search_survey_taxonomy(
    program: str = Query(default=""),
    submodule: str = Query(default=""),
    protocol: str = Query(default=""),
    jurisdiction: str = Query(default=""),
    q: str = Query(default=""),
    limit: int = Query(default=25, ge=1, le=200),
):
    import main as _m

    if not _m.taxonomy_catalog:
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
    package_ids = _m._resolve_taxonomy_search_package_ids(
        program=program,
        protocol=protocol,
        jurisdiction=jurisdiction,
    )
    if (program or protocol or jurisdiction) and _m.survey_store and not package_ids:
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
    results = _m.taxonomy_catalog.search(
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
    import main as _m

    catalog = _m._require_taxonomy_catalog()
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
    import main as _m

    catalog = _m._require_taxonomy_catalog()
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
    activate: bool | None = Query(default=None),
):
    import main as _m

    catalog = _m._require_taxonomy_catalog()
    if not getattr(catalog, "rebuild_release", None):
        raise HTTPException(status_code=501, detail="Taxonomy rebuild unavailable")
    try:
        release = catalog.rebuild_release(force=force, activate=activate)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "ok", "release": release}


@router.post("/api/admin/taxonomy/releases/{release_id}/activate", tags=["Health"])
async def activate_taxonomy_release_admin(release_id: str):
    import main as _m

    catalog = _m._require_taxonomy_catalog()
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
    import main as _m

    catalog = _m._require_taxonomy_catalog()
    if not getattr(catalog, "export_discrepancy_report", None):
        raise HTTPException(
            status_code=501, detail="Taxonomy discrepancy report unavailable"
        )
    return catalog.export_discrepancy_report(release_id)


@router.post("/api/admin/taxonomy/bulk-import", tags=["Health"])
async def bulk_import_taxonomy(file: UploadFile = File(...)):
    """Bulk import species data from CSV or JSON file."""
    import csv as csv_mod
    import io

    import main as _m

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    content = await file.read()
    text = content.decode("utf-8-sig")
    entries = []

    if file.filename.endswith(".json"):
        data = json.loads(text)
        raw_entries = data if isinstance(data, list) else data.get("entries", data.get("species", []))
        for item in raw_entries:
            if isinstance(item, dict) and item.get("scientific_name"):
                entries.append(item)
    elif file.filename.endswith(".csv"):
        reader = csv_mod.DictReader(io.StringIO(text))
        for row in reader:
            sci = (row.get("scientific_name") or row.get("学名") or "").strip()
            if not sci:
                continue
            entries.append({
                "scientific_name": sci,
                "simplified_chinese_name": (row.get("chinese_name") or row.get("中文名") or "").strip(),
                "english_common_name": (row.get("english_name") or row.get("英文名") or "").strip(),
                "taxon_group": (row.get("taxon_group") or row.get("类群") or "birds").strip().lower(),
                "order": (row.get("order") or row.get("目") or "").strip(),
                "family": (row.get("family") or row.get("科") or "").strip(),
                "national_protection_status": (row.get("protection") or row.get("保护等级") or "").strip(),
                "red_list_status": (row.get("iucn") or row.get("IUCN") or row.get("红色名录") or "").strip(),
            })
    else:
        raise HTTPException(status_code=400, detail="Unsupported file format. Use .json or .csv")

    imported = 0
    if _m.taxonomy_catalog and hasattr(_m.taxonomy_catalog, "upsert_entry"):
        for entry in entries:
            try:
                _m.taxonomy_catalog.upsert_entry(entry)
                imported += 1
            except Exception:
                pass
    else:
        output_path = os.path.join(
            os.environ.get("BIRD_PLATFORM_DATA_DIR", str(Path(__file__).resolve().parent.parent / "data")),
            f"imported_species_{int(_time.time())}.json",
        )
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({"total": len(entries), "entries": entries}, f, ensure_ascii=False, indent=2)
        imported = len(entries)

    return {
        "status": "ok",
        "total_parsed": len(entries),
        "imported": imported,
        "message": f"Successfully imported {imported} species entries",
    }
