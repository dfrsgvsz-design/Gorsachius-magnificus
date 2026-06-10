import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main as backend_main
import runtime_paths


class RuntimePathsTests(unittest.TestCase):
    def test_runtime_root_externalizes_mutable_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir) / "runtime"
            backend_dir = Path(temp_dir) / "bundle" / "backend"
            env = {
                "BIRD_PLATFORM_RUNTIME_DIR": str(runtime_root),
                "BIRD_PLATFORM_BACKEND_DIR": str(backend_dir),
            }

            with patch.dict(os.environ, env, clear=False):
                summary = runtime_paths.describe_runtime_paths()
                self.assertEqual(runtime_paths.get_data_dir(), runtime_root / "data")
                self.assertEqual(
                    runtime_paths.get_output_dir(), runtime_root / "output"
                )
                self.assertEqual(
                    runtime_paths.get_checkpoints_dir(), backend_dir / "checkpoints"
                )
                self.assertTrue(summary["mutable_data_externalized"])
                self.assertTrue(summary["mutable_output_externalized"])
                self.assertTrue(summary["mutable_runtime_externalized"])


class HealthRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.original_state = {
            "model": backend_main.model,
            "species_mapping": backend_main.species_mapping,
            "species_db": backend_main.species_db,
            "device_mgr": backend_main.device_mgr,
            "rt_processor": backend_main.rt_processor,
            "det_store": backend_main.det_store,
            "emb_engine": backend_main.emb_engine,
            "survey_store": backend_main.survey_store,
            "taxonomy_catalog": getattr(backend_main, "taxonomy_catalog", None),
        }
        self.addCleanup(self._restore_state)

    def _restore_state(self):
        backend_main.model = self.original_state["model"]
        backend_main.species_mapping = self.original_state["species_mapping"]
        backend_main.species_db = self.original_state["species_db"]
        backend_main.device_mgr = self.original_state["device_mgr"]
        backend_main.rt_processor = self.original_state["rt_processor"]
        backend_main.det_store = self.original_state["det_store"]
        backend_main.emb_engine = self.original_state["emb_engine"]
        backend_main.survey_store = self.original_state["survey_store"]
        backend_main.taxonomy_catalog = self.original_state["taxonomy_catalog"]

    def _set_runtime_state(
        self, *, model_loaded: bool, model_species: int, db_species: int
    ):
        backend_main.model = object() if model_loaded else None
        backend_main.species_mapping = {
            f"species-{idx}": idx for idx in range(model_species)
        }
        backend_main.species_db = SimpleNamespace(count=db_species)
        backend_main.device_mgr = SimpleNamespace(online_count=2)
        backend_main.rt_processor = SimpleNamespace(
            list_sessions=lambda: [{"id": "s1"}]
        )
        backend_main.det_store = SimpleNamespace(
            get_stats=lambda: {"total_detections": 12}
        )
        backend_main.emb_engine = SimpleNamespace(
            get_stats=lambda: {"total_records": 5}
        )

    def _set_taxonomy_release_state(
        self,
        *,
        packages: list[dict],
        protocol_count: int = 1,
        taxonomy_taxa: int = 1,
        current_release_id: str = "release-2026.04.23",
        review_backlog_count: int = 0,
        count_parity_ok: bool = False,
    ):
        backend_main.survey_store = SimpleNamespace(
            list_protocol_definitions=lambda: [
                {"protocol": f"protocol-{idx}"} for idx in range(protocol_count)
            ],
            list_taxonomy_packages=lambda: packages,
        )
        exhaustive_package_count = sum(
            1
            for item in packages
            if bool(item.get("exhaustive") or item.get("exhaustive_species_content"))
        )
        backend_main.taxonomy_catalog = SimpleNamespace(
            stats=lambda: {
                "taxa": taxonomy_taxa,
                "current_taxonomy_release_id": current_release_id,
                "taxonomy_review_backlog_count": review_backlog_count,
            },
            current_release_summary=lambda: {
                "taxonomy_release_id": current_release_id,
                "taxonomy_exhaustive_package_count": exhaustive_package_count,
                "taxonomy_review_backlog_count": review_backlog_count,
                "taxonomy_count_parity_ok": count_parity_ok,
            },
        )

    def test_runtime_state_prefers_warning_over_ready(self):
        state = backend_main._runtime_state_from_warnings(
            [
                {"level": "info"},
                {"level": "warning"},
            ]
        )
        self.assertEqual(state, "warning")

    def test_health_check_reports_degraded_runtime_for_species_gap(self):
        self._set_runtime_state(model_loaded=True, model_species=217, db_species=254)
        runtime_paths_summary = {
            "runtime_dir": "F:/runtime",
            "backend_dir": "F:/bundle/backend",
            "resource_data_dir": "F:/bundle/backend/data",
            "data_dir": "F:/runtime/data",
            "output_dir": "F:/runtime/output",
            "checkpoints_dir": "F:/bundle/backend/checkpoints",
            "mutable_data_externalized": True,
            "mutable_output_externalized": True,
            "mutable_runtime_externalized": True,
        }

        with patch.object(
            backend_main, "describe_runtime_paths", return_value=runtime_paths_summary
        ):
            with patch.object(
                backend_main.birdnet_engine, "is_available", return_value=False
            ):
                payload = asyncio.run(backend_main.health_check())

        self.assertEqual(payload["runtime_state"], "warning")
        self.assertTrue(payload["ready"])
        self.assertFalse(payload["deployment_ready"])
        self.assertEqual(payload["readiness"]["mode"], "degraded")
        self.assertIn(
            "RUNTIME_WARNINGS_PRESENT", payload["readiness"]["blocking_codes"]
        )
        self.assertEqual(payload["species_coverage"]["missing_from_model"], 37)
        self.assertEqual(payload["devices_online"], 2)
        self.assertEqual(payload["active_sessions"], 1)
        self.assertTrue(
            any(item["code"] == "SPECIES_COVERAGE_GAP" for item in payload["warnings"])
        )

    def test_health_check_distinguishes_demo_mode_from_production_ready(self):
        self._set_runtime_state(model_loaded=True, model_species=254, db_species=254)
        runtime_paths_summary = {
            "runtime_dir": None,
            "backend_dir": "F:/bundle/backend",
            "resource_data_dir": "F:/bundle/backend/data",
            "data_dir": "F:/bundle/backend/data",
            "output_dir": "F:/bundle",
            "checkpoints_dir": "F:/bundle/backend/checkpoints",
            "mutable_data_externalized": False,
            "mutable_output_externalized": False,
            "mutable_runtime_externalized": False,
        }

        with patch.object(
            backend_main, "describe_runtime_paths", return_value=runtime_paths_summary
        ):
            with patch.object(
                backend_main.birdnet_engine, "is_available", return_value=True
            ):
                payload = asyncio.run(backend_main.health_check())

        self.assertEqual(payload["runtime_state"], "ready")
        self.assertTrue(payload["ready"])
        self.assertFalse(payload["deployment_ready"])
        self.assertEqual(payload["readiness"]["mode"], "demo")
        self.assertEqual(
            payload["readiness"]["blocking_codes"],
            ["MUTABLE_RUNTIME_NOT_EXTERNALIZED"],
        )

    def test_health_check_reports_strict_production_readiness(self):
        self._set_runtime_state(model_loaded=True, model_species=254, db_species=254)
        runtime_paths_summary = {
            "runtime_dir": "F:/runtime",
            "backend_dir": "F:/bundle/backend",
            "resource_data_dir": "F:/bundle/backend/data",
            "data_dir": "F:/runtime/data",
            "output_dir": "F:/runtime/output",
            "checkpoints_dir": "F:/bundle/backend/checkpoints",
            "mutable_data_externalized": True,
            "mutable_output_externalized": True,
            "mutable_runtime_externalized": True,
        }

        with patch.object(
            backend_main, "describe_runtime_paths", return_value=runtime_paths_summary
        ):
            with patch.object(
                backend_main.birdnet_engine, "is_available", return_value=False
            ):
                payload = asyncio.run(backend_main.health_check())

        self.assertEqual(payload["runtime_state"], "ready")
        self.assertTrue(payload["ready"])
        self.assertTrue(payload["deployment_ready"])
        self.assertEqual(payload["readiness"]["mode"], "production")
        self.assertEqual(payload["readiness"]["blocking_codes"], [])
        self.assertTrue(payload["runtime_paths"]["mutable_runtime_externalized"])

    def test_health_check_reports_fallback_when_model_missing(self):
        self._set_runtime_state(model_loaded=False, model_species=0, db_species=254)
        runtime_paths_summary = {
            "runtime_dir": "F:/runtime",
            "backend_dir": "F:/bundle/backend",
            "resource_data_dir": "F:/bundle/backend/data",
            "data_dir": "F:/runtime/data",
            "output_dir": "F:/runtime/output",
            "checkpoints_dir": "F:/bundle/backend/checkpoints",
            "mutable_data_externalized": True,
            "mutable_output_externalized": True,
            "mutable_runtime_externalized": True,
        }

        with patch.object(
            backend_main, "describe_runtime_paths", return_value=runtime_paths_summary
        ):
            with patch.object(
                backend_main.birdnet_engine, "is_available", return_value=True
            ):
                payload = asyncio.run(backend_main.health_check())

        self.assertFalse(payload["ready"])
        self.assertFalse(payload["deployment_ready"])
        self.assertEqual(payload["readiness"]["mode"], "fallback")
        self.assertIn("MODEL_NOT_LOADED", payload["readiness"]["blocking_codes"])

    def test_health_check_reports_taxonomy_release_blockers_and_counts(self):
        self._set_runtime_state(model_loaded=True, model_species=254, db_species=254)
        self._set_taxonomy_release_state(
            packages=[
                {
                    "program": "terrestrial_vertebrates",
                    "seed_only": True,
                    "exhaustive": False,
                    "exhaustive_species_content": False,
                    "local_seed_asset_count": 2,
                },
                {
                    "program": "plants",
                    "seed_only": True,
                    "exhaustive": False,
                    "exhaustive_species_content": False,
                    "local_seed_asset_count": 0,
                },
                {
                    "program": "insects",
                    "seed_only": False,
                    "exhaustive": False,
                    "exhaustive_species_content": False,
                    "local_seed_asset_count": 0,
                },
                {
                    "program": "marine",
                    "seed_only": False,
                    "exhaustive": True,
                    "exhaustive_species_content": True,
                    "local_seed_asset_count": 99,
                },
            ],
            protocol_count=4,
            taxonomy_taxa=12,
        )
        runtime_paths_summary = {
            "runtime_dir": "F:/runtime",
            "backend_dir": "F:/bundle/backend",
            "resource_data_dir": "F:/bundle/backend/data",
            "data_dir": "F:/runtime/data",
            "output_dir": "F:/runtime/output",
            "checkpoints_dir": "F:/bundle/backend/checkpoints",
            "mutable_data_externalized": True,
            "mutable_output_externalized": True,
            "mutable_runtime_externalized": True,
        }

        with patch.object(
            backend_main, "describe_runtime_paths", return_value=runtime_paths_summary
        ):
            with patch.object(
                backend_main.birdnet_engine, "is_available", return_value=False
            ):
                payload = asyncio.run(backend_main.health_check())

        survey_readiness = payload["survey_readiness"]
        self.assertEqual(payload["current_taxonomy_release_id"], "release-2026.04.23")
        self.assertEqual(payload["taxonomy_exhaustive_package_count"], 1)
        self.assertFalse(payload["taxonomy_count_parity_ok"])
        self.assertEqual(payload["taxonomy_review_backlog_count"], 0)
        self.assertTrue(survey_readiness["taxonomy_assets_ready"])
        self.assertTrue(survey_readiness["protocol_registry_loaded"])
        self.assertTrue(survey_readiness["attachment_storage_ready"])
        self.assertEqual(survey_readiness["taxonomy_package_count"], 3)
        self.assertEqual(
            survey_readiness["current_taxonomy_release_id"], "release-2026.04.23"
        )
        self.assertEqual(survey_readiness["taxonomy_exhaustive_package_count"], 1)
        self.assertFalse(survey_readiness["taxonomy_count_parity_ok"])
        self.assertEqual(survey_readiness["taxonomy_review_backlog_count"], 0)
        self.assertEqual(survey_readiness["taxonomy_seed_only_package_count"], 2)
        self.assertEqual(survey_readiness["taxonomy_local_seed_asset_gap_count"], 2)
        self.assertEqual(
            survey_readiness["go_live_blockers"],
            [
                "TERRESTRIAL_VERTEBRATE_CATALOG_INCOMPLETE",
                "PLANT_INSECT_SEED_ASSETS_MISSING",
                "TAXONOMY_PACKAGES_STILL_SEED_ONLY",
                "TAXONOMY_RELEASE_COUNT_PARITY_FAILED",
                "TAXONOMY_RELEASE_NOT_EXHAUSTIVE",
            ],
        )
        self.assertFalse(survey_readiness["go_live_ready"])
        self.assertTrue(survey_readiness["deployment_ready"])

    def test_health_check_reports_go_live_ready_when_taxonomy_release_is_complete(self):
        self._set_runtime_state(model_loaded=True, model_species=254, db_species=254)
        self._set_taxonomy_release_state(
            packages=[
                {
                    "program": "terrestrial_vertebrates",
                    "seed_only": False,
                    "exhaustive": True,
                    "exhaustive_species_content": True,
                    "local_seed_asset_count": 1,
                },
                {
                    "program": "plants",
                    "seed_only": False,
                    "exhaustive": True,
                    "exhaustive_species_content": True,
                    "local_seed_asset_count": 1,
                },
                {
                    "program": "insects",
                    "seed_only": False,
                    "exhaustive": True,
                    "exhaustive_species_content": True,
                    "local_seed_asset_count": 1,
                },
            ],
            protocol_count=3,
            taxonomy_taxa=25,
            review_backlog_count=0,
            count_parity_ok=True,
        )
        runtime_paths_summary = {
            "runtime_dir": "F:/runtime",
            "backend_dir": "F:/bundle/backend",
            "resource_data_dir": "F:/bundle/backend/data",
            "data_dir": "F:/runtime/data",
            "output_dir": "F:/runtime/output",
            "checkpoints_dir": "F:/bundle/backend/checkpoints",
            "mutable_data_externalized": True,
            "mutable_output_externalized": True,
            "mutable_runtime_externalized": True,
        }

        with patch.object(
            backend_main, "describe_runtime_paths", return_value=runtime_paths_summary
        ):
            with patch.object(
                backend_main.birdnet_engine, "is_available", return_value=False
            ):
                payload = asyncio.run(backend_main.health_check())

        survey_readiness = payload["survey_readiness"]
        self.assertEqual(payload["current_taxonomy_release_id"], "release-2026.04.23")
        self.assertEqual(payload["taxonomy_exhaustive_package_count"], 3)
        self.assertTrue(payload["taxonomy_count_parity_ok"])
        self.assertEqual(payload["taxonomy_review_backlog_count"], 0)
        self.assertEqual(survey_readiness["go_live_blockers"], [])
        self.assertTrue(survey_readiness["go_live_ready"])
        self.assertTrue(survey_readiness["deployment_ready"])
        self.assertEqual(survey_readiness["taxonomy_exhaustive_package_count"], 3)
        self.assertTrue(survey_readiness["taxonomy_count_parity_ok"])
        self.assertEqual(survey_readiness["taxonomy_review_backlog_count"], 0)


if __name__ == "__main__":
    unittest.main()
