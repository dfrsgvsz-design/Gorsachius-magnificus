"""Multimodal survey endpoints (species-specific)."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["Multimodal Survey"])
logger = logging.getLogger("field_survey_platform")

try:
    from multimodal_survey import (
        SurveySession,
        SurveyStore,
        batch_import_audio,
        batch_import_camera_trap,
    )
    from survey_report import (
        generate_csv_report,
        generate_darwin_core_archive,
        generate_json_report,
    )

    _survey_store = SurveyStore()
    _available = True
    logger.info("Multimodal survey module loaded")
except ImportError:
    _survey_store = None
    _available = False
    logger.warning("Multimodal survey module not available")


if _available and _survey_store:

    @router.get("/api/multimodal/sessions")
    async def list_multimodal_sessions():
        return {"sessions": _survey_store.list_sessions()}

    @router.post("/api/multimodal/sessions")
    async def create_multimodal_session(
        site_name: str = "",
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        habitat_type: str = "",
        observer: str = "",
    ):
        session = SurveySession(
            site_name=site_name,
            latitude=latitude,
            longitude=longitude,
            habitat_type=habitat_type,
            observer=observer,
        )
        _survey_store.save(session)
        return {"session_id": session.session_id, "status": "created"}

    @router.get("/api/multimodal/sessions/{session_id}")
    async def get_multimodal_session(session_id: str):
        session = _survey_store.load(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session.to_dict()

    @router.get("/api/multimodal/sessions/{session_id}/summary")
    async def get_multimodal_summary(session_id: str):
        session = _survey_store.load(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session.get_summary()

    @router.delete("/api/multimodal/sessions/{session_id}")
    async def delete_multimodal_session(session_id: str):
        if _survey_store.delete(session_id):
            return {"status": "deleted"}
        raise HTTPException(status_code=404, detail="Session not found")

    @router.post("/api/multimodal/sessions/{session_id}/import-images")
    async def import_camera_images(session_id: str, directory: str = ""):
        session = _survey_store.load(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        stats = batch_import_camera_trap(directory, session)
        if "error" in stats:
            raise HTTPException(status_code=400, detail=stats["error"])
        _survey_store.save(session)
        return stats

    @router.post("/api/multimodal/sessions/{session_id}/import-audio")
    async def import_audio_recordings(session_id: str, directory: str = ""):
        session = _survey_store.load(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        stats = batch_import_audio(directory, session)
        if "error" in stats:
            raise HTTPException(status_code=400, detail=stats["error"])
        _survey_store.save(session)
        return stats

    @router.post("/api/multimodal/sessions/{session_id}/manual")
    async def add_manual_record(
        session_id: str,
        species: str = "",
        count: int = 1,
        evidence_type: str = "visual",
    ):
        session = _survey_store.load(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        record = session.add_manual_record(
            species=species, count=count, evidence_type=evidence_type
        )
        _survey_store.save(session)
        return record

    @router.get("/api/multimodal/sessions/{session_id}/export/csv")
    async def export_csv(session_id: str):
        session = _survey_store.load(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        csv_content = generate_csv_report(session.get_summary())
        from starlette.responses import Response

        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=survey_{session_id}.csv"
            },
        )

    @router.get("/api/multimodal/sessions/{session_id}/export/darwin-core")
    async def export_multimodal_darwin_core(session_id: str):
        session = _survey_store.load(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        archive_bytes = generate_darwin_core_archive(session.get_summary())
        from starlette.responses import Response

        return Response(
            content=archive_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename=survey_{session_id}_dwc.zip"
            },
        )
