"""Image upload, camera trap processing, and analysis endpoints."""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

import main as _main

router = APIRouter()


@router.post("/api/image/analyze", tags=["Image"])
async def analyze_image(
    file: UploadFile = File(...),
    site_name: Optional[str] = Query(default=None),
    notes: Optional[str] = Query(default=None),
):
    """Upload a bird photo for EXIF extraction, classification, and database storage."""
    content = await _main._read_upload(file, _main.MAX_IMAGE_BYTES)
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    exif = _main.extract_exif(content)
    if "error" in exif:
        raise HTTPException(status_code=400, detail=exif["error"])

    thumbnail = _main.create_thumbnail(content)
    classification = _main.classify_image(content, top_k=5)
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
    _main._image_records.append(record)
    _main._save_image_records()

    return {
        "id": record_id,
        "exif": exif,
        "thumbnail": thumbnail,
        "classification": classification[:5],
        "bird_predictions": bird_predictions,
        "top_label": top_label,
        "stored": True,
    }


@router.get("/api/image/records", tags=["Image"])
async def list_image_records(offset: int = 0, limit: int = 100):
    """List stored image analysis records with pagination."""
    limit = min(limit, 500)
    page = _main._image_records[offset : offset + limit]
    return {
        "total": len(_main._image_records),
        "offset": offset,
        "limit": limit,
        "records": page,
    }


# ── Camera Trap (Infrared) Processing ──

@router.post("/api/trap/analyze", tags=["Camera Trap"])
async def analyze_trap_image(
    file: UploadFile = File(...),
    site_name: Optional[str] = Query(default=None),
    detect_animals: bool = Query(default=True),
):
    """Upload an infrared camera trap image for processing and animal detection."""
    content = await _main._read_upload(file, _main.MAX_IMAGE_BYTES)
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    meta = _main.extract_trap_metadata(content)
    if "error" in meta:
        raise HTTPException(status_code=400, detail=meta["error"])

    thumbnail = _main.create_ir_thumbnail(content)
    detections = _main.detect_animals_basic(content) if detect_animals else []
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
    _main._trap_records.append(record)
    _main._save_trap_records()

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
    limit = min(limit, 500)
    page = _main._trap_records[offset : offset + limit]
    return {
        "total": len(_main._trap_records),
        "offset": offset,
        "limit": limit,
        "records": page,
    }


@router.get("/api/trap/sequences", tags=["Camera Trap"])
async def get_trap_sequences(max_gap: int = Query(default=60, ge=10, le=600)):
    """Group camera trap records into event sequences by timestamp."""
    seqs = _main.group_sequences(_main._trap_records, max_gap_seconds=max_gap)
    return {"total_sequences": len(seqs), "sequences": seqs}
