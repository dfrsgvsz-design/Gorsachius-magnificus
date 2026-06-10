"""Platform configuration endpoint."""

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/api/config")
async def platform_config_endpoint():
    """Return platform configuration for the frontend."""
    import main as _m

    return _m._serialize_platform_config_for_frontend()
