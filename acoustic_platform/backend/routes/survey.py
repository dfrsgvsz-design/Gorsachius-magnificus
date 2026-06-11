"""Survey CRUD, projects, sites, routes, observations, tracks, events, sync."""

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

import main as _main
from models.schemas import (
    SurveyCreateRequest,
    SurveyProjectRequest,
    SurveySiteRequest,
    SurveyRouteRequest,
    ObservationRecordRequest,
    TrackLogRequest,
    MapPackageRequest,
    DesignAssetRequest,
    SamplingEventRequest,
    ExportJobRequest,
    SyncPushRequest,
    ConflictResolveRequest,
)

router = APIRouter()


@router.get("/api/surveys", tags=["Surveys"])
async def list_surveys():
    """List all survey sites with their status."""
    raw_sites = list(_main._survey_sites)
    if _main.survey_store:
        seen_names = {site.get("site_name", "") for site in raw_sites}
        for site in _main.survey_store.list_sites():
            site_name = site.get("name", "")
            if site_name in seen_names:
                continue
            raw_sites.append(
                {
                    "site_name": site_name,
                    "region": site.get("admin_region", ""),
                    "latitude": site.get("latitude"),
                    "longitude": site.get("longitude"),
                    "habitat_type": site.get("habitat_type", ""),
                    "protocol": "field_survey",
                    "notes": site.get("notes", ""),
                    "created_at": site.get("created_at", ""),
                    "surveys_completed": 0,
                }
            )

    enriched = []
    for site in raw_sites:
        site_name = site.get("site_name", "")
        site_detections = (
            _main.det_store.get_site_detections(site_name) if _main.det_store and site_name else []
        )
        if not isinstance(site_detections, list):
            site_detections = []
        unique_species = len(
            {
                d.get("species", d.get("species_scientific", ""))
                for d in site_detections
                if isinstance(d, dict)
            }
        )
        enriched.append(
            {
                **site,
                "total_detections": len(site_detections),
                "species_detected": unique_species,
            }
        )
    return {"total": len(enriched), "sites": enriched}


@router.post("/api/surveys", tags=["Surveys"])
async def create_survey(req: SurveyCreateRequest):
    """Register a new survey site."""
    if any(s.get("site_name") == req.site_name for s in _main._survey_sites):
        raise HTTPException(
            status_code=409, detail=f"Site '{req.site_name}' already exists"
        )
    site = {
        "site_name": req.site_name,
        "region": req.region,
        "latitude": req.latitude,
        "longitude": req.longitude,
        "habitat_type": req.habitat_type,
        "protocol": req.protocol,
        "notes": req.notes,
        "created_at": datetime.now().isoformat(),
        "surveys_completed": 0,
    }
    _main._survey_sites.append(site)
    _main._save_surveys()
    if _main.survey_store:
        _main.survey_store.upsert_site(
            {
                "name": req.site_name,
                "latitude": req.latitude,
                "longitude": req.longitude,
                "habitat_type": req.habitat_type,
                "admin_region": req.region,
                "notes": req.notes,
                "extra": {"protocol": req.protocol, "legacy_site": True},
            }
        )
    return {"status": "ok", "site": site}


@router.delete("/api/surveys/{site_name}", tags=["Surveys"])
async def remove_survey(site_name: str):
    """Remove a survey site."""
    before = len(_main._survey_sites)
    _main._survey_sites = [s for s in _main._survey_sites if s.get("site_name") != site_name]
    deleted_from_store = False
    if _main.survey_store:
        for site in _main.survey_store.list_sites():
            if site.get("name") == site_name:
                deleted_from_store = (
                    _main.survey_store.delete_entity("site", site.get("site_id", ""))
                    or deleted_from_store
                )
    if len(_main._survey_sites) == before:
        if deleted_from_store:
            return {"status": "ok"}
        raise HTTPException(status_code=404, detail="Site not found")
    _main._save_surveys()
    return {"status": "ok"}


