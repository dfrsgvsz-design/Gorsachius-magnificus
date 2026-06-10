"""Real-time monitoring, WebSocket streaming, and session endpoints."""

import json
import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["Monitoring"])
logger = logging.getLogger("field_survey_platform")


@router.websocket("/ws/stream/{device_id}")
async def websocket_audio_stream(websocket: WebSocket, device_id: str):
    """WebSocket endpoint for real-time audio streaming from field devices."""
    import main as _m

    await websocket.accept()

    device = _m.device_mgr.get(device_id)
    if not device:
        await websocket.send_json({"error": "Device not registered", "code": 404})
        await websocket.close()
        return

    session_id = None
    try:
        config = await websocket.receive_json()
        if config.get("action") != "start":
            await websocket.send_json({"error": "Expected start action"})
            await websocket.close()
            return

        sample_rate = config.get("sample_rate", device.sample_rate)
        threshold = config.get("threshold", 0.3)

        session_id = _m.device_mgr.start_session(device_id)
        session = _m.rt_processor.create_session(
            device_id=device_id,
            session_id=session_id,
            sample_rate=sample_rate,
            confidence_threshold=threshold,
        )

        await websocket.send_json(
            {
                "event": "session_started",
                "session_id": session_id,
                "device_id": device_id,
                "sample_rate": sample_rate,
                "threshold": threshold,
            }
        )

        while True:
            message = await websocket.receive()

            if "text" in message:
                try:
                    data = json.loads(message["text"])
                except (json.JSONDecodeError, ValueError):
                    await websocket.send_json(
                        {"event": "error", "detail": "Invalid JSON"}
                    )
                    continue
                if data.get("action") == "stop":
                    break
                elif data.get("action") == "heartbeat":
                    _m.device_mgr.heartbeat(device_id)
                    await websocket.send_json({"event": "heartbeat_ack"})
                continue

            if "bytes" in message:
                pcm_bytes = message["bytes"]
                _m.device_mgr.heartbeat(device_id)

                new_detections = await _m.rt_processor.process_audio(
                    session_id, pcm_bytes
                )

                if new_detections:
                    _m.device_mgr.increment_stats(
                        device_id,
                        recordings=1,
                        detections=len(new_detections),
                    )
                    summary = session.get_summary()
                    await websocket.send_json(
                        {
                            "event": "detections",
                            "new_detections": new_detections,
                            "summary": {
                                "unique_species": summary["unique_species"],
                                "total_detections": summary["total_detections"],
                                "duration": summary["duration_seconds"],
                                "species_counts": summary["species_counts"],
                            },
                            "accumulation": session.get_accumulation_data(),
                        }
                    )

    except WebSocketDisconnect:
        logger.info("Device %s disconnected", device_id)
    except Exception as e:
        logger.exception("WebSocket error for %s: %s", device_id, e)
    finally:
        if session_id:
            final_summary = _m.rt_processor.end_session(session_id)
            _m.device_mgr.end_session(device_id)
            session = _m.rt_processor.get_session(session_id)
            if session:
                _m.detection_history[session_id] = session.all_detections
                if _m.det_store and session.all_detections:
                    site_name = device.location_name if device else "unknown"
                    persisted = []
                    for det in session.all_detections:
                        persisted.append(
                            {
                                **det,
                                "species": det.get("species")
                                or det.get("species_scientific", ""),
                                "device_id": device_id,
                                "site_name": site_name or "unknown",
                                "model_version": _m._current_model_version(),
                            }
                        )
                    _m.det_store.batch_add(
                        persisted,
                        session_id=session_id,
                        site_name=site_name or "unknown",
                    )
                    _m.det_store.save()
            _m.rt_processor.remove_session(session_id)
            logger.info("Session %s ended: %s", session_id, final_summary)


@router.get("/api/monitoring/sessions")
async def list_monitoring_sessions():
    """List all active monitoring sessions."""
    import main as _m

    sessions = _m.rt_processor.list_sessions()
    return {"total": len(sessions), "sessions": sessions}


@router.get("/api/monitoring/sessions/{session_id}")
async def get_monitoring_session(session_id: str):
    """Get details of a monitoring session."""
    import main as _m

    session = _m.rt_processor.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session": session.get_summary(),
        "accumulation": session.get_accumulation_data(),
        "detections": session.all_detections[-50:],
    }


@router.get("/api/monitoring/dashboard")
async def monitoring_dashboard():
    """Aggregated dashboard data: all devices + all active sessions."""
    import main as _m

    sessions = _m.rt_processor.list_sessions()
    devices = _m.device_mgr.list_all()

    all_species = {}
    total_detections = 0
    for s in sessions:
        total_detections += s.get("total_detections", 0)
        for sp, count in s.get("species_counts", {}).items():
            all_species[sp] = all_species.get(sp, 0) + count

    return {
        "devices": {"total": len(devices), "online": _m.device_mgr.online_count},
        "sessions": {
            "total": len(sessions),
            "active": sum(1 for s in sessions if s.get("is_active")),
        },
        "detections": {
            "total": total_detections,
            "unique_species": len(all_species),
            "top_species": sorted(all_species.items(), key=lambda x: -x[1])[:20],
        },
        "map_data": _m.device_mgr.get_map_data(),
    }
