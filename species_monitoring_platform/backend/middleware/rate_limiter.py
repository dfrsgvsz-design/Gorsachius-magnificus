"""Rate limiting middleware for the Biodiversity Field Survey Platform."""

import os
import sys
import time as _time
from collections import OrderedDict as _OrderedDict

from fastapi.responses import JSONResponse

_RATE_LIMIT = 60
_SURVEY_RATE_LIMIT = 60
_TILE_RATE_LIMIT = int(os.environ.get("TILE_RATE_LIMIT", "600"))
_RATE_WINDOW = 60
_RATE_MAX_CLIENTS = int(os.environ.get("RATE_MAX_CLIENTS", "10000"))
_rate_limits: _OrderedDict[str, list[float]] = _OrderedDict()
_rate_gc_counter = 0
_RATE_GC_INTERVAL = 100


def _rate_state():
    state = sys.modules.get("main")
    if state is None or not hasattr(state, "_rate_limits"):
        state = sys.modules[__name__]
    rate_limits = getattr(state, "_rate_limits", _rate_limits)
    if not isinstance(rate_limits, _OrderedDict):
        rate_limits = _OrderedDict(rate_limits or {})
        setattr(state, "_rate_limits", rate_limits)
    if not hasattr(state, "_rate_gc_counter"):
        setattr(state, "_rate_gc_counter", _rate_gc_counter)
    return state, rate_limits


def _rate_limit_bucket_for_path(path: str) -> tuple[str, int]:
    if path.startswith("/api/map-tiles/") or path.startswith("/api/maps/tiles/"):
        return "tiles", _TILE_RATE_LIMIT
    if path.startswith("/api/surveys"):
        return "survey", _SURVEY_RATE_LIMIT
    return "general", _RATE_LIMIT


async def rate_limit_middleware(request, call_next):
    path = request.url.path
    # `/api/health` and its readiness/liveness subpaths (B10) stay unmetered so
    # container healthchecks and load balancer probes are never throttled.
    if (
        not path.startswith("/api")
        or path == "/api/health"
        or path.startswith("/api/health/")
    ):
        return await call_next(request)

    global _rate_gc_counter
    state, rate_limits = _rate_state()
    client_ip = request.client.host if request.client else "unknown"
    bucket_name, bucket_limit = _rate_limit_bucket_for_path(path)
    bucket_key = f"{client_ip}:{bucket_name}"
    now = _time.time()

    timestamps = rate_limits.get(bucket_key, [])
    timestamps = [t for t in timestamps if now - t < _RATE_WINDOW]

    if len(timestamps) >= bucket_limit:
        rate_limits[bucket_key] = timestamps
        rate_limits.move_to_end(bucket_key)
        return JSONResponse(
            status_code=429,
            content={
                "detail": f"Rate limit exceeded for {bucket_name} API traffic. Max {bucket_limit} requests per minute."
            },
        )
    timestamps.append(now)
    rate_limits[bucket_key] = timestamps
    rate_limits.move_to_end(bucket_key)

    state._rate_gc_counter = int(getattr(state, "_rate_gc_counter", 0)) + 1
    _rate_gc_counter = state._rate_gc_counter
    if state._rate_gc_counter >= _RATE_GC_INTERVAL:
        state._rate_gc_counter = 0
        _rate_gc_counter = 0
        stale = [
            k
            for k, ts in rate_limits.items()
            if not ts or now - ts[-1] > _RATE_WINDOW * 2
        ]
        for k in stale:
            del rate_limits[k]

    while len(rate_limits) > _RATE_MAX_CLIENTS:
        rate_limits.popitem(last=False)

    return await call_next(request)
