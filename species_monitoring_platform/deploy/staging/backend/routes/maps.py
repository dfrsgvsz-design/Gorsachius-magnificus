"""Tile proxy and map package endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

router = APIRouter(tags=["Health"])
logger = logging.getLogger("field_survey_platform")


@router.get("/api/map-tiles/{z}/{x}/{y}")
@router.get("/api/maps/tiles/{z}/{x}/{y}")
async def proxy_map_tile(
    z: int,
    x: int,
    y: int,
    s: Optional[str] = Query(default=None, min_length=1, max_length=8),
):
    """Proxy map tiles through the API origin so the service worker can cache them offline."""
    import main as _m

    upstream_url = _m._build_upstream_tile_url(z, x, y, s)
    if not _m._is_remote_tile_source_url(upstream_url):
        raise HTTPException(
            status_code=503, detail="Tile proxy requires a remote tile source URL"
        )

    try:
        import httpx

        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            upstream_response = await client.get(
                upstream_url,
                headers={
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                    "User-Agent": "biodiversity-field-survey-platform-tile-proxy/1.0",
                },
            )
    except Exception as exc:
        logger.warning("Tile proxy request failed for %s: %s", upstream_url, exc)
        raise HTTPException(
            status_code=502, detail="Tile upstream unavailable"
        ) from exc

    response_headers = {}
    for header_name in ("Cache-Control", "ETag", "Last-Modified", "Expires"):
        header_value = upstream_response.headers.get(header_name)
        if header_value:
            response_headers[header_name] = header_value

    response_headers.setdefault("Cache-Control", "public, max-age=86400")

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers,
        media_type=upstream_response.headers.get("Content-Type"),
    )
