"""Real-time monitoring, WebSocket, and session endpoints."""

import json
import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

import main as _main

logger = logging.getLogger("field_survey_platform")

router = APIRouter()


@router.websocket("/ws/stream/{device_id}")
async def websocket_audio_stream(websocket: WebSocket, device_id: str):
    """
    WebSocket endpoint for real-time audio streaming from field devices.

    Protocol:
    1. Client connects with device_id
    2. Client sends JSON config: {"action": "start", "sample_rate": 22050, "threshold": 0.3}
    3. Client sends binary PCM audio frames (int16, mono)
    4. Server responds with JSON detection events
    5. Client sends {"action": "stop"} to end session
    """
    await websocket.accept()

    device = _main.device_mgr.get(device_id)
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

        session_id = _main.device_mgr.start_session(device_id)
        session = _main.rt_processor.create_session(
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
                    _main.device_mgr.heartbeat(device_id)
                    await websocket.send_json({"event": "heartbeat_ack"})
                continue

            if "bytes" in message:
                pcm_bytes = message["bytes"]
                _main.device_mgr.heartbeat(device_id)

                new_detections = await _main.rt_processor.process_audio(session_id, pcm_bytes)

                if new_detections:
                    _main.device_mgr.increment_stats(
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
            final_summary = _main.rt_processor.end_session(session_id)
            _main.device_mgr.end_session(device_id)
            session = _main.rt_processor.get_session(session_id)
            if session:
                _main.detection_history[session_id] = session.all_detections
                if _main.det_store and session.all_detections:
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
                                "model_version": _main._current_model_version(),
                            }
                        )
                    _main.det_store.batch_add(
                        persisted,
                        session_id=session_id,
                        site_name=site_name or "unknown",
                    )
                    _main.det_store.save()
            _main.rt_processor.remove_session(session_id)
            logger.info("Session %s ended: %s", session_id, final_summary)


@router.get("/api/monitoring/sessions", tags=["Monitoring"])
async def list_monitoring_sessions():
    """List all active monitoring sessions."""
    sessions = _main.rt_processor.list_sessions()
    return {"total": len(sessions), "sessions": sessions}


@router.get("/api/monitoring/sessions/{session_id}", tags=["Monitoring"])
async def get_monitoring_session(session_id: str):
    """Get details of a monitoring session."""
    session = _main.rt_processor.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session": session.get_summary(),
        "accumulation": session.get_accumulation_data(),
        "detections": session.all_detections[-50:],
    }


@router.get("/api/monitoring/dashboard", tags=["Monitoring"])
async def monitoring_dashboard():
    """Aggregated dashboard data: all devices + all active sessions."""
    sessions = _main.rt_processor.list_sessions()
    devices = _main.device_mgr.list_all()

    all_species = {}
    total_detections = 0
    for s in sessions:
        total_detections += s.get("total_detections", 0)
        for sp, count in s.get("species_counts", {}).items():
            all_species[sp] = all_species.get(sp, 0) + count

    return {
        "devices": {"total": len(devices), "online": _main.device_mgr.online_count},
        "sessions": {
            "total": len(sessions),
            "active": sum(1 for s in sessions if s.get("is_active")),
        },
        "detections": {
            "total": total_detections,
            "unique_species": len(all_species),
            "top_species": sorted(all_species.items(), key=lambda x: -x[1])[:20],
        },
        "map_data": _main.device_mgr.get_map_data(),
    }