@router.get("/api/surveys/projects", tags=["Field Survey"])
async def list_survey_projects():
    return {
        "total": len(_main.survey_store.list_projects()) if _main.survey_store else 0,
        "projects": _main.survey_store.list_projects() if _main.survey_store else [],
    }


@router.get("/api/surveys/protocols", tags=["Field Survey"])
async def list_survey_protocols(
    program: str = Query(default=""),
    protocol: str = Query(default=""),
):
    if not _main.survey_store:
        return {"total": 0, "protocols": []}
    protocols = _main.survey_store.list_protocol_definitions(
        program=program, protocol=protocol
    )
    return {"total": len(protocols), "protocols": protocols}


@router.post("/api/surveys/projects", tags=["Field Survey"])
async def create_survey_project(req: SurveyProjectRequest):
    if not _main.survey_store:
        raise HTTPException(status_code=503, detail="Survey store unavailable")
    project = _main.survey_store.upsert_project(_main._model_to_dict(req))
    return {"status": "ok", "project": project}


@router.get("/api/surveys/sites", tags=["Field Survey"])
async def list_field_sites(project_id: str = Query(default="")):
    if not _main.survey_store:
        return {"total": 0, "sites": []}
    sites = _main.survey_store.list_sites(project_id=project_id)
    return {"total": len(sites), "sites": sites}


@router.post("/api/surveys/sites", tags=["Field Survey"])
async def create_field_site(req: SurveySiteRequest):
    if not _main.survey_store:
        raise HTTPException(status_code=503, detail="Survey store unavailable")
    site = _main.survey_store.upsert_site(_main._model_to_dict(req))
    return {"status": "ok", "site": site}


@router.get("/api/surveys/routes", tags=["Field Survey"])
async def list_field_routes(
    project_id: str = Query(default=""),
    site_id: str = Query(default=""),
):
    if not _main.survey_store:
        return {"total": 0, "routes": []}
    routes = _main.survey_store.list_routes(project_id=project_id, site_id=site_id)
    return {"total": len(routes), "routes": routes}


@router.post("/api/surveys/routes", tags=["Field Survey"])
async def create_field_route(req: SurveyRouteRequest):
    if not _main.survey_store:
        raise HTTPException(status_code=503, detail="Survey store unavailable")
    route = _main.survey_store.upsert_route(_main._model_to_dict(req))
    return {"status": "ok", "route": route}


@router.get("/api/surveys/routes/{route_id}/summary", tags=["Field Survey"])
async def get_field_route_summary(route_id: str):
    if not _main.survey_store:
        raise HTTPException(status_code=503, detail="Survey store unavailable")
    try:
        summary = _main.survey_store.get_route_summary(route_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Route not found") from exc
    return {"status": "ok", "summary": summary}


@router.post("/api/surveys/routes/import", tags=["Field Survey"])
async def import_field_route(
    file: UploadFile = File(...),
    project_id: str = Query(default=""),
    site_id: str = Query(default=""),
    name: str = Query(default=""),
    route_type: str = Query(default="transect"),
):
    if not _main.survey_store:
        raise HTTPException(status_code=503, detail="Survey store unavailable")
    raw = await _main._read_upload(file, max_bytes=10 * 1024 * 1024)
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        content = raw.decode("utf-8-sig", errors="replace")
    try:
        route = _main.survey_store.import_route(
            project_id=project_id,
            site_id=site_id,
            name=name,
            route_type=route_type,
            filename=file.filename or "route.geojson",
            content=content,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid route file: {exc}"
        ) from exc
    return {"status": "ok", "route": route}


@router.get("/api/surveys/routes/{route_id}/export", tags=["Field Survey"])
async def export_field_route(route_id: str, format: str = Query(default="geojson")):
    if not _main.survey_store:
        raise HTTPException(status_code=503, detail="Survey store unavailable")
    try:
        exported = _main.survey_store.export_route(route_id, format)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Route not found") from exc
    return Response(
        content=exported["content"],
        media_type=exported["media_type"],
        headers={"Content-Disposition": f"attachment; filename={exported['filename']}"},
    )


@router.get("/api/surveys/routes/{route_id}/report/export", tags=["Field Survey"])
async def export_field_route_report(route_id: str, format: str = Query(default="json")):
    if not _main.survey_store:
        raise HTTPException(status_code=503, detail="Survey store unavailable")
    try:
        exported = _main.survey_store.export_route_report(route_id, format)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Route not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=exported["content"],
        media_type=exported["media_type"],
        headers={"Content-Disposition": f"attachment; filename={exported['filename']}"},
    )


