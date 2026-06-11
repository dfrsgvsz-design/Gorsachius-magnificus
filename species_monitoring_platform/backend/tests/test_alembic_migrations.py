"""Tests for the P0 W3 alembic integration for survey_store.

Covers three boot scenarios the runtime helper distinguishes:
    1. Empty DB           -> alembic upgrade head creates all baseline tables
                             AND records 0001_survey_store_baseline as current.
    2. Pre-alembic DB     -> existing schema (created via the old _DDL path)
                             is stamped at baseline without DDL replay.
    3. Roundtrip          -> upgrade head, downgrade base, upgrade head again
                             — schema reaches the same shape both times.

Also asserts SurveyStore.__init__ itself runs migrations cleanly when the
operator points it at a fresh tempdir, so the lifespan hook is exercised.
"""

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2].parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


from shared.backend.stores.migrations_runtime import (
    apply_survey_store_migrations,
    survey_store_migration_config,
)
from survey_store import SurveyStore


def _table_names(db_path: Path) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


def _current_revision(db_path: Path) -> str:
    conn = sqlite3.connect(str(db_path))
    try:
        try:
            row = conn.execute(
                "SELECT version_num FROM alembic_version LIMIT 1"
            ).fetchone()
        except sqlite3.OperationalError:
            return ""
        return row[0] if row else ""
    finally:
        conn.close()


class AlembicSurveyStoreTests(unittest.TestCase):
    def test_fresh_db_upgrade_head_creates_baseline_tables(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "survey_store.db"
            apply_survey_store_migrations(db_path)

            tables = _table_names(db_path)
            for required in (
                "alembic_version",
                "survey_projects",
                "survey_sites",
                "survey_observations",
                "survey_sync_jobs",
                "survey_sync_conflicts",
                "survey_audit_log",
            ):
                self.assertIn(required, tables, f"missing baseline table: {required}")
            self.assertEqual(
                _current_revision(db_path), "0001_survey_store_baseline"
            )

    def test_pre_alembic_db_is_stamped_without_ddl_replay(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "survey_store.db"
            # Simulate a deployed DB from before alembic landed: create a
            # baseline table directly so the helper sees survey_projects but
            # not alembic_version.
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(
                    """
                    CREATE TABLE survey_projects (
                        project_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        region TEXT DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        deleted_at TEXT DEFAULT ''
                    )
                    """
                )
                conn.execute(
                    "INSERT INTO survey_projects (project_id, name, created_at, updated_at, payload_json) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("preexisting-id", "Pre-alembic project", "t0", "t0", "{}"),
                )
                conn.commit()
            finally:
                conn.close()

            self.assertNotIn("alembic_version", _table_names(db_path))
            apply_survey_store_migrations(db_path)

            # After stamping + upgrade head, the survey_projects row must
            # still be there (i.e. DDL was NOT replayed and data was NOT lost).
            tables = _table_names(db_path)
            self.assertIn("alembic_version", tables)
            self.assertIn("survey_projects", tables)
            self.assertEqual(
                _current_revision(db_path), "0001_survey_store_baseline"
            )

            conn = sqlite3.connect(str(db_path))
            try:
                row = conn.execute(
                    "SELECT name FROM survey_projects WHERE project_id=?",
                    ("preexisting-id",),
                ).fetchone()
            finally:
                conn.close()
            self.assertIsNotNone(row, "pre-alembic data was wiped during stamp")
            self.assertEqual(row[0], "Pre-alembic project")

    def test_upgrade_downgrade_roundtrip(self):
        try:
            from alembic import command
        except ImportError:
            self.skipTest("alembic not installed")

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "survey_store.db"
            apply_survey_store_migrations(db_path)
            baseline_tables = _table_names(db_path)

            config = survey_store_migration_config(db_path)
            command.downgrade(config, "base")

            after_downgrade = _table_names(db_path)
            # Only alembic plumbing should remain after downgrade base.
            self.assertNotIn("survey_projects", after_downgrade)
            self.assertNotIn("survey_observations", after_downgrade)

            command.upgrade(config, "head")
            after_reupgrade = _table_names(db_path)
            self.assertEqual(baseline_tables, after_reupgrade)

    def test_survey_store_init_invokes_migrations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SurveyStore(storage_dir=temp_dir)
            try:
                db_path = Path(temp_dir) / "survey_store.db"
                tables = _table_names(db_path)
                # The lifespan path must produce an alembic_version row.
                self.assertIn("alembic_version", tables)
                self.assertEqual(
                    _current_revision(db_path),
                    "0001_survey_store_baseline",
                )
                # And the store should be usable immediately.
                project = store.upsert_project(
                    {"name": "Alembic-touched", "region": "test"}
                )
                self.assertTrue(project.get("project_id"))
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
