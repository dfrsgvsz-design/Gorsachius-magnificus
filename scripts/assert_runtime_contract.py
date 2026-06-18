"""Assert the production runtime contract (no-demo guard).

This is the single source of truth for the "Production runtime contract"
gate. release_gate.ps1 and release_gate.yml both delegate to this
script so we never drift between local and CI gating logic.

What it checks:
    1. shared.backend.utils.runtime_paths.describe_runtime_paths() reports
       all four *_externalized flags as True. These flags drive the
       /api/health endpoint's "demo mode" detection — if any externalization
       flag is False, the API replies with readiness.mode = "demo" and
       refuses to advertise deployment_ready = True.
    2. shared.backend.utils.platform_config.load_config() loads cleanly and
       the resulting config has a non-empty `platform.name`. Missing or
       broken config falls back to "demo mode" too.

Pre-conditions (the caller stages these env vars):
    SURVEY_DATA_DIR     — writable directory for survey/detection stores
    CHECKPOINTS_DIR     — directory containing trained model checkpoints
    FRONTEND_DIST_DIR   — directory containing the built frontend
    BIRD_API_KEY        — required in production (any non-empty string)
    CORS_ORIGINS        — required in production
    APP_ENV=production  — flips the runtime contract into strict mode

Usage:
    python scripts/assert_runtime_contract.py           # human-readable
    python scripts/assert_runtime_contract.py --json    # JSON output

Exit codes:
    0  — contract holds
    1  — one or more invariants failed (diagnostic printed)
    2  — script bug / unexpected import error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _check_contract() -> dict:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    from shared.backend.utils.runtime_paths import describe_runtime_paths
    from shared.backend.utils.platform_config import load_config, validate_config

    paths = describe_runtime_paths()
    required_flags = (
        "data_dir_externalized",
        "checkpoints_dir_externalized",
        "frontend_dist_dir_externalized",
        "mutable_runtime_externalized",
    )
    missing_flags = [name for name in required_flags if not paths.get(name)]

    cfg = load_config()
    validation = validate_config(cfg)
    platform_name = (cfg.get("platform") or {}).get("name", "")

    failures: list[str] = []
    if missing_flags:
        failures.append(
            "runtime_paths externalization flags missing: "
            + ", ".join(missing_flags)
        )
    if not validation["valid"]:
        failures.append(
            "shared platform_config invalid: "
            + ", ".join(validation["missing_required_fields"])
        )
    elif not platform_name:
        failures.append("shared platform_config missing platform.name")

    return {
        "passed": not failures,
        "platform_name": platform_name,
        "missing_externalization_flags": missing_flags,
        "config_validation": validation,
        "runtime_paths": paths,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON report instead of human text",
    )
    args = parser.parse_args()

    try:
        result = _check_contract()
    except Exception as exc:  # noqa: BLE001 - surface unexpected import errors
        print(f"FAIL contract assertion bug: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    elif result["passed"]:
        print(
            "OK runtime contract (no demo mode): "
            f"{result['platform_name']}"
        )
    else:
        print("FAIL production runtime contract:")
        for line in result["failures"]:
            print(f"  - {line}")
        print(
            json.dumps(
                {
                    "runtime_paths": result["runtime_paths"],
                    "config_validation": result["config_validation"],
                },
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        )

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
