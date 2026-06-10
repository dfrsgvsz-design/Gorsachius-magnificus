"""
Runtime path helpers for source and bundled desktop execution.

Production environment variables (preferred names from B-stage release plan):
    SURVEY_DATA_DIR    — writable directory for survey/detection/taxonomy stores
    CHECKPOINTS_DIR    — directory containing trained model checkpoints
    FRONTEND_DIST_DIR  — directory containing the built frontend (index.html)

Legacy environment variables (still honored as fall-backs for existing
deployments and the PyInstaller desktop bundle):
    BIRD_PLATFORM_RUNTIME_DIR
    BIRD_PLATFORM_BACKEND_DIR
    BIRD_PLATFORM_OUTPUT_DIR
    BIRD_PLATFORM_DATA_DIR
    BIRD_PLATFORM_CHECKPOINTS_DIR

If both a preferred and a legacy variable are set, the preferred name wins.
This module is intentionally kept in lock-step with
`shared/backend/utils/runtime_paths.py` and `species_monitoring_platform/backend/runtime_paths.py`
pending the P1 consolidation that moves all callers to `shared.backend.*`.
"""

from __future__ import annotations

import os
from pathlib import Path


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    return Path(value).expanduser().resolve()


def _first_env_path(*names: str) -> Path | None:
    for name in names:
        resolved = _env_path(name)
        if resolved is not None:
            return resolved
    return None


def get_runtime_dir() -> Path | None:
    return _env_path("BIRD_PLATFORM_RUNTIME_DIR")


def _runtime_child_dir(name: str) -> Path | None:
    runtime_dir = get_runtime_dir()
    if runtime_dir is None:
        return None
    return runtime_dir / name


def get_backend_dir() -> Path:
    override = _env_path("BIRD_PLATFORM_BACKEND_DIR")
    if override:
        return override
    return Path(__file__).resolve().parent


def get_output_dir() -> Path:
    override = _env_path("BIRD_PLATFORM_OUTPUT_DIR")
    if override:
        return override
    runtime_dir = _runtime_child_dir("output")
    if runtime_dir:
        return runtime_dir
    return get_backend_dir().parent


def get_resource_data_dir() -> Path:
    return get_backend_dir() / "data"


def get_data_dir() -> Path:
    override = _first_env_path("SURVEY_DATA_DIR", "BIRD_PLATFORM_DATA_DIR")
    if override:
        return override
    runtime_dir = _runtime_child_dir("data")
    if runtime_dir:
        return runtime_dir
    return get_resource_data_dir()


def get_checkpoints_dir() -> Path:
    override = _first_env_path("CHECKPOINTS_DIR", "BIRD_PLATFORM_CHECKPOINTS_DIR")
    if override:
        return override
    return get_backend_dir() / "checkpoints"


def get_static_dir() -> Path:
    return get_backend_dir() / "static"


def get_frontend_dist_dir() -> Path:
    override = _env_path("FRONTEND_DIST_DIR")
    if override:
        return override
    candidate = get_backend_dir().parent / "frontend" / "dist"
    return candidate if candidate.exists() else get_static_dir()


def describe_runtime_paths() -> dict[str, str | bool | None]:
    runtime_dir = get_runtime_dir()
    data_dir = get_data_dir()
    output_dir = get_output_dir()
    resource_data_dir = get_resource_data_dir()
    checkpoints_dir = get_checkpoints_dir()
    frontend_dist_dir = get_frontend_dist_dir()
    default_checkpoints = get_backend_dir() / "checkpoints"

    data_dir_externalized = (
        _first_env_path("SURVEY_DATA_DIR", "BIRD_PLATFORM_DATA_DIR") is not None
        or get_runtime_dir() is not None
    )
    checkpoints_externalized = (
        _first_env_path("CHECKPOINTS_DIR", "BIRD_PLATFORM_CHECKPOINTS_DIR") is not None
        or checkpoints_dir != default_checkpoints
    )
    frontend_externalized = _env_path("FRONTEND_DIST_DIR") is not None

    return {
        "runtime_dir": str(runtime_dir) if runtime_dir else None,
        "backend_dir": str(get_backend_dir()),
        "resource_data_dir": str(resource_data_dir),
        "data_dir": str(data_dir),
        "output_dir": str(output_dir),
        "checkpoints_dir": str(checkpoints_dir),
        "frontend_dist_dir": str(frontend_dist_dir),
        "mutable_data_externalized": data_dir != resource_data_dir,
        "mutable_output_externalized": (
            runtime_dir is not None or _env_path("BIRD_PLATFORM_OUTPUT_DIR") is not None
        ),
        "mutable_runtime_externalized": (
            data_dir != resource_data_dir
            and (
                runtime_dir is not None
                or _env_path("BIRD_PLATFORM_OUTPUT_DIR") is not None
            )
        ),
        "data_dir_externalized": data_dir_externalized,
        "checkpoints_dir_externalized": checkpoints_externalized,
        "frontend_dist_dir_externalized": frontend_externalized,
        "env_var_aliases": {
            "data_dir": ["SURVEY_DATA_DIR", "BIRD_PLATFORM_DATA_DIR"],
            "checkpoints_dir": ["CHECKPOINTS_DIR", "BIRD_PLATFORM_CHECKPOINTS_DIR"],
            "frontend_dist_dir": ["FRONTEND_DIST_DIR"],
        },
    }
