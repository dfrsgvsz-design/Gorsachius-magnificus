"""
Biodiversity Field Survey Platform API server.
Supports offline-first survey operations, taxonomy-aware exports,
shared field metadata, and optional acoustic analysis workflows.

Endpoints:
- POST /api/analyze            — Upload audio → CNN species detection + diversity metrics
- GET  /api/species            — Legacy bird species reference list for the acoustic workspace
- POST /api/search-xc          — Search xeno-canto for recordings
- GET  /api/diversity           — Compute biodiversity metrics from detection history
- POST /api/compare-sites      — Beta diversity between multiple sites
- WS   /ws/stream/{device_id}  — Real-time audio stream from field devices
- POST /api/devices/register   — Register a field recording device
- GET  /api/devices             — List all registered devices
- GET  /api/monitoring/sessions — List active monitoring sessions
"""

import os
import sys

# Route modules are written as `import main as _m`, but uvicorn loads us as
# `backend.main`. Without this alias Python loads `main` a second time as a
# top-level module, producing an independent module object whose lifespan
# never runs — so `_m.survey_store` stays None and every write endpoint 503s.
sys.modules.setdefault("main", sys.modules[__name__])

import copy
import json
import uuid
import asyncio
import ipaddress as _ipaddress
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Dict
from urllib.parse import urlparse as _urlparse

try:
    from runtime_paths import (
        describe_runtime_paths,
        get_backend_dir,
        get_checkpoints_dir,
        get_frontend_dist_dir,
    )
except ImportError:  # pragma: no cover - package import path
    from .runtime_paths import (
        describe_runtime_paths,
        get_backend_dir,
        get_checkpoints_dir,
        get_frontend_dist_dir,
    )

BACKEND_DIR = get_backend_dir()
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import numpy as np
import torch
from fastapi import (
    FastAPI,
    UploadFile,
    File,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from shared.backend.models.cnn_model import create_model, BirdSoundCNN
from shared.backend.models.cnn_model_v2 import SEResNet50, SEResNet18
from shared.backend.models.cnn_model_v6 import (
    SEResNet50V6,
    SEResNet18V6,
    compute_dual_channel_mel,
)
from shared.backend.models.cnn_model_v7 import (
    ConvNeXtBirdV7,
    ConvNeXtBirdV7Student,
    compute_dual_channel_mel as compute_dual_channel_mel_v7,
    create_model_v7,
    count_parameters as count_parameters_v7,
)
from shared.backend.engines import birdnet_engine
import report_generator
from audio_processor import (
    load_audio,
    audio_to_mel_spectrogram,
    normalize_spectrogram,
    segment_audio,
    spectrogram_to_base64_image,
    waveform_to_base64_image,
    DEFAULT_SR,
    SEGMENT_DURATION,
    OVERLAP,
)
from shared.backend.analysis.biodiversity import (
    compute_alpha_diversity,
    compute_beta_diversity,
    detection_summary,
)
from xeno_canto_client import (
    CHINA_BIRD_SPECIES,
    search_recordings,
    search_recordings_global,
    get_species_list,
    get_species_count,
    set_api_key,
    get_api_key,
)
import ebird_client
from image_processor import extract_exif, create_thumbnail, classify_image
from camera_trap_processor import (
    preprocess_ir_image,
    create_ir_thumbnail,
    extract_trap_metadata,
    detect_animals_basic,
    group_sequences,
)
from shared.backend.analysis.biodiversity_calculator import (
    compute_comprehensive_indices,
    compute_multi_site_beta,
)
from batch_import import (
    scan_directory,
    group_by_camera,
    group_by_date,
    create_import_manifest,
)
from species_survey_planner import generate_expected_species, generate_survey_protocol
import gbif_client
import inaturalist_client
from species_db import get_species_db
from device_manager import get_device_manager, DeviceStatus
from realtime import get_realtime_processor
from detection_store import get_detection_store, VerificationStatus
from embedding_engine import get_embedding_engine
from survey_store import get_survey_store
from taxonomy_catalog import get_taxonomy_catalog

RELEASE_APP_TITLE = "Biodiversity Field Survey Platform API"
__doc__ = (
    "Biodiversity Field Survey Platform API server.\n\n"
    "Supports offline-first biodiversity survey workflows, shared survey metadata,\n"
    "route and track handling, jurisdiction-aware exports, and secondary\n"
    "acoustic analysis services."
)

# ──────────────────────────────────────────────
# API Key authentication (optional, set via BIRD_API_KEY env var)
# ──────────────────────────────────────────────
BIRD_API_KEY = os.environ.get("BIRD_API_KEY", "")
APP_ENV = os.environ.get("APP_ENV", "").strip().lower()
IS_PRODUCTION = APP_ENV in {"prod", "production"}

MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "100")) * 1024 * 1024
MAX_IMAGE_BYTES = int(os.environ.get("MAX_IMAGE_MB", "20")) * 1024 * 1024
MAX_BATCH_FILES = int(os.environ.get("MAX_BATCH_FILES", "50"))


async def _read_upload(file: UploadFile, max_bytes: int = MAX_UPLOAD_BYTES) -> bytes:
    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(content) / 1024 / 1024:.1f} MB). Maximum allowed: {max_bytes / 1024 / 1024:.0f} MB.",
        )
    return content


# ──────────────────────────────────────────────
# App initialization
# ──────────────────────────────────────────────
# ──────────────────────────────────────────────
# Lifespan dispatcher
#
# We register startup/shutdown callbacks against the lists below and surface
# them through a single FastAPI lifespan context. This replaces the legacy
# `@app.on_event("startup")` decorator (deprecated since FastAPI 0.93) and
# guarantees that required runtime stores (survey_store, detection_store,
# taxonomy_catalog) are confirmed live after startup — any None instance
# becomes a hard RuntimeError instead of silently degrading every POST
# /api/surveys/* call to a 503 "Survey store unavailable".
# ──────────────────────────────────────────────
_LIFESPAN_STARTUP_HANDLERS: list = []
_LIFESPAN_SHUTDOWN_HANDLERS: list = []
_LIFESPAN_REQUIRED_STORES: tuple[str, ...] = (
    "survey_store",
    "det_store",  # backwards-compat name for the detection store global
    "taxonomy_catalog",
)


