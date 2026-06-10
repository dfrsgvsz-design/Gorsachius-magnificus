"""Survey audit logging middleware (B20).

Records every mutating operation (POST/PUT/PATCH/DELETE) against the survey
and device APIs into the ``survey_audit_log`` table managed by
``survey_store.SurveyStore``: who (device_id/user_id/ip), what (op,
entity_type, entity_id), when (UTC timestamp), and the outcome (status code,
request id).

Identity attribution is best-effort: clients send ``X-Device-Id`` /
``X-User-Id`` headers (the sync payload also carries them in the body, which
stays untouched here to avoid double-reading the request stream).
"""

import logging
import re
import sys

logger = logging.getLogger(__name__)

_AUDITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_AUDITED_PREFIXES = ("/api/surveys", "/api/devices")

_ENTITY_TYPE_BY_SEGMENT = {
    "projects": "project",
    "sites": "site",
    "routes": "route",
    "observations": "observation",
    "tracks": "track",
    "events": "event",
    "design-assets": "design_asset",
    "map-packages": "map_package",
    "exports": "export_job",
    "sync": "sync",
    "trash": "trash",
}
_RESTORE_RE = re.compile(r"/restore/?$")


def classify_operation(method: str, path: str) -> tuple[str, str, str]:
    """Return (op, entity_type, entity_id) for an audited request path."""
    segments = [seg for seg in path.split("/") if seg]
    entity_type = ""
    entity_id = ""

    if len(segments) >= 2 and segments[1] == "devices":
        entity_type = "device"
        entity_id = segments[2] if len(segments) > 2 else ""
    elif len(segments) >= 2 and segments[1] == "surveys":
        if len(segments) == 2:
            entity_type = "legacy_site"
        elif segments[2] in _ENTITY_TYPE_BY_SEGMENT:
            entity_type = _ENTITY_TYPE_BY_SEGMENT[segments[2]]
            if len(segments) > 3:
                entity_id = segments[3]
        elif segments[2] == "offline" and len(segments) > 3:
            entity_type = _ENTITY_TYPE_BY_SEGMENT.get(segments[3], segments[3])
        else:
            # Legacy DELETE /api/surveys/{site_name}
            entity_type = "legacy_site"
            entity_id = segments[2]

    if _RESTORE_RE.search(path):
        op = "restore"
        if len(segments) >= 2:
            entity_id = segments[-2]
    elif entity_type == "sync":
        op = "sync_push" if segments[-1] == "push" else "sync"
        entity_id = ""
    elif method == "DELETE":
        op = "delete"
    elif method == "POST":
        op = "create_or_update"
    else:
        op = "update"
    return op, entity_type, entity_id


def resolve_client_ip(request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def _survey_store():
    state = sys.modules.get("main")
    return getattr(state, "survey_store", None) if state else None


async def audit_log_middleware(request, call_next):
    method = request.method.upper()
    path = request.url.path
    if method not in _AUDITED_METHODS or not path.startswith(_AUDITED_PREFIXES):
        return await call_next(request)

    response = await call_next(request)

    try:
        store = _survey_store()
        if store is not None and hasattr(store, "append_audit_entry"):
            op, entity_type, entity_id = classify_operation(method, path)
            store.append_audit_entry(
                {
                    "device_id": request.headers.get("X-Device-Id", "").strip(),
                    "user_id": request.headers.get("X-User-Id", "").strip(),
                    "op": op,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "method": method,
                    "path": path,
                    "ip": resolve_client_ip(request),
                    "status_code": int(getattr(response, "status_code", 0) or 0),
                    "request_id": str(
                        getattr(request.state, "request_id", "") or ""
                    ),
                }
            )
    except Exception:  # noqa: BLE001 - auditing must never break the request
        logger.exception(
            "Failed to write survey audit log entry for %s %s", method, path
        )
    return response
