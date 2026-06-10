"""Alert configuration and webhook validation endpoints."""

import ipaddress
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException

from models.schemas import AlertConfigRequest

router = APIRouter(tags=["Alerts"])


def validate_webhook_url(url: str) -> bool:
    """Reject non-HTTPS URLs and URLs that resolve to private/internal networks."""
    parsed = urlparse(url)
    if parsed.scheme not in ("https",):
        return False
    hostname = parsed.hostname or ""
    if hostname.lower() in ("localhost", ""):
        return False
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_reserved:
            return False
    except ValueError:
        pass
    return True


@router.post("/api/alerts/configure")
async def configure_alerts(req: AlertConfigRequest):
    """Configure detection alert push notifications."""
    import main as _m

    for label, hook_url in [
        ("wechat_webhook", req.wechat_webhook),
        ("dingtalk_webhook", req.dingtalk_webhook),
    ]:
        if hook_url and not validate_webhook_url(hook_url):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid {label}: must be an HTTPS URL pointing to a public host.",
            )
    _m.alert_pusher.configure(
        target_species=req.target_species,
        min_confidence=req.min_confidence,
        wechat_webhook=req.wechat_webhook,
        dingtalk_webhook=req.dingtalk_webhook,
        email=req.email,
        platform_url=req.platform_url,
    )
    return {"status": "ok", "config": _m.alert_pusher.get_config()}


@router.get("/api/alerts/config")
async def get_alert_config():
    """Get current alert configuration."""
    import main as _m

    return _m.alert_pusher.get_config()
