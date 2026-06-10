"""Tests for B19 (admin token), B20 (audit log), B21 (trash GC), B10 (health probes)."""

import hashlib
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main as backend_main
from detection_store import DetectionStore
from device_manager import DeviceManager
from middleware import admin_auth
from middleware.audit_log import classify_operation
from realtime import RealtimeProcessor
from survey_store import SurveyStore


class _ClientHarness(unittest.TestCase):
    """Same lightweight harness as test_api_smoke: no startup events, temp stores."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.original_state = {
            "model": backend_main.model,
            "species_mapping": backend_main.species_mapping,
            "species_db": backend_main.species_db,
            "device_mgr": backend_main.device_mgr,
            "rt_processor": backend_main.rt_processor,
            "det_store": backend_main.det_store,
            "emb_engine": backend_main.emb_engine,
            "survey_store": backend_main.survey_store,
            "startup": list(backend_main.app.router.on_startup),
            "shutdown": list(backend_main.app.router.on_shutdown),
        }
        backend_main.app.router.on_startup = []
        backend_main.app.router.on_shutdown = []
        self.addCleanup(self._restore_state)

        backend_main.model = object()
        backend_main.species_mapping = {f"species-{idx}": idx for idx in range(12)}
        backend_main.species_db = SimpleNamespace(count=15)
        backend_main.device_mgr = DeviceManager()
        backend_main.rt_processor = RealtimeProcessor()
        backend_main.det_store = DetectionStore(storage_dir=self.temp_dir.name)
        backend_main.survey_store = SurveyStore(storage_dir=self.temp_dir.name)
        backend_main.emb_engine = SimpleNamespace(
            get_stats=lambda: {"total_records": 0, "sessions": 0, "unique_species": 0}
        )

        self.client = TestClient(backend_main.app)
        self.addCleanup(self.client.close)

    def _restore_state(self):
        if (
            backend_main.det_store
            and backend_main.det_store is not self.original_state["det_store"]
        ):
            backend_main.det_store.close()
        if (
            backend_main.survey_store
            and backend_main.survey_store is not self.original_state["survey_store"]
        ):
            backend_main.survey_store.close()
        for key in (
            "model",
            "species_mapping",
            "species_db",
            "device_mgr",
            "rt_processor",
            "det_store",
            "emb_engine",
            "survey_store",
        ):
            setattr(backend_main, key, self.original_state[key])
        backend_main.app.router.on_startup = self.original_state["startup"]
        backend_main.app.router.on_shutdown = self.original_state["shutdown"]

    def _create_project(self, name="Admin guard project"):
        response = self.client.post("/api/surveys/projects", json={"name": name})
        self.assertEqual(response.status_code, 200)
        return response.json()["project"]["project_id"]


class AdminTokenTests(_ClientHarness):
    def test_derivation_matches_reference_vector(self):
        pin = "123456"
        expected = hashlib.pbkdf2_hmac(
            "sha256", pin.encode(), b"gm-admin-token-v1", 100_000
        ).hex()
        self.assertEqual(admin_auth.derive_admin_token(pin), expected)

    def test_delete_allowed_when_auth_disabled(self):
        with patch.dict(
            "os.environ", {"ADMIN_PIN": "", "ADMIN_API_TOKEN": ""}, clear=False
        ):
            project_id = self._create_project()
            response = self.client.delete(f"/api/surveys/projects/{project_id}")
            self.assertEqual(response.status_code, 200)

    def test_delete_requires_token_when_enabled(self):
        with patch.dict(
            "os.environ",
            {"ADMIN_API_TOKEN": "secret-token", "ADMIN_PIN": ""},
            clear=False,
        ):
            project_id = self._create_project()

            missing = self.client.delete(f"/api/surveys/projects/{project_id}")
            self.assertEqual(missing.status_code, 401)

            wrong = self.client.delete(
                f"/api/surveys/projects/{project_id}",
                headers={"X-Admin-Token": "nope"},
            )
            self.assertEqual(wrong.status_code, 401)

            ok = self.client.delete(
                f"/api/surveys/projects/{project_id}",
                headers={"X-Admin-Token": "secret-token"},
            )
            self.assertEqual(ok.status_code, 200)

    def test_restore_requires_token_and_pin_derivation_works(self):
        pin = "4711"
        token = admin_auth.derive_admin_token(pin)
        with patch.dict(
            "os.environ", {"ADMIN_PIN": pin, "ADMIN_API_TOKEN": ""}, clear=False
        ):
            project_id = self._create_project()
            deleted = self.client.delete(
                f"/api/surveys/projects/{project_id}",
                headers={"X-Admin-Token": token},
            )
            self.assertEqual(deleted.status_code, 200)

            denied = self.client.post(f"/api/surveys/projects/{project_id}/restore")
            self.assertEqual(denied.status_code, 401)

            restored = self.client.post(
                f"/api/surveys/projects/{project_id}/restore",
                headers={"X-Admin-Token": token},
            )
            self.assertEqual(restored.status_code, 200)

    def test_audit_log_endpoint_is_admin_only(self):
        with patch.dict(
            "os.environ",
            {"ADMIN_API_TOKEN": "audit-secret", "ADMIN_PIN": ""},
            clear=False,
        ):
            denied = self.client.get("/api/surveys/audit-log")
            self.assertEqual(denied.status_code, 401)
            allowed = self.client.get(
                "/api/surveys/audit-log",
                headers={"X-Admin-Token": "audit-secret"},
            )
            self.assertEqual(allowed.status_code, 200)
            self.assertIn("entries", allowed.json())


class AuditLogTests(_ClientHarness):
    def test_mutating_survey_ops_are_audited(self):
        project_id = self._create_project("Audited project")
        self.client.delete(
            f"/api/surveys/projects/{project_id}",
            headers={"X-Device-Id": "device-42", "X-User-Id": "ranger-li"},
        )

        entries = backend_main.survey_store.list_audit_entries(limit=10)
        self.assertGreaterEqual(len(entries), 2)

        delete_entry = next(e for e in entries if e["op"] == "delete")
        self.assertEqual(delete_entry["entity_type"], "project")
        self.assertEqual(delete_entry["entity_id"], project_id)
        self.assertEqual(delete_entry["device_id"], "device-42")
        self.assertEqual(delete_entry["user_id"], "ranger-li")
        self.assertEqual(delete_entry["status_code"], 200)
        self.assertEqual(delete_entry["method"], "DELETE")

        create_entry = next(e for e in entries if e["op"] == "create_or_update")
        self.assertEqual(create_entry["entity_type"], "project")

    def test_classify_operation_paths(self):
        self.assertEqual(
            classify_operation("DELETE", "/api/surveys/projects/p1"),
            ("delete", "project", "p1"),
        )
        self.assertEqual(
            classify_operation("POST", "/api/surveys/sites/s9/restore"),
            ("restore", "site", "s9"),
        )
        self.assertEqual(
            classify_operation("POST", "/api/surveys/sync/push"),
            ("sync_push", "sync", ""),
        )
        self.assertEqual(
            classify_operation("DELETE", "/api/devices/dev-1"),
            ("delete", "device", "dev-1"),
        )
        self.assertEqual(
            classify_operation("DELETE", "/api/surveys/Old%20Site"),
            ("delete", "legacy_site", "Old%20Site"),
        )


class TrashGcTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.store = SurveyStore(storage_dir=self.temp_dir.name)
        self.addCleanup(self.store.close)

    def _backdate_tombstone(self, table, id_field, entity_id, days):
        stamp = (
            (datetime.now(UTC) - timedelta(days=days))
            .isoformat()
            .replace("+00:00", "Z")
        )
        with self.store._lock:
            with self.store._conn:
                self.store._conn.execute(
                    f"UPDATE {table} SET deleted_at=? WHERE {id_field}=?",
                    (stamp, entity_id),
                )

    def test_purge_expired_trash_archives_and_deletes(self):
        old = self.store.upsert_project({"name": "old project"})
        fresh = self.store.upsert_project({"name": "fresh project"})
        self.store.delete_entity("project", old["project_id"])
        self.store.delete_entity("project", fresh["project_id"])
        self._backdate_tombstone(
            "survey_projects", "project_id", old["project_id"], days=45
        )

        summary = self.store.purge_expired_trash(retention_days=30)

        self.assertEqual(summary["purged"].get("project"), 1)
        self.assertTrue(summary["archived_files"])
        archive = Path(summary["archived_files"][0])
        self.assertTrue(archive.exists())
        self.assertIn(old["project_id"], archive.read_text(encoding="utf-8"))

        remaining_ids = {row["project_id"] for row in self.store.list_trash("project")}
        self.assertNotIn(old["project_id"], remaining_ids)
        self.assertIn(fresh["project_id"], remaining_ids)

        # GC itself is recorded in the audit trail.
        ops = {entry["op"] for entry in self.store.list_audit_entries(limit=10)}
        self.assertIn("trash_gc", ops)

    def test_purge_noop_when_nothing_expired(self):
        project = self.store.upsert_project({"name": "kept"})
        self.store.delete_entity("project", project["project_id"])
        summary = self.store.purge_expired_trash(retention_days=30)
        self.assertEqual(summary["purged_total"], 0)
        self.assertEqual(summary["archived_files"], [])


class HealthProbeTests(_ClientHarness):
    def test_liveness_and_readiness_bypass_api_key(self):
        with patch.object(backend_main, "BIRD_API_KEY", "locked-down"):
            liveness = self.client.get("/api/health/liveness")
            self.assertEqual(liveness.status_code, 200)
            self.assertEqual(liveness.json()["status"], "alive")

            readiness = self.client.get("/api/health/readiness")
            self.assertEqual(readiness.status_code, 200)
            self.assertIn("ready", readiness.json())

            # Sanity: a non-exempt endpoint still requires the API key.
            protected = self.client.get("/api/surveys/projects")
            self.assertEqual(protected.status_code, 401)


if __name__ == "__main__":
    unittest.main()