@asynccontextmanager
async def _app_lifespan(app):  # noqa: ARG001 - FastAPI passes app, unused
    for handler in _LIFESPAN_STARTUP_HANDLERS:
        await handler()
    missing = [
        name for name in _LIFESPAN_REQUIRED_STORES if globals().get(name) is None
    ]
    if missing:
        raise RuntimeError(
            "Required runtime stores failed to initialize during lifespan: "
            f"{missing}. This would cause 503 responses on every dependent "
            "endpoint. Check BIRD_PLATFORM_DATA_DIR / SURVEY_DATA_DIR and "
            "filesystem permissions for the data directory."
        )
    try:
        yield
    finally:
        for handler in _LIFESPAN_SHUTDOWN_HANDLERS:
            try:
                await handler()
            except Exception:  # noqa: BLE001 - shutdown must not raise
                try:
                    logger.exception("Lifespan shutdown handler failed")
                except Exception:  # noqa: BLE001 - logger may not be defined yet
                    pass


_OPENAPI_TAGS = [
    {"name": "Health", "description": "System health and status checks"},
    {
        "name": "Analysis",
        "description": "Audio analysis, batch processing, and report generation",
    },
    {"name": "Species", "description": "China bird species database queries"},
    {
        "name": "Devices",
        "description": "Field monitoring device registration and management",
    },
    {
        "name": "Monitoring",
        "description": "Real-time monitoring sessions and dashboard",
    },
    {
        "name": "Detections",
        "description": "Detection records, verification, and export",
    },
    {"name": "Diversity", "description": "Alpha/Beta/Functional biodiversity metrics"},
    {
        "name": "Embeddings",
        "description": "Acoustic embedding space analysis (t-SNE, clustering)",
    },
    {
        "name": "Xeno-canto",
        "description": "Xeno-canto recording search and API key management",
    },
    {"name": "BirdNET", "description": "BirdNET baseline comparison engine"},
    {"name": "Occupancy", "description": "Occupancy model data preparation"},
]

app = FastAPI(
    title=RELEASE_APP_TITLE,
    description=(
        "Offline-first biodiversity field survey platform for mainland China and Taiwan.\n\n"
        "## Prioritized Workflows\n"
        "- **Field survey operations**: Projects, sites, protocols, routes, events, observations, tracks, and exports\n"
        "- **Multi-module parity**: Terrestrial vertebrates, plants, and insects on one survey backend\n"
        "- **Jurisdiction-aware metadata**: Taxonomy packages and export profiles for mainland China and Taiwan\n"
        "- **Android-first field use**: Resume, recover, sync, and attachment workflows for offline teams\n"
        "- **Acoustic analysis**: Bird audio detection and reporting remain available as secondary modules\n\n"
        "## Error Codes\n"
        "| Range | Category |\n|---|---|\n"
        "| 1xxx | Audio Analysis |\n"
        "| 2xxx | Species Database |\n"
        "| 3xxx | Devices |\n"
        "| 4xxx | Monitoring Sessions |\n"
        "| 5xxx | Detections |\n"
        "| 6xxx | Xeno-canto |\n"
        "| 7xxx | BirdNET |\n"
        "| 8xxx | Auth & Rate Limit |\n"
        "| 9xxx | Internal |\n"
    ),
    version="7.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_tags=_OPENAPI_TAGS,
    lifespan=_app_lifespan,
)
app.title = RELEASE_APP_TITLE

import logging
import time as _time
from collections import defaultdict as _dd, OrderedDict as _OrderedDict

logger = logging.getLogger("field_survey_platform")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class _SecretRedactionFilter(logging.Filter):
    """Scrub credential material (API keys, admin tokens) out of log lines."""

    import re as _re

    _PATTERNS = (
        _re.compile(r"(?i)(x-admin-token['\"]?\s*[:=]\s*)\S+"),
        _re.compile(r"(?i)(x-api-key['\"]?\s*[:=]\s*)\S+"),
        _re.compile(r"(?i)(authorization['\"]?\s*[:=]\s*bearer\s+)\S+"),
        _re.compile(r"(?i)(admin_pin['\"]?\s*[:=]\s*)\S+"),
        _re.compile(r"(?i)(bird_api_key['\"]?\s*[:=]\s*)\S+"),
    )

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
            redacted = message
            for pattern in self._PATTERNS:
                redacted = pattern.sub(r"\1[REDACTED]", redacted)
            if redacted != message:
                record.msg = redacted
                record.args = ()
        except Exception:  # noqa: BLE001 - logging must never raise
            pass
        return True


for _handler in logging.getLogger().handlers:
    _handler.addFilter(_SecretRedactionFilter())

# Optional crash/error monitoring: enabled only when SENTRY_DSN is configured.
_SENTRY_DSN = os.environ.get("SENTRY_DSN", "").strip()
if _SENTRY_DSN:
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            traces_sample_rate=0.0,
            send_default_pii=False,
            environment=os.environ.get("DEPLOY_ENV", "production"),
        )
        logger.info("Sentry error monitoring enabled")
    except ImportError:
        logger.warning(
            "SENTRY_DSN is set but sentry-sdk is not installed; "
            "run `pip install sentry-sdk` to enable crash reporting"
        )