@router.get("/api/surveys/observations", tags=["Field Survey"])
async def list_field_observations(
    project_id: str = Query(default=""),
    site_id: str = Query(default=""),
    event_id: str = Query(default=""),
    program: str = Query(default=""),
    protocol: str = Query(default=""),
    jurisdiction: str = Query(default=""),
):
    if not _main.survey_store:
        return {"total": 0, "observations": []}
    observations = _main.survey_store.list_observations(
        project_id=project_id,
        site_id=site_id,
        event_id=event_id,
        program=program,
        protocol=protocol,
        jurisdiction=jurisdiction,
    )
    return {"total": len(observations), "observations": observations}


@router.post("/api/surveys/observations", tags=["Field Survey"])
async def create_field_observation(req: ObservationRecordRequest):
    if not _main.survey_store:
        raise HTTPException(status_code=503, detail="Survey store unavailable")
    observation = _main.survey_store.upsert_observation(_main._model_to_dict(req))
    return {"status": "ok", "observation": observation}


@router.get("/api/surveys/tracks", tags=["Field Survey"])
async def list_field_tracks(
    project_id: str = Query(default=""),
    site_id: str = Query(default=""),
):
    if not _main.survey_store:
        return {"total": 0, "tracks": []}
    tracks = _main.survey_store.list_tracks(project_id=project_id, site_id=site_id)
    return {"total": len(tracks), "tracks": tracks}


@router.post("/api/surveys/tracks", tags=["Field Survey"])
async def create_field_track(req: TrackLogRequest):
    if not _main.survey_store:
        raise HTTPException(status_code=503, detail="Survey store unavailable")
    track = _main.survey_store.upsert_track(_main._model_to_dict(req))
    return {"status": "ok", "track": track}


@router.post("/api/surveys/offline/map-packages", tags=["Field Survey"])
async def create_map_package(req: MapPackageRequest):
    if not _main.survey_store:
        raise HTTPException(status_code=503, detail="Survey store unavailable")
    package = _main.survey_store.create_map_package(_main._model_to_dict(req))
    return {"status": "ok", "package": package}


@router.get("/api/surveys/design-assets", tags=["Field Survey"])
async def list_design_assets(
    project_id: str = Query(default=""),
    site_id: str = Query(default=""),
    asset_type: str = Query(default=""),
    program: str = Query(default=""),
    submodule: str = Query(default=""),
    protocol: str = Query(default=""),
):
    if not _main.survey_store:
        return {"total": 0, "design_assets": []}
    assets = _main.survey_store.list_design_assets(
        project_id=project_id,
        site_id=site_id,
        asset_type=asset_type,
        program=program,
        submodule=submodule,
        protocol=protocol,
    )
    return {"total": len(assets), "design_assets": assets}


@router.post("/api/surveys/design-assets", tags=["Field Survey"])
async def create_design_asset(req: DesignAssetRequest):
    if not _main.survey_store:
        raise HTTPException(status_code=503, detail="Survey store unavailable")
    asset = _main.survey_store.upsert_design_asset(_main._model_to_dict(req))
    return {"status": "ok", "design_asset": asset}


