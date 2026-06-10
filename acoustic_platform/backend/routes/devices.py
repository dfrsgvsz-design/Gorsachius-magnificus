"""Device management and registration endpoints."""

from fastapi import APIRouter, HTTPException

import main as _main
from models.schemas import DeviceRegisterRequest

router = APIRouter(tags=["Devices"])


@router.post("/api/devices/register")
async def register_device(req: DeviceRegisterRequest):
    """Register a new field recording device."""
    device = _main.device_mgr.register(
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
    if not _main.device_mgr.unregister(device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    return {"status": "ok", "message": f"Device {device_id} removed"}


@router.get("/api/devices")
async def list_devices():
    """List all registered devices."""
    devices = _main.device_mgr.list_all()
    return {
        "total": len(devices),
        "online": _main.device_mgr.online_count,
        "devices": devices,
    }


@router.get("/api/devices/online")
async def list_online_devices():
    """List online devices only."""
    devices = _main.device_mgr.list_online()
    return {"total": len(devices), "devices": devices}


@router.get("/api/devices/map")
async def device_map_data():
    """Get device locations for map visualization."""
    return {"markers": _main.device_mgr.get_map_data()}


@router.post("/api/devices/{device_id}/heartbeat")
async def device_heartbeat(device_id: str):
    """Device heartbeat to keep alive."""
    if not _main.device_mgr.heartbeat(device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    return {"status": "ok"}
