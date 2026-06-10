"""Platform configuration loader — reads and validates platform_config.json."""

import json
import logging
import os
from pathlib import Path

_CONFIG_DIR = Path(
    os.environ.get("BIRD_PLATFORM_DATA_DIR", Path(__file__).parent / "data")
)
_CONFIG_FILE = _CONFIG_DIR / "platform_config.json"
_APP_ENV = os.environ.get("APP_ENV", "").strip().lower()
_STRICT_CONFIG_VALIDATION = os.environ.get(
    "STRICT_CONFIG_VALIDATION",
    "1" if _APP_ENV in {"prod", "production"} else "0",
).strip().lower() in {"1", "true", "yes", "on"}
_REQUIRED_PATHS: tuple[tuple[str, ...], ...] = (
    ("platform", "name"),
    ("platform", "version"),
    ("study_region", "name"),
)
logger = logging.getLogger("field_survey_platform.config")

_config: dict = {}


def _missing_required_paths(config: dict) -> list[str]:
    missing: list[str] = []
    for path in _REQUIRED_PATHS:
        current = config
        for key in path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                missing.append(".".join(path))
                break
        else:
            if current in ("", None):
                missing.append(".".join(path))
    return missing


def validate_config(config: dict) -> dict:
    missing = _missing_required_paths(config)
    return {
        "valid": not missing,
        "missing_required_fields": missing,
        "strict_mode": _STRICT_CONFIG_VALIDATION,
    }


def load_config() -> dict:
    global _config
    if not _CONFIG_FILE.exists():
        _config = {}
        message = (
            f"Platform config file not found: {_CONFIG_FILE}. "
            "Using empty configuration."
        )
        if _STRICT_CONFIG_VALIDATION:
            raise RuntimeError(message)
        logger.warning(message)
        return _config

    try:
        _config = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        message = f"Failed to load platform config from {_CONFIG_FILE}: {exc}"
        if _STRICT_CONFIG_VALIDATION:
            raise RuntimeError(message) from exc
        logger.warning(message)
        _config = {}
        return _config

    validation = validate_config(_config)
    if not validation["valid"]:
        fields = ", ".join(validation["missing_required_fields"])
        message = f"Platform config missing required fields: {fields}"
        if _STRICT_CONFIG_VALIDATION:
            raise RuntimeError(message)
        logger.warning(message)
    return _config


def get_config() -> dict:
    if not _config:
        load_config()
    return _config


def get_platform_info() -> dict:
    cfg = get_config()
    return cfg.get("platform", {})


def get_target_species() -> dict:
    return get_config().get("target_species", {})


def get_study_region() -> dict:
    return get_config().get("study_region", {})


def get_map_config() -> dict:
    return get_config().get("map", {})


def get_features() -> dict:
    return get_config().get("features", {})


def get_theme() -> dict:
    return get_config().get("theme", {})


def get_analysis_config() -> dict:
    return get_config().get("analysis", {})