@router.get("/api/surveys/events", tags=["Field Survey"])
async def list_sampling_events(
    project_id: str = Query(default=""),
    site_id: str = Query(default=""),
    event_id: str = Query(default=""),
    design_asset_id: str = Query(default=""),
    program: str = Query(default=""),
    submodule: str = Query(default=""),
    protocol: str = Query(default=""),
    jurisdiction: str = Query(default=""),
):
    if not _main.survey_store:
        return {"total": 0, "events": []}
    events = _main.survey_store.list_events(
        project_id=project_id,
        site_id=site_id,
        event_id=event_id,
        design_asset_id=design_asset_id,
        program=program,
        submodule=submodule,
        protocol=protocol,
        jurisdiction=jurisdiction,
    )
    return {"total": len(events), "events": events}


@router.post("/api/surveys/events", tags=["Field Survey"])
async def create_sampling_event(req: SamplingEventRequest):
    if not _main.survey_store:
        raise HTTPException(status_code=503, detail="Survey store unavailable")
    event = _main.survey_store.upsert_event(_main._model_to_dict(req))
    return {"status": "ok", "event": event}


@router.post("/api/surveys/exports/{jurisdiction}", tags=["Field Survey"])
async def create_survey_export(jurisdiction: str, req: ExportJobRequest):
    if not _main.survey_store:
        raise HTTPException(status_code=503, detail="Survey store unavailable")
    export_job = _main.survey_store.create_export_job(jurisdiction, _main._model_to_dict(req))
    return {
        "status": "ok",
        "export_job": export_job,
        "summary": export_job.get("summary", {}),
    }


@router.post("/api/surveys/sync/push", tags=["Field Survey"])
async def push_field_sync(req: SyncPushRequest):
    if not _main.survey_store:
        raise HTTPException(status_code=503, detail="Survey store unavailable")
    result = _main.survey_store.sync_push(
        device_id=req.device_id,
        user_id=req.user_id,
        operations=[_main._model_to_dict(item) for item in req.operations],
    )
    return {"status": "ok", "sync_job": result}


@router.get("/api/surveys/sync/conflicts", tags=["Field Survey"])
async def list_sync_conflicts(limit: int = Query(default=100, ge=1, le=500)):
    """List recent sync conflicts (open + resolved) for the conflict drawer."""
    if not _main.survey_store:
        return {"total": 0, "conflicts": []}
    conflicts = _main.survey_store.get_conflicts(limit=limit)
    return {"total": len(conflicts), "conflicts": conflicts}


@router.post(
    "/api/surveys/sync/conflicts/{conflict_id}/resolve",
    tags=["Field Survey"],
)
async def resolve_sync_conflict(conflict_id: str, req: ConflictResolveRequest):
    """Apply the operator's chosen strategy for a stored sync conflict.

    See ``ConflictResolveRequest`` for the three accepted strategies. The
    response payload mirrors ``survey_store.resolve_conflict`` and is the
    authoritative post-resolution state of the entity (so the client can
    refresh local cache without a follow-up pull).
    """
    if not _main.survey_store:
        raise HTTPException(status_code=503, detail="Survey store unavailable")
    try:
        result = _main.survey_store.resolve_conflict(
            conflict_id,
            strategy=req.strategy,
            merged_payload=req.merged_payload,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "ok", "resolution": result}


@router.get("/api/surveys/sync/pull", tags=["Field Survey"])
async def pull_field_sync(since: str = Query(default="")):
    if not _main.survey_store:
        return {
            "projects": [],
            "sites": [],
            "routes": [],
            "observations": [],
            "tracks": [],
            "attachments": [],
            "map_packages": [],
            "design_assets": [],
            "events": [],
            "export_jobs": [],
            "conflicts": [],
            "pulled_at": datetime.now().isoformat(),
        }
    return _main.survey_store.sync_pull(since=since)
