"""Lifespan-time entry point for survey_store alembic migrations.

Why this lives outside `migrations/`:
    `migrations/env.py` is alembic's *config* module — it gets invoked by
    alembic itself, not by the application. This module is the helper the
    application + CLI both reach for to actually fire alembic commands.

What it does:
    `apply_survey_store_migrations(db_path)` brings a survey_store SQLite
    database up to `head`. It handles three boot scenarios:

      * Fresh empty DB         → alembic upgrade head creates everything
      * Pre-alembic existing DB → stamp at baseline (no DDL replay), then
                                  upgrade head walks any new revisions
      * Up-to-date DB          → alembic upgrade head is a no-op

    The detection of "pre-alembic existing DB" looks at the SQLite catalog
    for both `alembic_version` (alembic's version table) and `survey_projects`
    (a representative baseline table) so we never re-run baseline DDL on a
    populated database.

When NOT to use this helper:
    SurveyStore._init_schema still runs its idempotent CREATE IF NOT EXISTS
    block after migrations as a defense-in-depth safety net (in case alembic
    itself fails to import or the migration registry is incomplete). The
    helper short-circuits to a warning-only mode if alembic is unavailable
    rather than raising, so an old wheel without the alembic dependency can
    still boot.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Optional


_LOGGER = logging.getLogger("field_survey_platform.migrations")

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_BASELINE_REVISION = "0001_survey_store_baseline"
# Representative table from the baseline; if this exists we know the DB
# has been initialized at least once.
_BASELINE_TABLE = "survey_projects"


def _existing_tables(db_path: Path) -> set[str]:
    if not db_path.exists():
        return set()
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


def apply_survey_store_migrations(db_path: Path) -> Optional[str]:
    """Bring the survey_store SQLite database at ``db_path`` to head.

    Returns the head revision id on success, or ``None`` if alembic is not
    installed (in which case the caller's ``_init_schema`` fallback takes
    over and emits its own log line about pre-alembic mode).
    """

    try:
        from alembic import command
        from alembic.config import Config
    except ImportError:
        _LOGGER.warning(
            "alembic is not installed (`pip install alembic`); "
            "falling back to _init_schema's CREATE IF NOT EXISTS path. "
            "Schema is still created correctly but no migration version is "
            "tracked, so rollback/forward-migration tooling is unavailable."
        )
        return None

    db_path = Path(db_path).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    config = Config(str(_MIGRATIONS_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")

    existing = _existing_tables(db_path)
    has_alembic_table = "alembic_version" in existing
    has_baseline_table = _BASELINE_TABLE in existing

    if has_baseline_table and not has_alembic_table:
        _LOGGER.info(
            "survey_store at %s has pre-alembic schema; stamping at baseline "
            "%s without replaying DDL.",
            db_path,
            _BASELINE_REVISION,
        )
        command.stamp(config, _BASELINE_REVISION)

    _LOGGER.info("survey_store: alembic upgrade head (db=%s)", db_path)
    command.upgrade(config, "head")
    return "head"


def survey_store_migration_config(db_path: Path):
    """Return an alembic Config bound to ``db_path`` for CLI use.

    This is what scripts/db_migrate.py reaches for so the operator can
    `python scripts/db_migrate.py current` / `... upgrade head` /
    `... downgrade -1` against whichever SURVEY_DATA_DIR is currently
    deployed without touching alembic.ini by hand.
    """

    from alembic.config import Config

    db_path = Path(db_path).resolve()
    config = Config(str(_MIGRATIONS_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    return config
