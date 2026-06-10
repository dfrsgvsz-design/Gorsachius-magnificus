"""Alert configuration and webhook management."""

from fastapi import APIRouter

import main as _main
from models.schemas import AlertConfigRequest

router = APIRouter(tags=["Alerts"])


@router.post("/api/alerts/configure")
async def configure_alerts(req: AlertConfigRequest):
    """Configure detection alert push notifications."""
    _main.alert_pusher.configure(
        target_species=req.target_species,
        min_confidence=req.min_confidence,
        wechat_webhook=req.wechat_webhook,
        dingtalk_webhook=req.dingtalk_webhook,
        email=req.email,
        platform_url=req.platform_url,
    )
    return {"status": "ok", "config": _main.alert_pusher.get_config()}


@router.get("/api/alerts/config")
async def get_alert_config():
    """Get current alert configuration."""
    return _main.alert_pusher.get_config()
