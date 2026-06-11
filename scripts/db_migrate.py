"""Operator CLI for the survey_store alembic migrations.

Thin wrapper around alembic so the operator never has to remember the
alembic command-line shape or set sqlalchemy.url by hand. Resolves the
target database from SURVEY_DATA_DIR / BIRD_PLATFORM_DATA_DIR via
``shared.backend.utils.runtime_paths.get_data_dir()`` so the same script
works in dev, staging, and production without any per-host hacking.

Usage:
    python scripts/db_migrate.py current
    python scripts/db_migrate.py history
    python scripts/db_migrate.py upgrade head
    python scripts/db_migrate.py upgrade +1
    python scripts/db_migrate.py downgrade -1
    python scripts/db_migrate.py stamp head
    python scripts/db_migrate.py heads
    python scripts/db_migrate.py revision -m "describe change"

Override the database location (e.g. when targeting a backup):
    python scripts/db_migrate.py --db /path/to/survey_store.db current
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _resolve_default_db() -> Path:
    """Match the production resolution path used by SurveyStore.__init__."""

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from shared.backend.utils.runtime_paths import get_data_dir

    return (get_data_dir() / "survey_store" / "survey_store.db").resolve()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help=(
            "Explicit path to the survey_store.db SQLite file. Defaults to "
            "<SURVEY_DATA_DIR or BIRD_PLATFORM_DATA_DIR>/survey_store/"
            "survey_store.db."
        ),
    )
    parser.add_argument(
        "command",
        help=(
            "alembic command (current / history / upgrade / downgrade / stamp "
            "/ heads / revision / show / branches)"
        ),
    )
    parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="Positional + flag args forwarded to alembic.",
    )
    parsed = parser.parse_args()

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    db_path = parsed.db or _resolve_default_db()
    db_path = db_path.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    from shared.backend.stores.migrations_runtime import (
        survey_store_migration_config,
    )

    config = survey_store_migration_config(db_path)
    print(f"[db_migrate] target: sqlite:///{db_path.as_posix()}", file=sys.stderr)

    try:
        from alembic import command as _cmd
    except ImportError:
        print(
            "[db_migrate] FAIL: alembic is not installed. "
            "Run `pip install alembic` and retry.",
            file=sys.stderr,
        )
        return 2

    fn = getattr(_cmd, parsed.command, None)
    if fn is None:
        print(
            f"[db_migrate] FAIL: unknown alembic command: {parsed.command!r}",
            file=sys.stderr,
        )
        return 2

    # Forward all remaining positional args. Flag args like `-m "message"`
    # for `revision` are parsed manually because alembic's command functions
    # take keyword arguments rather than a flat argv list.
    extra_args = list(parsed.args)
    kwargs: dict = {}
    positional: list = []
    i = 0
    while i < len(extra_args):
        token = extra_args[i]
        if token.startswith("--"):
            key = token[2:]
            if "=" in key:
                key, value = key.split("=", 1)
                kwargs[key.replace("-", "_")] = value
            else:
                # Next token is the value unless it's another flag.
                if i + 1 < len(extra_args) and not extra_args[i + 1].startswith(
                    "-"
                ):
                    kwargs[key.replace("-", "_")] = extra_args[i + 1]
                    i += 1
                else:
                    kwargs[key.replace("-", "_")] = True
        elif token.startswith("-") and len(token) >= 2:
            # Short flags (-m "message"): the next token is always the value.
            key = token.lstrip("-")
            if i + 1 < len(extra_args):
                kwargs[{"m": "message"}.get(key, key)] = extra_args[i + 1]
                i += 1
            else:
                kwargs[key] = True
        else:
            positional.append(token)
        i += 1

    fn(config, *positional, **kwargs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
