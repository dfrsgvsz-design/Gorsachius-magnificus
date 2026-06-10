"""DwC export, reports, CSV/JSON export."""

import csv
import io
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

import main as _main
from models.schemas import DwCExportRequest

router = APIRouter(tags=["Detections"])


@router.get("/api/export/detections")
async def export_detections(session_id: Optional[str] = Query(default=None)):
    """Export detection records as CSV."""
    records = []
    if _main.det_store:
        if session_id:
            records = _main.det_store.get_session_detections(session_id)
        else:
            records = (
                _main.det_store.get_all_detections()
                if hasattr(_main.det_store, "get_all_detections")
                else []
            )

    if not records and session_id in _main.detection_history:
        records = _main.detection_history[session_id]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "species_scientific",
            "species_chinese",
            "species_english",
            "confidence",
            "reliable",
            "time_start",
            "time_end",
            "session_id",
            "verified",
            "ood_detected",
        ]
    )
    for r in records:
        writer.writerow(
            [
                r.get("species_scientific", ""),
                r.get(
                    "species_chinese",
                    _main.species_to_chinese.get(r.get("species_scientific", ""), ""),
                ),
                r.get(
                    "species_english",
                    _main.species_to_english.get(r.get("species_scientific", ""), ""),
                ),
                r.get("confidence", ""),
                r.get("reliable", ""),
                r.get("time_start", ""),
                r.get("time_end", ""),
                r.get("session_id", session_id or ""),
                r.get("verified", ""),
                r.get("_meta", {}).get("ood_detected", ""),
            ]
        )

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=detections.csv"},
    )


@router.post("/api/export/darwin-core", tags=["Export"])
async def export_darwin_core(req: DwCExportRequest):
    """Export detections as a Darwin Core Archive ZIP file."""
    detections = _main.dwc_exporter.get_filtered_detections(
        species_filter=req.species_filter,
        date_start=req.date_start,
        date_end=req.date_end,
        min_confidence=req.min_confidence,
        verified_only=req.verified_only,
    )
    if not detections:
        raise HTTPException(
            status_code=404, detail="No detections match the filter criteria"
        )
    zip_path = _main.dwc_exporter.export_archive(detections, req.metadata)
    from fastapi.responses import FileResponse as FR

    return FR(
        str(zip_path),
        media_type="application/zip",
        filename=f"dwca_{req.metadata.get('dataset_name', 'export')}.zip",
    )
