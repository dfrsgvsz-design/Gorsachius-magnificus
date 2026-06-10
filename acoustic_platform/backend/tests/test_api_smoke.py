import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main as backend_main
from detection_store import DetectionStore
from device_manager import DeviceManager
from realtime import RealtimeProcessor
from survey_store import SurveyStore


class ApiSmokeTests(unittest.TestCase):
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
            "rate_limits": dict(backend_main._rate_limits),
            "rate_gc_counter": backend_main._rate_gc_counter,
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
            get_stats=lambda: {"total_records": 3, "sessions": 1, "unique_species": 2}
        )

        self.birdnet_patcher = patch.object(
            backend_main.birdnet_engine, "is_available", return_value=False
        )
        self.birdnet_patcher.start()
        self.addCleanup(self.birdnet_patcher.stop)

        self.client = TestClient(backend_main.app)
        self.addCleanup(self.client.close)

    def _restore_state(self):
        backend_main.model = self.original_state["model"]
        backend_main.species_mapping = self.original_state["species_mapping"]
        backend_main.species_db = self.original_state["species_db"]
        backend_main.device_mgr = self.original_state["device_mgr"]
        backend_main.rt_processor = self.original_state["rt_processor"]
        if (
            backend_main.det_store
            and backend_main.det_store is not self.original_state["det_store"]
        ):
            backend_main.det_store.close()
        backend_main.det_store = self.original_state["det_store"]
        if (
            backend_main.survey_store
            and backend_main.survey_store is not self.original_state["survey_store"]
        ):
            backend_main.survey_store.close()
        backend_main.survey_store = self.original_state["survey_store"]
        backend_main.emb_engine = self.original_state["emb_engine"]
        backend_main.app.router.on_startup = self.original_state["startup"]
        backend_main.app.router.on_shutdown = self.original_state["shutdown"]
        backend_main._rate_limits = dict(self.original_state["rate_limits"])
        backend_main._rate_gc_counter = self.original_state["rate_gc_counter"]

    def test_health_endpoint_reports_runtime_summary(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["runtime_state"], "warning")
        self.assertTrue(payload["ready"])
        self.assertEqual(payload["species_coverage"]["missing_from_model"], 3)
        self.assertIn("warnings", payload)

    def test_devices_endpoints_cover_register_list_map_and_remove(self):
        create_response = self.client.post(
            "/api/devices/register",
            json={
                "name": "Forest Unit A",
                "device_type": "audiomoth",
                "location_name": "Site Alpha",
                "latitude": 22.451,
                "longitude": 106.962,
            },
        )
        self.assertEqual(create_response.status_code, 200)
        device = create_response.json()["device"]
        device_id = device["device_id"]
        self.assertEqual(device["device_type"], "audiomoth")

        list_response = self.client.get("/api/devices")
        self.assertEqual(list_response.status_code, 200)
        listed = list_response.json()
        self.assertEqual(listed["total"], 1)
        self.assertEqual(listed["online"], 1)
        self.assertEqual(listed["devices"][0]["device_id"], device_id)

        map_response = self.client.get("/api/devices/map")
        self.assertEqual(map_response.status_code, 200)
        markers = map_response.json()["markers"]
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0]["device_id"], device_id)

        remove_response = self.client.delete(f"/api/devices/{device_id}")
        self.assertEqual(remove_response.status_code, 200)
        self.assertEqual(remove_response.json()["status"], "ok")

    def test_monitoring_and_detection_endpoints_return_live_data(self):
        device = backend_main.device_mgr.register(
            name="Forest Unit B",
            device_type="raspberry_pi",
            location_name="Site Beta",
            latitude=23.0,
            longitude=108.0,
        )
        session_id = backend_main.device_mgr.start_session(device.device_id)
        session = backend_main.rt_processor.create_session(
            device_id=device.device_id,
            session_id=session_id,
            sample_rate=22050,
            confidence_threshold=0.3,
        )
        session.total_segments = 4
        session.add_detection(
            species="Gorsachius magnificus",
            confidence=0.91,
            segment_time=12.5,
            extra={
                "species_chinese": "White-eared Night Heron",
                "species_english": "White-eared Night Heron",
            },
        )

        detection_id = backend_main.det_store.add_detection(
            species="Gorsachius magnificus",
            confidence=0.33,
            session_id=session_id,
            time_offset=12.5,
            device_id=device.device_id,
            site_name="Site Beta",
            species_chinese="White-eared Night Heron",
        )
        backend_main.det_store.save()

        monitoring_response = self.client.get("/api/monitoring/dashboard")
        self.assertEqual(monitoring_response.status_code, 200)
        dashboard = monitoring_response.json()
        self.assertEqual(dashboard["devices"]["online"], 1)
        self.assertEqual(dashboard["sessions"]["active"], 1)
        self.assertEqual(dashboard["detections"]["total"], 1)

        sessions_response = self.client.get("/api/monitoring/sessions")
        self.assertEqual(sessions_response.status_code, 200)
        sessions = sessions_response.json()["sessions"]
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["session_id"], session_id)

        unverified_response = self.client.get("/api/detections/unverified")
        self.assertEqual(unverified_response.status_code, 200)
        pending = unverified_response.json()["detections"]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["detection_id"], detection_id)

        verify_response = self.client.post(
            "/api/detections/verify",
            json={
                "detection_id": detection_id,
                "status": "confirmed",
                "verified_by": "smoke-test",
                "notes": "Looks correct.",
            },
        )
        self.assertEqual(verify_response.status_code, 200)
        self.assertEqual(verify_response.json()["verification"], "confirmed")

        stats_response = self.client.get("/api/detections/stats")
        self.assertEqual(stats_response.status_code, 200)
        stats = stats_response.json()
        self.assertEqual(stats["confirmed"], 1)
        self.assertEqual(stats["unverified"], 0)

    def test_rate_limit_skips_frontend_routes_and_separates_survey_bucket(self):
        backend_main._rate_limits.clear()
        backend_main._rate_gc_counter = 0

        for _ in range(backend_main._RATE_LIMIT + 5):
            frontend_response = self.client.get("/")
            self.assertEqual(frontend_response.status_code, 200)

        backend_main._rate_limits.clear()
        api_responses = [
            self.client.get("/api/devices") for _ in range(backend_main._RATE_LIMIT + 1)
        ]
        self.assertEqual(api_responses[-1].status_code, 429)
        self.assertIn("general API traffic", api_responses[-1].json()["detail"])

        survey_response = self.client.get("/api/surveys/sync/pull")
        self.assertEqual(survey_response.status_code, 200)

        health_response = self.client.get("/api/health")
        self.assertEqual(health_response.status_code, 200)

        backend_main._rate_limits.clear()
        survey_responses = [
            self.client.get("/api/surveys/sync/pull")
            for _ in range(backend_main._SURVEY_RATE_LIMIT + 1)
        ]
        self.assertEqual(survey_responses[-1].status_code, 429)
        self.assertIn("survey API traffic", survey_responses[-1].json()["detail"])

        general_after_survey = self.client.get("/api/devices")
        self.assertEqual(general_after_survey.status_code, 200)

    def test_analyze_invalid_audio_returns_client_error(self):
        response = self.client.post(
            "/api/analyze",
            files={"file": ("invalid.txt", b"not audio", "text/plain")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid audio file", response.json()["detail"])

    def test_field_survey_endpoints_cover_project_route_observation_track_and_sync(
        self,
    ):
        project_response = self.client.post(
            "/api/surveys/projects",
            json={
                "name": "Nonggang Patrol",
                "region": "Guangxi",
                "target_taxa": ["birds", "mammals"],
            },
        )
        self.assertEqual(project_response.status_code, 200)
        project = project_response.json()["project"]

        site_response = self.client.post(
            "/api/surveys/sites",
            json={
                "project_id": project["project_id"],
                "name": "Valley Site",
                "latitude": 22.45,
                "longitude": 106.95,
                "habitat_type": "evergreen forest",
            },
        )
        self.assertEqual(site_response.status_code, 200)
        site = site_response.json()["site"]

        route_response = self.client.post(
            "/api/surveys/routes",
            json={
                "project_id": project["project_id"],
                "site_id": site["site_id"],
                "name": "Transect A",
                "route_type": "transect",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [106.95, 22.45],
                        [106.951, 22.451],
                        [106.952, 22.452],
                    ],
                },
            },
        )
        self.assertEqual(route_response.status_code, 200)
        route = route_response.json()["route"]
        self.assertGreater(route["length_m"], 0)

        event_response = self.client.post(
            "/api/surveys/events",
            json={
                "project_id": project["project_id"],
                "site_id": site["site_id"],
                "route_id": route["route_id"],
                "program": "terrestrial_vertebrates",
                "protocol": "bird_line_transect",
                "jurisdiction": "mainland_china",
                "started_at": "2026-04-18T00:00:00Z",
                "ended_at": "2026-04-18T00:10:00Z",
                "observers": ["tester"],
            },
        )
        self.assertEqual(event_response.status_code, 200)
        event = event_response.json()["event"]

        observation_response = self.client.post(
            "/api/surveys/observations",
            json={
                "project_id": project["project_id"],
                "site_id": site["site_id"],
                "route_id": route["route_id"],
                "event_id": event["event_id"],
                "program": "terrestrial_vertebrates",
                "protocol": "bird_line_transect",
                "jurisdiction": "mainland_china",
                "scientific_name": "Gorsachius magnificus",
                "chinese_name": "海南鳽",
                "taxon_group": "birds",
                "count": 1,
                "evidence_type": "visual",
                "observer": "tester",
                "latitude": 22.451,
                "longitude": 106.951,
                "observed_at": "2026-04-18T00:05:00Z",
                "extra": {"weather": {"conditions": "Mist", "temperature_c": 19}},
            },
        )
        self.assertEqual(observation_response.status_code, 200)

        snapped_observation_response = self.client.post(
            "/api/surveys/observations",
            json={
                "project_id": project["project_id"],
                "site_id": site["site_id"],
                "snapped_route_id": route["route_id"],
                "event_id": event["event_id"],
                "program": "terrestrial_vertebrates",
                "protocol": "bird_line_transect",
                "jurisdiction": "mainland_china",
                "scientific_name": "Lophura nycthemera",
                "english_name": "Silver Pheasant",
                "taxon_group": "birds",
                "count": 2,
                "observer": "assistant tester",
                "latitude": 22.4515,
                "longitude": 106.9515,
                "observed_at": "2026-04-18T00:10:00Z",
                "extra": {"weather": {"conditions": "Cloudy", "humidity_pct": 90}},
            },
        )
        self.assertEqual(snapped_observation_response.status_code, 200)

        track_response = self.client.post(
            "/api/surveys/tracks",
            json={
                "project_id": project["project_id"],
                "site_id": site["site_id"],
                "route_id": route["route_id"],
                "event_id": event["event_id"],
                "program": "terrestrial_vertebrates",
                "protocol": "bird_line_transect",
                "jurisdiction": "mainland_china",
                "name": "Walk 1",
                "source": "recorded",
                "started_at": "2026-04-18T00:00:00Z",
                "ended_at": "2026-04-18T00:10:00Z",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [106.95, 22.45],
                        [106.951, 22.451],
                        [106.952, 22.452],
                    ],
                },
                "extra": {
                    "observer": "tester",
                    "weather": {"wind": "Light breeze", "temperature_c": 20},
                },
            },
        )
        self.assertEqual(track_response.status_code, 200)
        self.assertGreater(track_response.json()["track"]["distance_m"], 0)

        summary_response = self.client.get(
            f"/api/surveys/routes/{route['route_id']}/summary"
        )
        self.assertEqual(summary_response.status_code, 200)
        summary_payload = summary_response.json()
        self.assertEqual(summary_payload["status"], "ok")
        self.assertEqual(summary_payload["summary"]["totals"]["observation_count"], 2)
        self.assertEqual(summary_payload["summary"]["totals"]["individual_count"], 3)
        self.assertEqual(summary_payload["summary"]["totals"]["track_count"], 1)
        self.assertEqual(
            summary_payload["summary"]["totals"]["unique_species_count"], 2
        )
        self.assertEqual(len(summary_payload["summary"]["species"]), 2)
        self.assertEqual(summary_payload["summary"]["observers"][0]["name"], "tester")
        self.assertIn("Mist", summary_payload["summary"]["weather"]["conditions"])
        self.assertIn("Cloudy", summary_payload["summary"]["weather"]["conditions"])

        export_response = self.client.get(
            f"/api/surveys/routes/{route['route_id']}/export?format=geojson"
        )
        self.assertEqual(export_response.status_code, 200)
        self.assertIn("FeatureCollection", export_response.text)

        report_json_response = self.client.get(
            f"/api/surveys/routes/{route['route_id']}/report/export?format=json"
        )
        self.assertEqual(report_json_response.status_code, 200)
        self.assertEqual(
            report_json_response.headers["content-type"], "application/json"
        )
        self.assertEqual(
            report_json_response.json()["summary"]["totals"]["individual_count"], 3
        )

        report_csv_response = self.client.get(
            f"/api/surveys/routes/{route['route_id']}/report/export?format=csv"
        )
        self.assertEqual(report_csv_response.status_code, 200)
        self.assertEqual(
            report_csv_response.headers["content-type"], "text/csv; charset=utf-8"
        )
        self.assertIn(
            "scientific_name,chinese_name,english_name", report_csv_response.text
        )
        self.assertIn("Gorsachius magnificus", report_csv_response.text)
        self.assertIn("Lophura nycthemera", report_csv_response.text)

        sync_response = self.client.post(
            "/api/surveys/sync/push",
            json={
                "device_id": "device-1",
                "user_id": "tester",
                "operations": [
                    {
                        "entity_type": "project",
                        "operation": "upsert",
                        "payload": {
                            "project_id": project["project_id"],
                            "name": "Nonggang Patrol v2",
                            "server_updated_at": project["updated_at"],
                        },
                    }
                ],
            },
        )
        self.assertEqual(sync_response.status_code, 200)
        self.assertEqual(sync_response.json()["sync_job"]["applied_count"], 1)

        pull_response = self.client.get("/api/surveys/sync/pull")
        self.assertEqual(pull_response.status_code, 200)
        payload = pull_response.json()
        self.assertGreaterEqual(len(payload["projects"]), 1)
        self.assertGreaterEqual(len(payload["sites"]), 1)
        self.assertGreaterEqual(len(payload["routes"]), 1)
        self.assertGreaterEqual(len(payload["observations"]), 1)
        self.assertGreaterEqual(len(payload["tracks"]), 1)
        updated_project = next(
            item
            for item in payload["projects"]
            if item["project_id"] == project["project_id"]
        )
        self.assertEqual(updated_project["name"], "Nonggang Patrol v2")
        self.assertEqual(updated_project["region"], "Guangxi")

    def test_unified_survey_core_endpoints_cover_protocols_taxonomy_assets_events_and_exports(
        self,
    ):
        protocol_response = self.client.get("/api/surveys/protocols?program=plants")
        self.assertEqual(protocol_response.status_code, 200)
        protocol_payload = protocol_response.json()
        self.assertEqual(protocol_payload["total"], 2)
        self.assertEqual(
            {item["protocol"] for item in protocol_payload["protocols"]},
            {"plant_quadrat", "plant_transect"},
        )

        taxonomy_response = self.client.get(
            "/api/surveys/taxonomy/packages?jurisdiction=taiwan&program=terrestrial_vertebrates"
        )
        self.assertEqual(taxonomy_response.status_code, 200)
        taxonomy_payload = taxonomy_response.json()
        self.assertEqual(taxonomy_payload["total"], 1)
        self.assertEqual(
            taxonomy_payload["packages"][0]["package_id"], "tw-terrestrial-vertebrates"
        )
        self.assertEqual(
            taxonomy_payload["packages"][0]["asset_package_id"],
            "tw_terrestrial_vertebrates_seed",
        )
        self.assertTrue(taxonomy_payload["packages"][0]["seed_only"])
        self.assertFalse(taxonomy_payload["packages"][0]["exhaustive"])
        self.assertGreater(taxonomy_payload["packages"][0]["catalog_count"], 0)
        self.assertEqual(taxonomy_payload["packages"][0]["catalog_status"], "seed_only")

        project = self.client.post(
            "/api/surveys/projects",
            json={"name": "Unified Backend Project", "region": "Taiwan"},
        ).json()["project"]
        site = self.client.post(
            "/api/surveys/sites",
            json={
                "project_id": project["project_id"],
                "name": "Forest Plot",
                "latitude": 24.123,
                "longitude": 121.456,
            },
        ).json()["site"]

        asset_response = self.client.post(
            "/api/surveys/design-assets",
            json={
                "project_id": project["project_id"],
                "site_id": site["site_id"],
                "asset_type": "plot",
                "program": "plants",
                "protocol": "plant_quadrat",
                "name": "Quadrat A1",
                "geometry": {"type": "Point", "coordinates": [121.456, 24.123]},
            },
        )
        self.assertEqual(asset_response.status_code, 200)
        asset = asset_response.json()["design_asset"]

        event_response = self.client.post(
            "/api/surveys/events",
            json={
                "project_id": project["project_id"],
                "site_id": site["site_id"],
                "design_asset_id": asset["asset_id"],
                "program": "plants",
                "protocol": "plant_quadrat",
                "jurisdiction": "taiwan",
                "started_at": "2026-04-18T01:00:00Z",
                "ended_at": "2026-04-18T01:30:00Z",
                "observers": ["botanist-a"],
                "effort_metrics": {"plot_area_m2": 100},
            },
        )
        self.assertEqual(event_response.status_code, 200)
        event = event_response.json()["event"]
        self.assertEqual(event["design_asset_id"], asset["asset_id"])

        list_assets = self.client.get(
            f"/api/surveys/design-assets?project_id={project['project_id']}&program=plants"
        )
        self.assertEqual(list_assets.status_code, 200)
        self.assertEqual(list_assets.json()["total"], 1)

        list_events = self.client.get(
            f"/api/surveys/events?project_id={project['project_id']}&protocol=plant_quadrat"
        )
        self.assertEqual(list_events.status_code, 200)
        self.assertEqual(list_events.json()["total"], 1)

        export_response = self.client.post(
            "/api/surveys/exports/taiwan",
            json={
                "project_id": project["project_id"],
                "site_id": site["site_id"],
                "program": "plants",
                "protocol": "plant_quadrat",
            },
        )
        self.assertEqual(export_response.status_code, 200)
        export_payload = export_response.json()
        self.assertEqual(export_payload["export_job"]["jurisdiction"], "taiwan")
        self.assertEqual(export_payload["summary"]["design_asset_count"], 1)
        self.assertEqual(export_payload["summary"]["event_count"], 1)

    def test_taiwan_mammal_export_bundle_and_event_observation_filters_work(self):
        project = self.client.post(
            "/api/surveys/projects",
            json={"name": "Taiwan Mammal Export", "region": "Taiwan"},
        ).json()["project"]
        site = self.client.post(
            "/api/surveys/sites",
            json={
                "project_id": project["project_id"],
                "name": "Mountain Trap Site",
                "latitude": 24.123,
                "longitude": 121.456,
            },
        ).json()["site"]
        asset = self.client.post(
            "/api/surveys/design-assets",
            json={
                "project_id": project["project_id"],
                "site_id": site["site_id"],
                "asset_type": "trap_station",
                "program": "terrestrial_vertebrates",
                "protocol": "mammal_trap_net",
                "name": "Trap Station 01",
            },
        ).json()["design_asset"]
        event_response = self.client.post(
            "/api/surveys/events",
            json={
                "project_id": project["project_id"],
                "site_id": site["site_id"],
                "design_asset_id": asset["asset_id"],
                "program": "terrestrial_vertebrates",
                "protocol": "mammal_trap_net",
                "jurisdiction": "taiwan",
                "started_at": "2026-04-19T01:00:00Z",
                "ended_at": "2026-04-19T06:00:00Z",
                "observers": ["mammalogist-a"],
                "event_payload": {
                    "trap_method": "cage_trap",
                    "trap_station_count": 4,
                    "deployment_start_time": "2026-04-19T01:00:00Z",
                    "deployment_end_time": "2026-04-19T06:00:00Z",
                    "bait_type": "sweet_potato",
                    "observer_count": 1,
                    "trap_nights": 4,
                    "active_trap_count": 4,
                    "checked_station_count": 4,
                },
            },
        )
        self.assertEqual(event_response.status_code, 200)
        event = event_response.json()["event"]

        observation_response = self.client.post(
            "/api/surveys/observations",
            json={
                "project_id": project["project_id"],
                "site_id": site["site_id"],
                "event_id": event["event_id"],
                "program": "terrestrial_vertebrates",
                "protocol": "mammal_trap_net",
                "jurisdiction": "taiwan",
                "scientific_name": "Macaca cyclopis",
                "english_name": "Taiwan Macaque",
                "taxon_group": "mammals",
                "count": 1,
                "latitude": 24.123,
                "longitude": 121.456,
                "observed_at": "2026-04-19T03:30:00Z",
                "record_payload": {
                    "taxon_id": "vert-mammal-macaca-cyclopis",
                    "capture_status": "captured_alive",
                    "observation_time": "2026-04-19T03:30:00Z",
                    "trap_station_id": "trap-01",
                    "release_status": "released",
                    "sample_collected": False,
                    "protected_coordinate_policy": "mask",
                },
            },
        )
        self.assertEqual(observation_response.status_code, 200)

        filtered_events = self.client.get(
            f"/api/surveys/events?event_id={event['event_id']}&jurisdiction=taiwan&protocol=mammal_trap_net"
        )
        self.assertEqual(filtered_events.status_code, 200)
        self.assertEqual(filtered_events.json()["total"], 1)

        filtered_observations = self.client.get(
            f"/api/surveys/observations?event_id={event['event_id']}&jurisdiction=taiwan&protocol=mammal_trap_net&program=terrestrial_vertebrates"
        )
        self.assertEqual(filtered_observations.status_code, 200)
        self.assertEqual(filtered_observations.json()["total"], 1)

        export_response = self.client.post(
            "/api/surveys/exports/taiwan",
            json={
                "project_id": project["project_id"],
                "site_id": site["site_id"],
                "program": "terrestrial_vertebrates",
                "protocol": "mammal_trap_net",
                "event_id": event["event_id"],
            },
        )
        self.assertEqual(export_response.status_code, 200)
        export_payload = export_response.json()["export_job"]
        self.assertEqual(export_payload["summary"]["bundle_file_count"], 4)
        self.assertEqual(export_payload["summary"]["masked_observation_count"], 1)
        species_file = next(
            item
            for item in export_payload["bundle"]["files"]
            if item["output_id"] == "species_list"
        )
        self.assertEqual(
            species_file["filename"], "mammal_trap_net_species_list_tw.csv"
        )
        self.assertIn("Macaca cyclopis", species_file["content"])
        self.assertIn("True", species_file["content"])
        self.assertIn("record_coordinate_policy", species_file["content"])


if __name__ == "__main__":
    unittest.main()
