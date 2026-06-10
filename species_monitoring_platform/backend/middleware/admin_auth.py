"""Admin token verification for destructive survey endpoints (B19).

Protects DELETE / restore endpoints with an ``X-Admin-Token`` header that is
derived from the same PIN the field lead configures in the frontend AdminGate
(``frontend/src/lib/adminAuth.js``). Both sides compute

    PBKDF2-HMAC-SHA256(pin, salt="gm-admin-token-v1", iterations=100000) -> hex

so the operator only has to share one PIN between the device and the server
``.env`` (``ADMIN_PIN``). Alternatively ``ADMIN_API_TOKEN`` can be set to the
final token value directly (takes precedence over ``ADMIN_PIN``).

Backward compatibility: when neither env var is configured the dependency
allows every request (mirrors the ``BIRD_API_KEY`` opt-in pattern) so local
development and the hybrid-local APK keep working. Production deployments
MUST set one of the two variables.
"""

import hashlib
import hmac
import logging
import os
from functools import lru_cache

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

ADMIN_TOKEN_HEADER = "X-Admin-Token"
_TOKEN_SALT = b"gm-admin-token-v1"
_TOKEN_ITERATIONS = 100_000
_warned_disabled = False


@lru_cache(maxsize=8)
def derive_admin_token(pin: str) -> str:
    """Derive the shared admin token from a numeric PIN (same as frontend)."""
    return hashlib.pbkdf2_hmac(
        "sha256", pin.encode("utf-8"), _TOKEN_SALT, _TOKEN_ITERATIONS
    ).hex()


def expected_admin_token() -> str:
    """Resolve the expected token from env. Empty string means auth disabled."""
    direct = os.environ.get("ADMIN_API_TOKEN", "").strip()
    if direct:
        return direct
    pin = os.environ.get("ADMIN_PIN", "").strip()
    if pin:
        return derive_admin_token(pin)
    return ""


def admin_auth_enabled() -> bool:
    return bool(expected_admin_token())


async def verify_admin_token(request: Request) -> None:
    """FastAPI dependency guarding destructive admin operations."""
    global _warned_disabled
    expected = expected_admin_token()
    if not expected:
        if not _warned_disabled:
            logger.warning(
                "Admin token auth is DISABLED (set ADMIN_PIN or ADMIN_API_TOKEN "
                "to protect DELETE/restore endpoints in production)."
            )
            _warned_disabled = True
        return
    provided = request.headers.get(ADMIN_TOKEN_HEADER, "").strip()
    if not provided or not hmac.compare_digest(
        provided.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing admin token",
            headers={"WWW-Authenticate": ADMIN_TOKEN_HEADER},
        )
