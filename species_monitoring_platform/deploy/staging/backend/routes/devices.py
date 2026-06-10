"""Device management endpoints."""

from fastapi import APIRouter, HTTPException

from models.schemas import DeviceRegisterRequest

router = APIRouter(tags=["Devices"])


@router.post("/api/devices/register")
async def register_device(req: DeviceRegisterRequest):
    """Register a new field recording device."""
    import main as _m

    device = _m.device_mgr.register(
        name=req.name,
        device_type=req.device_type,
        location_name=req.location_name,
        latitude=req.latitude,
        longitude=req.longitude,
        altitude=req.altitude,
        sample_rate=req.sample_rate,
        channels=req.channels,
        bit_depth=req.bit_depth,
        metadata=req.metadata,
    )
    return {"status": "ok", "device": device.to_dict()}


@router.delete("/api/devices/{device_id}")
async def unregister_device(device_id: str):
    """Unregister a device."""
    import main as _m

    if not _m.device_mgr.unregister(device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    return {"status": "ok", "message": f"Device {device_id} removed"}


@router.get("/api/devices")
async def list_devices():
    """List all registered devices."""
    import main as _m

    devices = _m.device_mgr.list_all()
    return {
        "total": len(devices),
        "online": _m.device_mgr.online_count,
        "devices": devices,
    }


@router.get("/api/devices/online")
async def list_online_devices():
    """List online devices only."""
    import main as _m

    devices = _m.device_mgr.list_online()
    return {"total": len(devices), "devices": devices}


@router.get("/api/devices/map")
async def device_map_data():
    """Get device locations for map visualization."""
    import main as _m

    return {"markers": _m.device_mgr.get_map_data()}


@router.post("/api/devices/{device_id}/heartbeat")
async def device_heartbeat(device_id: str):
    """Device heartbeat to keep alive."""
    import main as _m

    if not _m.device_mgr.heartbeat(device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    return {"status": "ok"}
