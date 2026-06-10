"""Image upload, camera trap processing, and record management endpoints."""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

router = APIRouter(tags=["Image"])
logger = logging.getLogger("field_survey_platform")


@router.post("/api/image/analyze")
async def analyze_image(
    file: UploadFile = File(...),
    site_name: str | None = Query(default=None),
    notes: str | None = Query(default=None),
):
    """Upload a bird photo for EXIF extraction, classification, and database storage."""
    import main as _m
    from image_processor import classify_image, create_thumbnail, extract_exif

    content = await _m._read_upload(file, _m.MAX_IMAGE_BYTES)
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    exif = extract_exif(content)
    if "error" in exif:
        raise HTTPException(status_code=400, detail=exif["error"])

    thumbnail = create_thumbnail(content)
    classification = classify_image(content, top_k=5)
    bird_predictions = [p for p in classification if p.get("is_bird_related")]
    top_label = classification[0]["label"] if classification else "unknown"

    record_id = str(uuid.uuid4())[:8]
    record = {
        "id": record_id,
        "filename": file.filename or "image",
        "uploaded_at": datetime.now().isoformat(),
        "exif": exif,
        "latitude": exif.get("latitude"),
        "longitude": exif.get("longitude"),
        "datetime": exif.get("datetime"),
        "camera": f"{exif.get('camera_make', '')} {exif.get('camera_model', '')}".strip()
        or None,
        "site_name": site_name,
        "notes": notes,
        "top_classification": top_label,
        "bird_predictions": bird_predictions,
        "all_predictions": classification[:5],
    }
    _m._image_records.append(record)
    _m._save_image_records()

    return {
        "id": record_id,
        "exif": exif,
        "thumbnail": thumbnail,
        "classification": classification[:5],
        "bird_predictions": bird_predictions,
        "top_label": top_label,
        "stored": True,
    }


@router.get("/api/image/records")
async def list_image_records(offset: int = 0, limit: int = 100):
    """List stored image analysis records with pagination."""
    import main as _m

    limit = min(limit, 500)
    page = _m._image_records[offset : offset + limit]
    return {
        "total": len(_m._image_records),
        "offset": offset,
        "limit": limit,
        "records": page,
    }


@router.post("/api/trap/analyze", tags=["Camera Trap"])
async def analyze_trap_image(
    file: UploadFile = File(...),
    site_name: str | None = Query(default=None),
    detect_animals: bool = Query(default=True),
):
    """Upload an infrared camera trap image for processing and animal detection."""
    import main as _m
    from camera_trap_processor import (
        create_ir_thumbnail,
        detect_animals_basic,
        extract_trap_metadata,
    )

    content = await _m._read_upload(file, _m.MAX_IMAGE_BYTES)
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    meta = extract_trap_metadata(content)
    if "error" in meta:
        raise HTTPException(status_code=400, detail=meta["error"])

    thumbnail = create_ir_thumbnail(content)
    detections = detect_animals_basic(content) if detect_animals else []
    animal_detections = [d for d in detections if "note" not in d]

    record_id = str(uuid.uuid4())[:8]
    record = {
        "id": record_id,
        "filename": file.filename or "trap_image",
        "uploaded_at": datetime.now().isoformat(),
        "metadata": meta,
        "latitude": meta.get("latitude"),
        "longitude": meta.get("longitude"),
        "datetime": meta.get("datetime"),
        "is_ir": meta.get("is_ir", False),
        "site_name": site_name,
        "detections": animal_detections,
        "animal_count": len(animal_detections),
    }
    _m._trap_records.append(record)
    _m._save_trap_records()

    return {
        "id": record_id,
        "metadata": meta,
        "thumbnail": thumbnail,
        "detections": detections,
        "animal_count": len(animal_detections),
        "stored": True,
    }


@router.get("/api/trap/records", tags=["Camera Trap"])
async def list_trap_records(offset: int = 0, limit: int = 100):
    """List camera trap analysis records with pagination."""
    import main as _m

    limit = min(limit, 500)
    page = _m._trap_records[offset : offset + limit]
    return {
        "total": len(_m._trap_records),
        "offset": offset,
        "limit": limit,
        "records": page,
    }


@router.get("/api/trap/sequences", tags=["Camera Trap"])
async def get_trap_sequences(max_gap: int = Query(default=60, ge=10, le=600)):
    """Group camera trap records into event sequences by timestamp."""
    import main as _m
    from camera_trap_processor import group_sequences

    seqs = group_sequences(_m._trap_records, max_gap_seconds=max_gap)
    return {"total_sequences": len(seqs), "sequences": seqs}
