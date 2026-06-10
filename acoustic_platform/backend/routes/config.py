"""Platform configuration endpoints."""

from fastapi import APIRouter

import main as _main

router = APIRouter(tags=["Health"])


@router.get("/api/config")
async def platform_config_endpoint():
    """Return platform configuration for the frontend."""
    return _main._serialize_platform_config_for_frontend()
