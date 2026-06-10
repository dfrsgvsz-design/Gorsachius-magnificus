"""Detection listing, verification, and batch operation endpoints."""

from typing import List

from fastapi import APIRouter, HTTPException, Query

from models.schemas import BatchVerifyRequest, VerifyRequest

router = APIRouter(tags=["Detections"])


@router.get("/api/detections/unverified")
async def get_unverified_detections(limit: int = Query(default=50, ge=1, le=200)):
    """Get detections needing human verification (priority: low confidence first)."""
    import main as _m

    return {"detections": _m.det_store.get_unverified(limit=limit)}


@router.post("/api/detections/verify")
async def verify_detection(req: VerifyRequest):
    """Verify a single detection: confirm, reject, or mark uncertain."""
    import main as _m
    from detection_store import VerificationStatus

    try:
        status = VerificationStatus(req.status)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Use: {[s.value for s in VerificationStatus]}",
        )
    if not _m.det_store.verify_detection(
        req.detection_id, status, req.verified_by, req.notes
    ):
        raise HTTPException(status_code=404, detail="Detection not found")
    return {
        "status": "ok",
        "detection_id": req.detection_id,
        "verification": req.status,
    }


@router.post("/api/detections/verify-batch")
async def batch_verify_detections(req: BatchVerifyRequest):
    """Batch verify multiple detections."""
    import main as _m
    from detection_store import VerificationStatus

    try:
        status = VerificationStatus(req.status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid verification status")
    count = _m.det_store.batch_verify(
        req.detection_ids, status, req.verified_by, req.notes
    )
    return {"status": "ok", "verified_count": count}


@router.get("/api/detections/stats")
async def detection_store_stats():
    """Get detection store statistics including verification rates."""
    import main as _m

    stats = _m.det_store.get_stats()
    return stats


@router.get("/api/detections/session/{session_id}")
async def get_session_stored_detections(
    session_id: str,
    verified_only: bool = Query(default=False),
):
    """Get stored detections for a session with optional verified-only filter."""
    import main as _m

    dets = _m.det_store.get_session_detections(session_id, verified_only=verified_only)
    return {"session_id": session_id, "total": len(dets), "detections": dets}


@router.get("/api/detections/site/{site_name}")
async def get_site_stored_detections(
    site_name: str,
    verified_only: bool = Query(default=False),
):
    """Get stored detections for a monitoring site."""
    import main as _m

    dets = _m.det_store.get_site_detections(site_name, verified_only=verified_only)
    return {"site_name": site_name, "total": len(dets), "detections": dets}
