import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main as backend_main
from survey_store import SurveyStore
from taxonomy_catalog import TaxonomyCatalog


class TaxonomyApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.original_state = {
            "survey_store": backend_main.survey_store,
            "taxonomy_catalog": getattr(backend_main, "taxonomy_catalog", None),
            "startup": list(backend_main.app.router.on_startup),
            "shutdown": list(backend_main.app.router.on_shutdown),
            "rate_limits": dict(backend_main._rate_limits),
            "rate_gc_counter": backend_main._rate_gc_counter,
        }
        backend_main.app.router.on_startup = []
        backend_main.app.router.on_shutdown = []
        self.addCleanup(self._restore_state)

        backend_main.survey_store = SurveyStore(storage_dir=self.temp_dir.name)
        backend_main.taxonomy_catalog = TaxonomyCatalog(storage_dir=self.temp_dir.name)

        self.client = TestClient(backend_main.app)
        self.addCleanup(self.client.close)

    def _restore_state(self):
        if (
            backend_main.survey_store
            and backend_main.survey_store is not self.original_state["survey_store"]
        ):
            backend_main.survey_store.close()
        backend_main.survey_store = self.original_state["survey_store"]

        current_catalog = getattr(backend_main, "taxonomy_catalog", None)
        if (
            current_catalog
            and current_catalog is not self.original_state["taxonomy_catalog"]
        ):
            current_catalog.close()
        backend_main.taxonomy_catalog = self.original_state["taxonomy_catalog"]

        backend_main.app.router.on_startup = self.original_state["startup"]
        backend_main.app.router.on_shutdown = self.original_state["shutdown"]
        backend_main._rate_limits = dict(self.original_state["rate_limits"])
        backend_main._rate_gc_counter = self.original_state["rate_gc_counter"]

    def test_taxonomy_search_filters_vertebrates_by_program_jurisdiction_and_query(
        self,
    ):
        response = self.client.get(
            "/api/surveys/taxonomy/search",
            params={
                "program": "terrestrial_vertebrates",
                "jurisdiction": "taiwan",
                "q": "Macaca",
                "limit": 5,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        result = payload["results"][0]
        self.assertEqual(result["taxon_id"], "vert-mammal-macaca-cyclopis")
        self.assertEqual(result["submodule"], "mammals")
        self.assertEqual(result["package_id"], "tw_terrestrial_vertebrates_seed")
        self.assertEqual(result["jurisdiction"], "taiwan")
        self.assertEqual(result["matched_name"], "Macaca cyclopis")

        mainland = self.client.get(
            "/api/surveys/taxonomy/search",
            params={
                "program": "terrestrial_vertebrates",
                "jurisdiction": "mainland_china",
                "q": "Macaca",
                "limit": 5,
            },
        )
        self.assertEqual(mainland.status_code, 200)
        self.assertEqual(mainland.json()["total"], 0)

    def test_taxonomy_search_respects_protocol_scope_and_keeps_legacy_species_endpoint(
        self,
    ):
        vertebrate_response = self.client.get(
            "/api/surveys/taxonomy/search",
            params={
                "protocol": "mammal_trap_net",
                "jurisdiction": "taiwan",
                "submodule": "mammals",
                "q": "pangolin",
                "limit": 10,
            },
        )
        self.assertEqual(vertebrate_response.status_code, 200)
        vertebrate_payload = vertebrate_response.json()
        self.assertEqual(vertebrate_payload["total"], 1)
        self.assertEqual(
            vertebrate_payload["results"][0]["taxon_id"],
            "vert-mammal-manis-pentadactyla",
        )

        plant_response = self.client.get(
            "/api/surveys/taxonomy/search",
            params={
                "protocol": "plant_quadrat",
                "jurisdiction": "taiwan",
                "q": "pangolin",
                "limit": 10,
            },
        )
        self.assertEqual(plant_response.status_code, 200)
        self.assertEqual(plant_response.json()["total"], 0)

        legacy_species = self.client.get("/api/species", params={"limit": 3})
        self.assertEqual(legacy_species.status_code, 200)
        species_payload = legacy_species.json()
        self.assertEqual(species_payload["total"], 3)
        self.assertIn("scientific_name", species_payload["species"][0])
        self.assertNotIn("program", species_payload["species"][0])

    def test_taxonomy_packages_report_real_seed_assets_for_plants_and_insects(self):
        response = self.client.get(
            "/api/surveys/taxonomy/packages",
            params={"program": "plants"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 2)
        self.assertTrue(
            all(item["local_seed_asset_count"] > 0 for item in payload["packages"])
        )
        self.assertTrue(all(item["catalog_count"] >= 2 for item in payload["packages"]))

        insect_response = self.client.get(
            "/api/surveys/taxonomy/search",
            params={
                "program": "insects",
                "jurisdiction": "taiwan",
                "q": "Papilio maraho",
                "limit": 5,
            },
        )
        self.assertEqual(insect_response.status_code, 200)
        insect_payload = insect_response.json()
        self.assertEqual(insect_payload["total"], 1)
        self.assertEqual(
            insect_payload["results"][0]["source_kind"], "generic_seed_asset"
        )

    def test_taxonomy_packages_expose_release_metadata_for_admin_surfaces(self):
        response = self.client.get(
            "/api/surveys/taxonomy/packages",
            params={
                "jurisdiction": "mainland_china",
                "program": "terrestrial_vertebrates",
                "protocol": "bird_point_count",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)

        package = payload["packages"][0]
        self.assertEqual(package["package_id"], "cn-mainland-terrestrial-vertebrates")
        self.assertEqual(
            package["asset_package_id"], "cn_mainland_terrestrial_vertebrates_seed"
        )
        self.assertEqual(package["asset_package_version"], "2026.04-seed")
        self.assertEqual(
            set(package["protocols"]),
            {
                "bird_line_transect",
                "bird_point_count",
                "mammal_trap_net",
                "herp_infrared_camera",
            },
        )
        self.assertIn("birds", package["taxa_groups"])
        self.assertEqual(package["languages"], ["zh-Hans", "en", "scientific"])
        self.assertTrue(package["seed_only"])
        self.assertFalse(package["exhaustive_species_content"])
        self.assertFalse(package["exhaustive"])
        self.assertEqual(package["catalog_status"], "seed_only")
        self.assertEqual(package["local_seed_asset_count"], 2)
        self.assertGreater(package["catalog_entry_count"], 0)
        self.assertEqual(package["catalog_count"], package["catalog_entry_count"])

    def test_taxonomy_admin_release_endpoints_expose_current_release_and_discrepancies(
        self,
    ):
        releases_response = self.client.get("/api/admin/taxonomy/releases")
        self.assertEqual(releases_response.status_code, 200)
        releases_payload = releases_response.json()
        self.assertGreaterEqual(releases_payload["total"], 1)
        self.assertTrue(releases_payload["current_taxonomy_release_id"])
        self.assertEqual(
            releases_payload["current_release"]["taxonomy_release_id"],
            releases_payload["current_taxonomy_release_id"],
        )

        current_response = self.client.get("/api/admin/taxonomy/releases/current")
        self.assertEqual(current_response.status_code, 200)
        current_payload = current_response.json()
        self.assertEqual(
            current_payload["taxonomy_release_id"],
            releases_payload["current_taxonomy_release_id"],
        )
        self.assertIn("taxonomy_exhaustive_package_count", current_payload)
        self.assertIn("taxonomy_review_backlog_count", current_payload)
        self.assertIn("taxonomy_count_parity_ok", current_payload)

        discrepancy_response = self.client.get(
            "/api/admin/taxonomy/discrepancy-report",
            params={"release_id": releases_payload["current_taxonomy_release_id"]},
        )
        self.assertEqual(discrepancy_response.status_code, 200)
        discrepancy_payload = discrepancy_response.json()
        self.assertEqual(
            discrepancy_payload["taxonomy_release_id"],
            releases_payload["current_taxonomy_release_id"],
        )
        self.assertIn("package_count", discrepancy_payload)
        self.assertIn("count_parity_ok", discrepancy_payload)
        self.assertIn("reviews", discrepancy_payload)

    def test_taxonomy_admin_rebuild_and_activate_endpoints_wrap_catalog_methods(self):
        current_release_id = backend_main.taxonomy_catalog.current_release_id()

        rebuild_response = self.client.post(
            "/api/admin/taxonomy/releases/rebuild",
            params={"force": "true", "activate": "false"},
        )
        self.assertEqual(rebuild_response.status_code, 200)
        rebuild_payload = rebuild_response.json()
        self.assertEqual(rebuild_payload["status"], "ok")
        self.assertEqual(
            rebuild_payload["release"]["taxonomy_release_id"],
            current_release_id,
        )
        self.assertFalse(rebuild_payload["release"]["is_current_release"])

        activate_response = self.client.post(
            f"/api/admin/taxonomy/releases/{current_release_id}/activate"
        )
        # Whether activation succeeds depends on whether the bundled seed for
        # the current platform passes the activation-ready threshold (see
        # test_manual_activation_rejects_seed_release_and_rebuild_without_activate_keeps_candidate_non_current
        # for the catalog-level equivalent). 200 (activated) or 409
        # (activation-ready failure) are both acceptable platform-correct
        # outcomes; anything else is a regression.
        self.assertIn(activate_response.status_code, (200, 409))
        if activate_response.status_code == 200:
            activate_payload = activate_response.json()
            self.assertEqual(activate_payload["status"], "ok")
            self.assertEqual(
                activate_payload["release"].get("taxonomy_release_id")
                or activate_payload["release"].get("release_id"),
                current_release_id,
            )
            self.assertTrue(activate_payload["release"].get("is_current_release"))
        else:
            self.assertIn("activation-ready", activate_response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