_allowed_origins = [
    o.strip()
    for o in os.environ.get(
        "CORS_ORIGINS", "http://localhost:5173,http://localhost:4173"
    ).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────
# Rate limiting (imported from middleware module)
# ──────────────────────────────────────────────
from middleware import rate_limiter as _rate_limiter
from middleware.rate_limiter import rate_limit_middleware

_RATE_LIMIT = _rate_limiter._RATE_LIMIT
_SURVEY_RATE_LIMIT = _rate_limiter._SURVEY_RATE_LIMIT
_rate_limits = _rate_limiter._rate_limits
_rate_gc_counter = _rate_limiter._rate_gc_counter

app.middleware("http")(rate_limit_middleware)


# ──────────────────────────────────────────────
# Tile proxy helpers
# ──────────────────────────────────────────────
_DEFAULT_TILE_URL_TEMPLATE = os.environ.get(
    "DEFAULT_TILE_URL_TEMPLATE",
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
)
_DEFAULT_TILE_SUBDOMAIN = os.environ.get("DEFAULT_TILE_SUBDOMAIN", "a").strip() or "a"
_TILE_PROXY_PATH_TEMPLATE = "/api/maps/tiles/{z}/{x}/{y}?s={s}"


def _resolve_request_id(request: Request) -> str:
    return (
        getattr(request.state, "request_id", "")
        or request.headers.get("X-Request-ID", "").strip()
        or str(uuid.uuid4())
    )


def _assert_runtime_contract() -> None:
    hard_failures: list[str] = []
    soft_warnings: list[str] = []
    runtime_paths = describe_runtime_paths()
    mutable_runtime_externalized = bool(
        runtime_paths.get("mutable_runtime_externalized")
    )
    if IS_PRODUCTION and not BIRD_API_KEY:
        hard_failures.append("BIRD_API_KEY is required in production.")
    if IS_PRODUCTION and not os.environ.get("CORS_ORIGINS", "").strip():
        hard_failures.append("CORS_ORIGINS is required in production.")
    if not mutable_runtime_externalized:
        soft_warnings.append(
            "Mutable runtime paths are not externalized; deployment is limited to demo mode."
        )
    for warning in soft_warnings:
        logger.warning("Runtime contract warning: %s", warning)
    if hard_failures:
        raise RuntimeError(" ".join(hard_failures))


def _current_model_version() -> str:
    if USE_V7:
        return "v7"
    if USE_V6_DUAL_CHANNEL:
        return "v6"
    return "v1-v3"


def _build_runtime_warnings():
    warnings = []
    model_species = len(species_mapping) if species_mapping else 0
    db_species = species_db.count if species_db else 0
    missing_species = max(0, db_species - model_species)

    if model is None:
        warnings.append(
            {
                "code": "MODEL_NOT_LOADED",
                "level": "error",
                "title": "Inference model unavailable",
                "detail": "The API is running, but no trained model is loaded for analysis.",
            }
        )

    if model_species and db_species and model_species < db_species:
        warnings.append(
            {
                "code": "SPECIES_COVERAGE_GAP",
                "level": "warning",
                "title": "Species coverage gap",
                "detail": (
                    f"The runtime model currently serves {model_species} species while the "
                    f"database lists {db_species}. {missing_species} species are not yet covered "
                    "by the active checkpoint."
                ),
            }
        )

    if not birdnet_engine.is_available():
        warnings.append(
            {
                "code": "BIRDNET_BASELINE_UNAVAILABLE",
                "level": "info",
                "title": "BirdNET baseline unavailable",
                "detail": "Baseline comparison is optional and is not installed in the current runtime.",
            }
        )

    return warnings


def _runtime_state_from_warnings(warnings):
    if any(item.get("level") == "error" for item in warnings):
        return "error"
    if any(item.get("level") == "warning" for item in warnings):
        return "warning"
    return "ready"


def _build_readiness_summary(
    runtime_state: str, runtime_paths: dict[str, Any]
) -> dict[str, Any]:
    checks = {
        "model_loaded": model is not None,
        "runtime_state_ready": runtime_state == "ready",
        "mutable_runtime_externalized": bool(
            runtime_paths.get("mutable_runtime_externalized")
        ),
    }
    blocking_codes = []
    if not checks["model_loaded"]:
        blocking_codes.append("MODEL_NOT_LOADED")
    if runtime_state == "error":
        blocking_codes.append("RUNTIME_ERRORS_PRESENT")
    elif runtime_state == "warning":
        blocking_codes.append("RUNTIME_WARNINGS_PRESENT")
    if not checks["mutable_runtime_externalized"]:
        blocking_codes.append("MUTABLE_RUNTIME_NOT_EXTERNALIZED")

    strict_ready = not blocking_codes
    if strict_ready:
        mode = "production"
    elif not checks["model_loaded"]:
        mode = "fallback"
    elif runtime_state != "ready":
        mode = "degraded"
    else:
        mode = "demo"

    return {
        "legacy_ready": checks["model_loaded"],
        "strict_ready": strict_ready,
        "mode": mode,
        "checks": checks,
        "blocking_codes": blocking_codes,
    }


def _taxonomy_release_health_summary(
    prioritized_taxonomy_packages: list[dict[str, Any]],
) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    release_summary: dict[str, Any] = {}
    if taxonomy_catalog and getattr(taxonomy_catalog, "stats", None):
        stats = taxonomy_catalog.stats() or {}
    if taxonomy_catalog and getattr(taxonomy_catalog, "current_release_summary", None):
        release_summary = taxonomy_catalog.current_release_summary() or {}

    exhaustive_fallback = sum(
        1
        for item in prioritized_taxonomy_packages
        if bool(item.get("exhaustive") or item.get("exhaustive_species_content"))
    )
    package_parity_values = [
        bool(item.get("count_parity_ok"))
        for item in prioritized_taxonomy_packages
        if "count_parity_ok" in item
    ]
    current_release_id = str(
        release_summary.get("taxonomy_release_id")
        or release_summary.get("release_id")
        or stats.get("current_taxonomy_release_id")
        or ""
    )
    return {
        "current_taxonomy_release_id": current_release_id,
        "taxonomy_exhaustive_package_count": int(
            release_summary.get("taxonomy_exhaustive_package_count")
            or stats.get("taxonomy_exhaustive_package_count")
            or exhaustive_fallback
        ),
        "taxonomy_count_parity_ok": bool(
            release_summary.get("taxonomy_count_parity_ok")
            if "taxonomy_count_parity_ok" in release_summary
            else (
                stats.get("taxonomy_count_parity_ok")
                if "taxonomy_count_parity_ok" in stats
                else (all(package_parity_values) if package_parity_values else False)
            )
        ),
        "taxonomy_review_backlog_count": int(
            release_summary.get("taxonomy_review_backlog_count")
            or stats.get("taxonomy_review_backlog_count")
            or 0
        ),
        "taxonomy_release": release_summary,
    }


def _require_taxonomy_catalog():
    if not taxonomy_catalog:
        raise HTTPException(status_code=503, detail="Taxonomy catalog unavailable")
    return taxonomy_catalog


def _resolve_taxonomy_search_package_ids(
    *,
    program: str,
    protocol: str,
    jurisdiction: str,
) -> list[str]:
    if not survey_store:
        return []
    packages = survey_store.list_taxonomy_packages(
        jurisdiction=jurisdiction,
        program=program,
        protocol=protocol,
    )
    resolved: list[str] = []
    for package in packages:
        if not isinstance(package, dict):
            continue
        package_id = str(
            package.get("asset_package_id") or package.get("package_id") or ""
        ).strip()
        if package_id and package_id not in resolved:
            resolved.append(package_id)
    return resolved


# ──────────────────────────────────────────────
# HTTP middleware
# ──────────────────────────────────────────────
@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request.state.request_id = _resolve_request_id(request)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


_AUTH_EXEMPT_PATHS = {
    "/api/health",
    "/api/config",
    "/api/docs",
    "/api/redoc",
    "/openapi.json",
}
# B10: `/api/health/` prefix keeps readiness/liveness probes reachable from
# load balancers and container healthchecks that cannot attach an API key.
_AUTH_EXEMPT_PREFIXES = (
    "/api/map-tiles/",
    "/api/maps/tiles/",
    "/api/health/",
)


def _check_api_key(request) -> bool:
    """Validate API key from headers only (not query params to avoid log leakage)."""
    if not BIRD_API_KEY:
        return True
    provided = (
        request.headers.get("X-API-Key", "")
        or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    )
    if not provided:
        return False
    import hmac

    return hmac.compare_digest(provided.encode(), BIRD_API_KEY.encode())


@app.middleware("http")
async def api_key_middleware(request, call_next):
    if not BIRD_API_KEY:
        return await call_next(request)
    path = request.url.path
    if path in _AUTH_EXEMPT_PATHS or any(
        path.startswith(prefix) for prefix in _AUTH_EXEMPT_PREFIXES
    ):
        return await call_next(request)
    if not path.startswith("/api") and not path.startswith("/ws"):
        return await call_next(request)
    if not _check_api_key(request):
        return JSONResponse(
            status_code=401, content={"detail": "Invalid or missing API key"}
        )
    return await call_next(request)


# ──────────────────────────────────────────────
# Survey audit logging (B20) — records mutating /api/surveys + /api/devices
# operations into survey_audit_log (device_id, user_id, op, entity, ip, ...).
# ──────────────────────────────────────────────
from middleware.audit_log import audit_log_middleware

app.middleware("http")(audit_log_middleware)


# ──────────────────────────────────────────────
# Platform config helpers (used by routes/config.py and routes/maps.py)
# ──────────────────────────────────────────────
def _resolve_platform_tile_source_url() -> str:
    from platform_config import get_map_config

    map_config = get_map_config() or {}
    configured_url = str(map_config.get("tile_url") or "").strip()
    return configured_url or _DEFAULT_TILE_URL_TEMPLATE


def _is_remote_tile_source_url(tile_url: str) -> bool:
    return tile_url.startswith("http://") or tile_url.startswith("https://")


def _resolve_tile_proxy_url_template() -> str:
    return _TILE_PROXY_PATH_TEMPLATE


def _serialize_platform_config_for_frontend() -> dict[str, Any]:
    from platform_config import get_config

    config = copy.deepcopy(get_config())
    map_config = dict(config.get("map") or {})
    tile_source_url = _resolve_platform_tile_source_url()
    tile_proxy_url = _resolve_tile_proxy_url_template()
    map_config["tile_source_url"] = tile_source_url
    map_config["tile_proxy_url"] = tile_proxy_url
    map_config["tile_proxy_path"] = tile_proxy_url
    if _is_remote_tile_source_url(tile_source_url):
        map_config["tile_url"] = tile_source_url
    else:
        map_config["tile_url"] = tile_source_url
    config["map"] = map_config
    return config


def _build_upstream_tile_url(z: int, x: int, y: int, subdomain: Optional[str]) -> str:
    tile_url = _resolve_platform_tile_source_url()
    resolved_subdomain = (
        subdomain or _DEFAULT_TILE_SUBDOMAIN
    ).strip() or _DEFAULT_TILE_SUBDOMAIN
    return (
        tile_url.replace("{s}", resolved_subdomain)
        .replace("{z}", str(z))
        .replace("{x}", str(x))
        .replace("{y}", str(y))
        .replace("{r}", "")
    )


# ──────────────────────────────────────────────
# Model loading and global state
# ──────────────────────────────────────────────
MODEL_DIR = get_checkpoints_dir()
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = None
teacher_model = None
species_mapping = None
idx_to_species = None
CALIBRATION_T = 1.0
USE_ENSEMBLE = False
USE_V6_DUAL_CHANNEL = False
species_to_chinese = {sp["scientific"]: sp["chinese"] for sp in CHINA_BIRD_SPECIES}
species_to_english = {sp["scientific"]: sp["english"] for sp in CHINA_BIRD_SPECIES}

MAX_DETECTION_SESSIONS = int(os.environ.get("MAX_DETECTION_SESSIONS", "100"))


class _LRUSessionHistory(dict):
    """In-memory detection history with LRU eviction to prevent unbounded memory growth."""

    def __setitem__(self, key, value):
        if key not in self and len(self) >= MAX_DETECTION_SESSIONS:
            oldest = next(iter(self))
            dict.__delitem__(self, oldest)
        dict.__setitem__(self, key, value)


detection_history = _LRUSessionHistory()

species_db = None
device_mgr = None
rt_processor = None
det_store = None
emb_engine = None
survey_store = None
taxonomy_catalog = None

USE_V7 = False


def _infer_checkpoint_num_species(checkpoint: dict) -> Optional[int]:
    """Infer classifier output size from a saved checkpoint."""
    state_dict = checkpoint.get("model_state_dict", {})
    candidate_keys = (
        "fc.weight",
        "classifier.weight",
        "head.weight",
        "species_head.weight",
        "cls_head.weight",
    )
    for key in candidate_keys:
        tensor = state_dict.get(key)
        if tensor is not None and getattr(tensor, "ndim", 0) >= 1:
            return int(tensor.shape[0])
    return None


def _align_species_mapping_to_checkpoint(expected_num_species: Optional[int]):
    """Reconcile the runtime species mapping with the loaded checkpoint head.

    Default behaviour (legacy): warn + trim the mapping down so the demo keeps
    running. This is the silent failure mode that ticket Algo-D / P0-W1 set out
    to kill once the v7-head-223 retrain is deployed.

    Strict behaviour (post-fix): set env ``ALGO_D_STRICT_HEAD_MATCH=1`` (or
    drop a file named ``.strict_head_match`` next to the checkpoint) and any
    mismatch becomes a hard RuntimeError, so deployment fails fast instead of
    silently shipping a model that cannot identify the trimmed species.

    Whichever branch we take, log the dropped species names (not just a count)
    so the warning is actionable.
    """
    global species_mapping, idx_to_species
    if not expected_num_species or not species_mapping or not idx_to_species:
        return

    current_num_species = len(species_mapping)
    if expected_num_species == current_num_species:
        return

    dropped = sorted(
        scientific
        for scientific, idx in species_mapping.items()
        if idx >= expected_num_species
    )
    dropped_preview = ", ".join(dropped[:6]) + (" ..." if len(dropped) > 6 else "")
    strict_env = os.environ.get("ALGO_D_STRICT_HEAD_MATCH", "").strip().lower() in {"1", "true", "yes", "on"}
    strict_flag_file = MODEL_DIR / ".strict_head_match"
    strict = strict_env or strict_flag_file.exists()

    msg = (
        f"Species mapping ({current_num_species}) does not match checkpoint head "
        f"({expected_num_species}); {len(dropped)} species would be silently dropped "
        f"from inference: [{dropped_preview}]."
    )
    if strict:
        logger.error("STRICT mode: %s Refusing to start. "
                     "Re-run training (see docs/algo_d/2026-06-10_head_217_to_223_decision.md) "
                     "or align species_mapping.json with the checkpoint.", msg)
        raise RuntimeError(msg)

    logger.warning(
        "%s Trimming runtime mapping to checkpoint classes (legacy mode). "
        "Set ALGO_D_STRICT_HEAD_MATCH=1 to fail fast instead.",
        msg,
    )
    species_mapping = {
        scientific: idx
        for scientific, idx in species_mapping.items()
        if idx < expected_num_species
    }
    idx_to_species = {
        idx: scientific
        for idx, scientific in idx_to_species.items()
        if idx < expected_num_species
    }


def load_model():
    """Load trained model — auto-detects v1/v2/v3/v6/v7 architecture + ensemble."""
    global model, teacher_model, species_mapping, idx_to_species, CALIBRATION_T, USE_ENSEMBLE, USE_V6_DUAL_CHANNEL, USE_V7

    model_path = MODEL_DIR / "best_model.pth"
    mapping_path = MODEL_DIR / "species_mapping.json"

    if model_path.exists() and mapping_path.exists():
        with open(mapping_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        species_mapping = data["species_to_idx"]
        idx_to_species = {int(k): v for k, v in data["idx_to_species"].items()}

        checkpoint = torch.load(model_path, map_location=DEVICE, weights_only=True)
        checkpoint_num_species = _infer_checkpoint_num_species(checkpoint)
        _align_species_mapping_to_checkpoint(checkpoint_num_species)
        num_species = len(species_mapping)
        version = checkpoint.get("version", "v1")
        model_type = checkpoint.get("model_type", "")

        if "v7" in str(version):
            USE_V7 = True
            USE_V6_DUAL_CHANNEL = True
            if model_type == "teacher":
                model = ConvNeXtBirdV7(num_species=num_species, in_channels=2).to(
                    DEVICE
                )
            else:
                model = ConvNeXtBirdV7Student(
                    num_species=num_species, in_channels=2
                ).to(DEVICE)
            logger.info(
                "Loading v7 %s model (ConvNeXt V7, MAP + Proto + OOD)", model_type
            )
        elif "v6" in str(version):
            USE_V6_DUAL_CHANNEL = True
            if model_type == "teacher":
                model = SEResNet50V6(num_species=num_species, in_channels=2).to(DEVICE)
            else:
                model = SEResNet18V6(num_species=num_species, in_channels=2).to(DEVICE)
            logger.info(
                "Loading v6 %s model (SE-ResNet V6, dual-channel + GeM)", model_type
            )
        elif "v3" in str(version) or model_type in ("student", "teacher"):
            if model_type == "teacher":
                model = SEResNet50(num_species=num_species).to(DEVICE)
            else:
                model = SEResNet18(num_species=num_species).to(DEVICE)
            logger.info("Loading v3 %s model (SE-ResNet)", model_type)
        else:
            lite = checkpoint.get("lite", False)
            model = create_model(num_species=num_species, lite=lite).to(DEVICE)

        model.load_state_dict(checkpoint["model_state_dict"])
        model.eval()
        logger.info(
            "Loaded model: %s, %d species, val_acc=%s",
            version,
            num_species,
            checkpoint.get("val_acc", "N/A"),
        )
        if USE_V7:
            ood_cal = (
                "calibrated" if checkpoint.get("ood_calibrated") else "uncalibrated"
            )
            logger.info("  OOD detector: %s", ood_cal)

        if USE_V7:
            teacher_path = MODEL_DIR / "best_teacher_v7.pth"
        elif USE_V6_DUAL_CHANNEL:
            teacher_path = MODEL_DIR / "best_teacher_v6.pth"
        else:
            teacher_path = MODEL_DIR / "best_teacher.pth"
        if teacher_path.exists() and model_type == "student":
            t_ckpt = torch.load(teacher_path, map_location=DEVICE, weights_only=True)
            if USE_V7:
                teacher_model = ConvNeXtBirdV7(
                    num_species=num_species, in_channels=2
                ).to(DEVICE)
            elif USE_V6_DUAL_CHANNEL:
                teacher_model = SEResNet50V6(num_species=num_species, in_channels=2).to(
                    DEVICE
                )
            else:
                teacher_model = SEResNet50(num_species=num_species).to(DEVICE)
            teacher_model.load_state_dict(t_ckpt["model_state_dict"])
            teacher_model.eval()
            USE_ENSEMBLE = True
            logger.info(
                "Ensemble mode: teacher loaded (val_acc=%s)",
                t_ckpt.get("val_acc", "N/A"),
            )

        calib_path = MODEL_DIR / "calibration.json"
        if calib_path.exists():
            with open(calib_path) as cf:
                calib = json.load(cf)
            CALIBRATION_T = calib.get("temperature", 1.0)
            logger.info(
                "Temperature calibration: T=%.4f (ECE: %s)",
                CALIBRATION_T,
                calib.get("ece_after", "?"),
            )
    else:
        num_species = len(CHINA_BIRD_SPECIES)
        species_mapping = {
            sp["scientific"]: i for i, sp in enumerate(CHINA_BIRD_SPECIES)
        }
        idx_to_species = {
            i: sp["scientific"] for i, sp in enumerate(CHINA_BIRD_SPECIES)
        }
        model = create_model(num_species=num_species, lite=False).to(DEVICE)
        model.eval()
        logger.warning(
            "Demo mode: model initialized with %d species (untrained)", num_species
        )


def _init_species_db():
    """Initialize species database and merge name mappings."""
    global species_db, species_to_chinese, species_to_english
    species_db = get_species_db()
    for sp in species_db.all_species:
        if sp["scientific"] not in species_to_chinese:
            species_to_chinese[sp["scientific"]] = sp["chinese"]
        if sp["scientific"] not in species_to_english:
            species_to_english[sp["scientific"]] = sp.get("english", "")
    logger.info("Species database loaded: %d species", species_db.count)


def _init_realtime():
    """Initialize real-time processor with inference pipeline."""
    global rt_processor, device_mgr
    rt_processor = get_realtime_processor()
    rt_processor.set_inference_pipeline(
        predict_fn=predict_species,
        mel_fn=audio_to_mel_spectrogram,
        norm_fn=normalize_spectrogram,
        use_dual_channel=USE_V6_DUAL_CHANNEL or USE_V7,
        dual_mel_fn=(
            compute_dual_channel_mel if (USE_V6_DUAL_CHANNEL or USE_V7) else None
        ),
    )
    device_mgr = get_device_manager()
    logger.info(
        "Real-time processor initialized (dual_channel=%s)",
        USE_V6_DUAL_CHANNEL or USE_V7,
    )


def _init_detection_store():
    """Initialize persistent detection store."""
    global det_store
    det_store = get_detection_store()
    logger.info(
        "Detection store loaded: %d records", det_store.get_stats()["total_detections"]
    )


def _init_embedding_engine():
    """Initialize feature embedding engine with loaded model."""
    global emb_engine
    emb_engine = get_embedding_engine()
    if model is not None:
        emb_engine.set_model(model, DEVICE)
    logger.info("Embedding engine initialized")


def _init_survey_store():
    """Initialize field survey storage."""
    global survey_store
    survey_store = get_survey_store()
    logger.info("Survey store initialized")


def _init_taxonomy_catalog():
    """Initialize normalized survey taxonomy storage."""
    global taxonomy_catalog
    taxonomy_catalog = get_taxonomy_catalog()
    logger.info("Taxonomy catalog initialized: %s", taxonomy_catalog.stats())


_SURVEY_FILE = BACKEND_DIR / "data" / "survey_sites.json"
_survey_sites: list = []


def _init_surveys():
    global _survey_sites
    try:
        if _SURVEY_FILE.exists():
            _survey_sites = json.loads(_SURVEY_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to load survey sites from %s: %s", _SURVEY_FILE, exc)
        _survey_sites = []


def _save_surveys():
    _SURVEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SURVEY_FILE.write_text(
        json.dumps(_survey_sites, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ──────────────────────────────────────────────
# Image and camera trap stores
# ──────────────────────────────────────────────
_IMAGE_STORE_DIR = BACKEND_DIR / "data" / "images"
_IMAGE_RECORDS_FILE = BACKEND_DIR / "data" / "image_records.json"
_image_records: list = []


def _init_image_store():
    global _image_records
    _IMAGE_STORE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        if _IMAGE_RECORDS_FILE.exists():
            _image_records = json.loads(_IMAGE_RECORDS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(
            "Failed to load image records from %s: %s", _IMAGE_RECORDS_FILE, exc
        )
        _image_records = []


def _save_image_records():
    _IMAGE_RECORDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _IMAGE_RECORDS_FILE.write_text(
        json.dumps(_image_records, ensure_ascii=False, indent=2), encoding="utf-8"
    )


_init_image_store()

_TRAP_RECORDS_FILE = BACKEND_DIR / "data" / "trap_records.json"
_trap_records: list = []


def _init_trap_store():
    global _trap_records
    try:
        if _TRAP_RECORDS_FILE.exists():
            _trap_records = json.loads(_TRAP_RECORDS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to load trap records from %s: %s", _TRAP_RECORDS_FILE, exc)
        _trap_records = []


def _save_trap_records():
    _TRAP_RECORDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TRAP_RECORDS_FILE.write_text(
        json.dumps(_trap_records, ensure_ascii=False, indent=2), encoding="utf-8"
    )


_init_trap_store()


# ──────────────────────────────────────────────
# Batch scan path validation
# ──────────────────────────────────────────────
_BATCH_SCAN_ROOTS = [
    p.strip()
    for p in os.environ.get("BATCH_SCAN_ROOTS", "/app/data,/mnt").split(",")
    if p.strip()
]


def _validate_scan_path(directory: str) -> Path:
    resolved = Path(directory).resolve()
    if not _BATCH_SCAN_ROOTS:
        raise HTTPException(
            status_code=403,
            detail="No scan roots configured. Set BATCH_SCAN_ROOTS environment variable.",
        )
    for root in _BATCH_SCAN_ROOTS:
        try:
            resolved.relative_to(Path(root).resolve())
            return resolved
        except ValueError:
            continue
    raise HTTPException(
        status_code=403,
        detail=f"Directory not within allowed scan roots: {', '.join(_BATCH_SCAN_ROOTS)}",
    )


# ──────────────────────────────────────────────
# Utility helpers used by route modules
# ──────────────────────────────────────────────
def _content_disposition(filename: str) -> str:
    from urllib.parse import quote
    try:
        filename.encode("latin-1")
        return f"attachment; filename={filename}"
    except UnicodeEncodeError:
        ascii_name = filename.encode("ascii", errors="replace").decode("ascii")
        encoded = quote(filename, safe="")
        return f"attachment; filename={ascii_name}; filename*=UTF-8''{encoded}"


def _model_to_dict(model_obj: BaseModel) -> dict:
    if hasattr(model_obj, "model_dump"):
        return model_obj.model_dump(exclude_unset=True)
    return model_obj.dict(exclude_unset=True)


# ──────────────────────────────────────────────
# Inference helper
# ──────────────────────────────────────────────
def predict_species(
    mel_spectrogram: np.ndarray,
    top_k: int = 5,
    use_tta: bool = False,
    mc_dropout_passes: int = 0,
):
    """Run CNN inference with ensemble, calibration, and uncertainty estimation."""
    if USE_V6_DUAL_CHANNEL:
        tensor = torch.FloatTensor(mel_spectrogram).unsqueeze(0).to(DEVICE)
    else:
        tensor = torch.FloatTensor(mel_spectrogram).unsqueeze(0).unsqueeze(0).to(DEVICE)

    ood_info = None
    with torch.no_grad():
        if USE_V7:
            logits, ood_info = model(tensor, return_ood=True)
        else:
            logits = model(tensor)

        if use_tta:
            tensor_flip = torch.flip(tensor, dims=[-1])
            if USE_V7:
                logits_flip, _ = model(tensor_flip, return_ood=True)
            else:
                logits_flip = model(tensor_flip)
            logits = (logits + logits_flip) / 2.0

        if USE_ENSEMBLE and teacher_model is not None:
            if USE_V7:
                t_logits, _ = teacher_model(tensor, return_ood=True)
            else:
                t_logits = teacher_model(tensor)
            if use_tta:
                if USE_V7:
                    t_flip, _ = teacher_model(
                        torch.flip(tensor, dims=[-1]), return_ood=True
                    )
                else:
                    t_flip = teacher_model(torch.flip(tensor, dims=[-1]))
                t_logits = (t_logits + t_flip) / 2.0
            logits = (logits + t_logits) / 2.0

    uncertainty = 0.0
    if mc_dropout_passes > 0:
        model.train()
        mc_probs = []
        with torch.no_grad():
            for _ in range(mc_dropout_passes):
                mc_logits = (
                    model(tensor) if not USE_V7 else model(tensor, return_ood=False)
                )
                mc_p = torch.softmax(mc_logits / CALIBRATION_T, dim=1)
                mc_probs.append(mc_p.cpu().numpy())
        model.eval()
        mc_stack = np.stack(mc_probs, axis=0)
        uncertainty = float(mc_stack.std(axis=0).mean())

    calibrated_logits = logits / CALIBRATION_T
    probs = torch.softmax(calibrated_logits, dim=1)[0]
    top_probs, top_indices = probs.topk(top_k)

    entropy = float(-(probs * torch.log(probs + 1e-10)).sum().cpu())
    max_entropy = np.log(len(probs))
    normalized_entropy = entropy / max_entropy

    is_ood = False
    ood_score = None
    if ood_info is not None:
        is_ood = bool(ood_info["is_ood"][0].item())
        ood_score = float(ood_info["ood_score"][0].item())

    results = []
    for prob, idx in zip(top_probs.cpu().numpy(), top_indices.cpu().numpy()):
        scientific = idx_to_species.get(int(idx), "Unknown")
        conf = float(round(prob, 4))
        reliable = conf > 0.3 and normalized_entropy < 0.7
        if is_ood:
            reliable = False
        results.append(
            {
                "species_scientific": scientific,
                "species_chinese": species_to_chinese.get(scientific, ""),
                "species_english": species_to_english.get(scientific, ""),
                "confidence": conf,
                "reliable": reliable,
            }
        )

    if results:
        meta = {
            "entropy": round(entropy, 4),
            "normalized_entropy": round(normalized_entropy, 4),
            "mc_uncertainty": round(uncertainty, 6) if mc_dropout_passes > 0 else None,
            "temperature": round(CALIBRATION_T, 4),
            "ensemble": USE_ENSEMBLE,
        }
        if USE_V7:
            meta["ood_detected"] = is_ood
            meta["ood_score"] = round(ood_score, 4) if ood_score is not None else None
            meta["model_version"] = "v7"
        results[0]["_meta"] = meta
    return results


def safe_predict_species(
    mel_spectrogram: np.ndarray,
    *,
    audio_path: Optional[str] = None,
    top_k: int = 5,
    use_tta: bool = False,
    mc_dropout_passes: int = 0,
):
    """Algo-D / P2-W3 :: fail-tolerant wrapper around :func:`predict_species`.

    Drop-in replacement. Catches CNN-side failures (OOM, missing model,
    runtime errors) and falls back to ``inference_fallback`` (BirdNET
    embedding + KNN, then BirdNET classifier). Returns the same list[dict]
    shape as :func:`predict_species`.

    Owned by Algo-D; see docs/algo_d/2026-06-10_inference_fallback_design.md.
    """
    from inference_fallback import (
        safe_predict_species as _safe,
        predict_species_fallback as _fallback,
    )

    if model is None:
        if audio_path is None:
            logger.warning(
                "safe_predict_species called with no model and no audio_path; "
                "returning empty fallback result."
            )
            return []
        return _fallback(
            audio_path,
            top_k=top_k,
            reason="no_model",
            chinese_lookup=lambda sci: species_to_chinese.get(sci, ""),
            english_lookup=lambda sci: species_to_english.get(sci, ""),
        )

    if audio_path is None:
        return predict_species(
            mel_spectrogram,
            top_k=top_k,
            use_tta=use_tta,
            mc_dropout_passes=mc_dropout_passes,
        )

    return _safe(
        primary=predict_species,
        primary_kwargs={
            "mel_spectrogram": mel_spectrogram,
            "top_k": top_k,
            "use_tta": use_tta,
            "mc_dropout_passes": mc_dropout_passes,
        },
        audio_path=audio_path,
        top_k=top_k,
        chinese_lookup=lambda sci: species_to_chinese.get(sci, ""),
        english_lookup=lambda sci: species_to_english.get(sci, ""),
    )


def safe_predict_species_with_explicit_routing(
    mel_spectrogram: np.ndarray,
    *,
    audio_path: Optional[str] = None,
    top_k: int = 5,
    use_tta: bool = False,
    mc_dropout_passes: int = 0,
):
    """Algo-D / P0-W1 PIVOT (GPU-off) :: CNN + proactive BirdNET routing.

    Used when the current CNN head is smaller than the historical mapping
    (because GPU is unavailable so we trimmed mapping to head=217 instead
    of retraining to head=223). For species that were trimmed off the
    mapping (listed in
    ``backend/checkpoints/explicit_fallback_species.json``), runs
    ``inference_fallback.proactive_predict_for_explicit_species`` on the
    same audio file and merges those predictions with the CNN ones,
    re-sorted by confidence and capped to ``top_k``.

    ``audio_path`` is required for explicit routing. If absent or no sidecar
    exists, this degrades to plain ``safe_predict_species`` semantics.
    """
    cnn_results = safe_predict_species(
        mel_spectrogram,
        audio_path=audio_path,
        top_k=top_k,
        use_tta=use_tta,
        mc_dropout_passes=mc_dropout_passes,
    )

    if not audio_path:
        return cnn_results

    from inference_fallback import (
        proactive_predict_for_explicit_species,
        explicit_fallback_species,
    )

    if not explicit_fallback_species():
        return cnn_results

    explicit_results = proactive_predict_for_explicit_species(
        audio_path,
        top_k=top_k,
        chinese_lookup=lambda sci: species_to_chinese.get(sci, ""),
        english_lookup=lambda sci: species_to_english.get(sci, ""),
    )
    if not explicit_results:
        return cnn_results

    seen: dict[str, dict] = {}
    for row in (cnn_results + explicit_results):
        sci = row.get("species_scientific", "")
        if not sci:
            continue
        prior = seen.get(sci)
        if prior is None or float(row.get("confidence", 0.0)) > float(prior.get("confidence", 0.0)):
            seen[sci] = row
    merged = sorted(seen.values(),
                    key=lambda r: -float(r.get("confidence", 0.0)))[:top_k]
    if merged:
        meta = dict(merged[0].get("_meta", {})) if isinstance(merged[0].get("_meta"), dict) else {}
        meta["explicit_routing_used"] = True
        meta["explicit_routing_count"] = len(explicit_results)
        merged[0]["_meta"] = meta
    return merged


# ──────────────────────────────────────────────
# Startup / Shutdown
# ──────────────────────────────────────────────
def _warn_insecure_cors_origins() -> None:
    """B13 regression guard: production CORS origins must be https."""
    for origin in _allowed_origins:
        lowered = origin.lower()
        if not lowered.startswith("http://"):
            continue
        host = _urlparse(origin).hostname or ""
        if host not in {"localhost", "127.0.0.1", "::1"}:
            logger.warning(
                "CORS origin %s uses plain http:// — Capacitor/WebView clients "
                "will block these calls as mixed content (B13). Use https://.",
                origin,
            )


# B21: periodic hard-delete of soft-deleted rows past the retention window.
TRASH_GC_ENABLED = os.environ.get("SURVEY_TRASH_GC_ENABLED", "1").strip() != "0"
TRASH_RETENTION_DAYS = int(os.environ.get("SURVEY_TRASH_RETENTION_DAYS", "30") or 30)
TRASH_GC_INTERVAL_HOURS = float(
    os.environ.get("SURVEY_TRASH_GC_INTERVAL_HOURS", "24") or 24
)
_trash_gc_task: Optional[asyncio.Task] = None


async def _trash_gc_loop() -> None:
    # Small initial delay so boot-time model loading is not competing with GC.
    await asyncio.sleep(60)
    while True:
        try:
            if survey_store is not None:
                summary = await asyncio.to_thread(
                    survey_store.purge_expired_trash, TRASH_RETENTION_DAYS
                )
                if summary.get("purged_total"):
                    logger.info(
                        "Trash GC purged %s rows (cutoff=%s, archives=%s)",
                        summary["purged_total"],
                        summary["cutoff"],
                        summary["archived_files"],
                    )
        except Exception:  # noqa: BLE001 - GC must keep running
            logger.exception("Trash GC iteration failed")
        await asyncio.sleep(max(0.25, TRASH_GC_INTERVAL_HOURS) * 3600)


async def _lifespan_startup():
    """Lifespan startup: load model, initialize all stores, schedule GC."""
    from platform_config import load_config, validate_config

    logger.info("Starting biodiversity field survey platform...")
    load_config()
    config_validation = validate_config(load_config())
    logger.info(
        "Platform config validated [valid=%s strict=%s missing=%s]",
        config_validation["valid"],
        config_validation["strict_mode"],
        config_validation["missing_required_fields"],
    )
    _assert_runtime_contract()
    _warn_insecure_cors_origins()
    await asyncio.to_thread(load_model)
    _init_species_db()
    _init_detection_store()
    _init_survey_store()
    _init_taxonomy_catalog()
    _init_embedding_engine()
    _init_realtime()
    _init_surveys()
    global _trash_gc_task
    if TRASH_GC_ENABLED and _trash_gc_task is None:
        _trash_gc_task = asyncio.create_task(_trash_gc_loop())
        logger.info(
            "Trash GC scheduled (retention=%sd, interval=%sh)",
            TRASH_RETENTION_DAYS,
            TRASH_GC_INTERVAL_HOURS,
        )
    logger.info("Platform ready (device=%s)", DEVICE)


async def _lifespan_shutdown():
    global _trash_gc_task
    if _trash_gc_task is not None:
        _trash_gc_task.cancel()
        _trash_gc_task = None


_LIFESPAN_STARTUP_HANDLERS.append(_lifespan_startup)
_LIFESPAN_SHUTDOWN_HANDLERS.append(_lifespan_shutdown)


# ──────────────────────────────────────────────
# Advanced analysis module singletons
# ──────────────────────────────────────────────
from shared.backend.export.darwin_core_exporter import DarwinCoreExporter
from soundscape_analyzer import SoundscapeAnalyzer
from phenology_engine import PhenologyEngine
from occupancy_engine import OccupancyEngine
from fewshot_detector import FewShotDetector
from alert_pusher import AlertPusher

dwc_exporter = DarwinCoreExporter(det_store)
soundscape_analyzer = SoundscapeAnalyzer()
phenology_engine = PhenologyEngine(det_store)
occupancy_engine = OccupancyEngine(det_store)
fewshot = FewShotDetector(embedding_engine=emb_engine)
alert_pusher = AlertPusher()


# ──────────────────────────────────────────────
# Register all routers
# ──────────────────────────────────────────────
from routes import all_routers

for _router in all_routers:
    app.include_router(_router)
from routes.health import health_check


# ──────────────────────────────────────────────
# API versioning: /api/v1/* mirrors /api/* for forward-compat
# ──────────────────────────────────────────────
@app.middleware("http")
async def api_v1_rewrite(request, call_next):
    path = request.scope.get("path", "")
    if path.startswith("/api/v1/"):
        request.scope["path"] = "/api/" + path[len("/api/v1/"):]
    return await call_next(request)


# ──────────────────────────────────────────────
# Exception handlers
# ──────────────────────────────────────────────
@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    request_id = _resolve_request_id(request)
    logger.exception(
        "Unhandled server error [request_id=%s] %s %s",
        request_id,
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "request_id": request_id,
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = _resolve_request_id(request)
    if exc.status_code >= 500:
        logger.error(
            "HTTP exception [request_id=%s] %s %s status=%s detail=%s",
            request_id,
            request.method,
            request.url.path,
            exc.status_code,
            exc.detail,
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "request_id": request_id},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = _resolve_request_id(request)
    logger.info(
        "Request validation failed [request_id=%s] %s %s",
        request_id,
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "request_id": request_id},
    )


# ──────────────────────────────────────────────
# Serve frontend static files (for desktop / single-binary deployment)
# ──────────────────────────────────────────────
_frontend_dist = get_frontend_dist_dir()

if _frontend_dist.exists():
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    @app.get("/")
    async def serve_index():
        return FileResponse(_frontend_dist / "index.html")

    app.mount(
        "/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend"
    )
    logger.info("Serving frontend from %s", _frontend_dist)


# ──────────────────────────────────────────────
# Run server
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("UVICORN_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = int(os.environ.get("UVICORN_PORT", "8000"))
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=os.environ.get("UVICORN_RELOAD", "").strip().lower()
        in {"1", "true", "yes", "on"},
    )
