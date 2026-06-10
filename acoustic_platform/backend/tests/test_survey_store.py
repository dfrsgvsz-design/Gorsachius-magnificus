import sys
import tempfile
import unittest
import json
import sqlite3
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from survey_store import (
    SurveyStore,
    _load_vertebrate_export_profiles,
    _taxonomy_entry_for_observation,
)


class SurveyStoreTests(unittest.TestCase):
    def test_store_bootstraps_existing_pre_migration_observation_table(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "survey_store.db"
            conn = sqlite3.connect(db_path)
            conn.executescript("""
                CREATE TABLE survey_observations (
                    observation_id TEXT PRIMARY KEY,
                    project_id TEXT DEFAULT '',
                    site_id TEXT DEFAULT '',
                    route_id TEXT DEFAULT '',
                    scientific_name TEXT DEFAULT '',
                    chinese_name TEXT DEFAULT '',
                    english_name TEXT DEFAULT '',
                    taxon_group TEXT DEFAULT '',
                    observed_at TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX idx_survey_observations_project ON survey_observations(project_id);
                CREATE INDEX idx_survey_observations_site ON survey_observations(site_id);
                CREATE INDEX idx_survey_observations_route ON survey_observations(route_id);
                """)
            conn.execute(
                """
                INSERT INTO survey_observations (
                    observation_id, project_id, site_id, route_id, scientific_name, chinese_name,
                    english_name, taxon_group, observed_at, created_at, updated_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "obs_legacy",
                    "proj_legacy",
                    "site_legacy",
                    "route_legacy",
                    "Gorsachius magnificus",
                    "海南鳽",
                    "White-eared Night Heron",
                    "birds",
                    "2026-04-20T00:05:00Z",
                    "2026-04-20T00:05:00Z",
                    "2026-04-20T00:05:00Z",
                    json.dumps(
                        {
                            "observation_id": "obs_legacy",
                            "project_id": "proj_legacy",
                            "site_id": "site_legacy",
                            "route_id": "route_legacy",
                            "scientific_name": "Gorsachius magnificus",
                            "taxon_group": "birds",
                            "observed_at": "2026-04-20T00:05:00Z",
                            "snapped_route_id": "route_legacy",
                            "extra": {
                                "event_id": "event_legacy",
                                "program": "terrestrial_vertebrates",
                                "protocol": "bird_line_transect",
                                "jurisdiction": "mainland_china",
                            },
                            "record_payload": {
                                "taxon_id": "vert-bird-gorsachius-magnificus",
                            },
                        }
                    ),
                ),
            )
            conn.commit()
            conn.close()

            store = SurveyStore(storage_dir=temp_dir)
            try:
                migrated = store.list_observations(
                    project_id="proj_legacy", site_id="site_legacy"
                )
                self.assertEqual(len(migrated), 1)
                self.assertEqual(migrated[0]["event_id"], "event_legacy")
                self.assertEqual(migrated[0]["program"], "terrestrial_vertebrates")
                self.assertEqual(migrated[0]["protocol"], "bird_line_transect")
                self.assertEqual(migrated[0]["jurisdiction"], "mainland_china")
                self.assertEqual(
                    migrated[0]["taxon_id"], "vert-bird-gorsachius-magnificus"
                )
                self.assertEqual(migrated[0]["snapped_route_id"], "route_legacy")
            finally:
                store.close()

    def test_vertebrate_export_profiles_cover_pilot_protocols_for_both_jurisdictions(
        self,
    ):
        profiles = _load_vertebrate_export_profiles()
        required_outputs = set(profiles["required_bundle_outputs"])

        with tempfile.TemporaryDirectory() as temp_dir:
            store = SurveyStore(storage_dir=temp_dir)
            try:
                protocol_definitions = {
                    item["protocol"]: item
                    for item in store.list_protocol_definitions(
                        program="terrestrial_vertebrates"
                    )
                }
            finally:
                store.close()

        self.assertEqual(
            set(profiles["supported_jurisdictions"]),
            {"mainland_china", "taiwan"},
        )
        self.assertEqual(
            set(profiles["supported_protocols"]),
            set(protocol_definitions),
        )

        expected_confidence_protocols = {"bird_point_count", "herp_infrared_camera"}
        for jurisdiction in profiles["supported_jurisdictions"]:
            jurisdiction_profile = profiles["profiles"][jurisdiction]
            self.assertEqual(
                set(jurisdiction_profile["protocols"]),
                set(protocol_definitions),
            )
            for protocol, definition in protocol_definitions.items():
                with self.subTest(jurisdiction=jurisdiction, protocol=protocol):
                    profile = jurisdiction_profile["protocols"][protocol]
                    self.assertEqual(
                        set(profile["bundle_outputs"]),
                        required_outputs,
                    )

                    expected_record_fields = set(definition["record_payload_fields"])
                    actual_record_fields = set(
                        profile["record_payload_keys"]["required"]
                    ) | set(profile["record_payload_keys"]["optional"])
                    self.assertEqual(actual_record_fields, expected_record_fields)

                    expected_event_fields = set(definition["event_payload_fields"])
                    actual_event_fields = set(
                        profile["event_payload_keys"]["required"]
                    ) | set(profile["event_payload_keys"]["optional"])
                    self.assertEqual(actual_event_fields, expected_event_fields)

                    species_columns = {
                        column["column_id"]
                        for column in profile["bundle_outputs"]["species_list"][
                            "columns"
                        ]
                    }
                    self.assertEqual(
                        "confidence" in species_columns,
                        protocol in expected_confidence_protocols,
                    )

    def test_protocol_and_taxonomy_registries_filter_by_program_and_jurisdiction(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SurveyStore(storage_dir=temp_dir)
            try:
                vertebrate_protocols = store.list_protocol_definitions(
                    program="terrestrial_vertebrates"
                )
                self.assertEqual(
                    {item["protocol"] for item in vertebrate_protocols},
                    {
                        "bird_line_transect",
                        "bird_point_count",
                        "mammal_trap_net",
                        "herp_infrared_camera",
                    },
                )

                taiwan_plants = store.list_taxonomy_packages(
                    jurisdiction="taiwan",
                    program="plants",
                )
                self.assertEqual(len(taiwan_plants), 1)
                self.assertEqual(taiwan_plants[0]["package_id"], "tw-plants")
                self.assertEqual(
                    taiwan_plants[0]["languages"], ["zh-Hant", "en", "scientific"]
                )
                self.assertEqual(taiwan_plants[0]["asset_package_id"], "tw_plants_seed")
                self.assertTrue(taiwan_plants[0]["seed_only"])
                self.assertFalse(taiwan_plants[0]["exhaustive_species_content"])
                self.assertFalse(taiwan_plants[0]["exhaustive"])
                self.assertEqual(taiwan_plants[0]["catalog_status"], "seed_only")
                self.assertEqual(taiwan_plants[0]["local_seed_asset_count"], 1)
                self.assertEqual(taiwan_plants[0]["catalog_entry_count"], 2)
                self.assertEqual(taiwan_plants[0]["catalog_count"], 2)
            finally:
                store.close()

    def test_taxonomy_entry_lookup_respects_observation_program(self):
        taxonomy = _taxonomy_entry_for_observation(
            {
                "program": "plants",
                "protocol": "plant_quadrat",
                "scientific_name": "Gorsachius magnificus",
                "taxon_group": "trees",
                "record_payload": {
                    "taxon_id": "vert-bird-gorsachius-magnificus",
                },
            },
            "mainland_china",
        )
        self.assertEqual(taxonomy["group"], "trees")
        self.assertEqual(taxonomy["names"]["scientific"], "Gorsachius magnificus")
        self.assertEqual(taxonomy["status_flags"]["mainland_china"], {})

    def test_import_route_parses_geojson_and_exports_gpx(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SurveyStore(storage_dir=temp_dir)
            try:
                route = store.import_route(
                    project_id="proj_1",
                    site_id="site_1",
                    name="Transect North",
                    route_type="transect",
                    filename="transect.geojson",
                    content='{"type":"Feature","geometry":{"type":"LineString","coordinates":[[106.95,22.45],[106.951,22.451],[106.952,22.452]]},"properties":{}}',
                )
                exported = store.export_route(route["route_id"], "gpx")

                self.assertEqual(route["imported_format"], "geojson")
                self.assertGreater(route["length_m"], 0)
                self.assertIn("<gpx", exported["content"])
            finally:
                store.close()

    def test_sync_push_creates_conflict_when_base_timestamp_is_stale(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SurveyStore(storage_dir=temp_dir)
            try:
                project = store.upsert_project(
                    {"name": "Base Project", "region": "Guangxi"}
                )
                site = store.upsert_site(
                    {
                        "project_id": project["project_id"],
                        "name": "Forest Site",
                        "latitude": 22.45,
                        "longitude": 106.95,
                    }
                )
                event = store.upsert_event(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "program": "terrestrial_vertebrates",
                        "protocol": "bird_point_count",
                        "jurisdiction": "mainland_china",
                        "started_at": "2026-04-18T00:00:00Z",
                        "ended_at": "2026-04-18T00:10:00Z",
                        "observers": ["tester"],
                    }
                )

                original = store.upsert_observation(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "event_id": event["event_id"],
                        "program": "terrestrial_vertebrates",
                        "protocol": "bird_point_count",
                        "jurisdiction": "mainland_china",
                        "scientific_name": "Gorsachius magnificus",
                        "count": 1,
                        "latitude": 22.451,
                        "longitude": 106.951,
                    }
                )
                time.sleep(0.01)
                updated = store.upsert_observation(
                    {
                        **original,
                        "count": 2,
                    }
                )

                result = store.sync_push(
                    device_id="device-a",
                    user_id="tester",
                    operations=[
                        {
                            "entity_type": "observation",
                            "operation": "upsert",
                            "entity_id": original["observation_id"],
                            "payload": {
                                **original,
                                "count": 4,
                                "server_updated_at": original["updated_at"],
                            },
                        }
                    ],
                )

                self.assertEqual(result["conflict_count"], 1)
                self.assertEqual(result["status"], "conflict")
                self.assertEqual(
                    result["conflicts"][0]["entity_id"], updated["observation_id"]
                )
                self.assertIn("count", result["conflicts"][0]["fields"])
            finally:
                store.close()

    def test_sync_push_replayed_equivalent_observation_is_treated_as_no_op(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SurveyStore(storage_dir=temp_dir)
            try:
                project = store.upsert_project(
                    {"name": "Replay Project", "region": "Guangxi"}
                )
                site = store.upsert_site(
                    {
                        "project_id": project["project_id"],
                        "name": "Replay Site",
                        "latitude": 22.45,
                        "longitude": 106.95,
                    }
                )
                event = store.upsert_event(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "program": "terrestrial_vertebrates",
                        "protocol": "bird_point_count",
                        "jurisdiction": "mainland_china",
                        "started_at": "2026-04-18T00:00:00Z",
                        "ended_at": "2026-04-18T00:10:00Z",
                        "observers": ["tester"],
                    }
                )

                original = store.upsert_observation(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "event_id": event["event_id"],
                        "program": "terrestrial_vertebrates",
                        "protocol": "bird_point_count",
                        "jurisdiction": "mainland_china",
                        "scientific_name": "Gorsachius magnificus",
                        "count": 1,
                        "latitude": 22.451,
                        "longitude": 106.951,
                    }
                )
                time.sleep(0.01)
                updated = store.upsert_observation(
                    {
                        **original,
                        "count": 2,
                    }
                )

                result = store.sync_push(
                    device_id="device-a",
                    user_id="tester",
                    operations=[
                        {
                            "entity_type": "observation",
                            "operation": "upsert",
                            "entity_id": updated["observation_id"],
                            "payload": {
                                **updated,
                                "server_updated_at": original["updated_at"],
                            },
                        }
                    ],
                )

                reloaded = store.list_observations(
                    project_id=project["project_id"], site_id=site["site_id"]
                )[0]
                self.assertEqual(result["conflict_count"], 0)
                self.assertEqual(result["status"], "applied")
                self.assertEqual(result["applied_count"], 1)
                self.assertEqual(
                    result["applied"][0]["record"]["updated_at"], updated["updated_at"]
                )
                self.assertEqual(reloaded["count"], 2)
                self.assertEqual(reloaded["updated_at"], updated["updated_at"])
            finally:
                store.close()

    def test_partial_upsert_preserves_existing_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SurveyStore(storage_dir=temp_dir)
            try:
                project = store.upsert_project(
                    {
                        "name": "Original Project",
                        "region": "Guangxi",
                        "notes": "keep me",
                        "target_taxa": ["birds"],
                    }
                )
                updated_project = store._apply_entity_upsert_locked(
                    "project",
                    {
                        "project_id": project["project_id"],
                        "name": "Renamed Project",
                    },
                )
                self.assertEqual(updated_project["name"], "Renamed Project")
                self.assertEqual(updated_project["region"], "Guangxi")
                self.assertEqual(updated_project["notes"], "keep me")
                self.assertEqual(updated_project["target_taxa"], ["birds"])

                site = store.upsert_site(
                    {
                        "project_id": project["project_id"],
                        "name": "Forest Site",
                        "latitude": 22.45,
                        "longitude": 106.95,
                    }
                )
                event = store.upsert_event(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "program": "terrestrial_vertebrates",
                        "protocol": "bird_point_count",
                        "jurisdiction": "mainland_china",
                        "started_at": "2026-04-18T00:00:00Z",
                        "ended_at": "2026-04-18T00:10:00Z",
                        "observers": ["tester"],
                    }
                )
                observation = store.upsert_observation(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "event_id": event["event_id"],
                        "program": "terrestrial_vertebrates",
                        "protocol": "bird_point_count",
                        "jurisdiction": "mainland_china",
                        "scientific_name": "Gorsachius magnificus",
                        "count": 1,
                        "observer": "tester",
                        "observed_at": "2026-04-18T00:05:00Z",
                        "notes": "baseline",
                        "latitude": 22.451,
                        "longitude": 106.951,
                    }
                )
                updated_observation = store._apply_entity_upsert_locked(
                    "observation",
                    {
                        "observation_id": observation["observation_id"],
                        "count": 3,
                    },
                )
                self.assertEqual(updated_observation["count"], 3)
                self.assertEqual(
                    updated_observation["project_id"], project["project_id"]
                )
                self.assertEqual(updated_observation["site_id"], site["site_id"])
                self.assertEqual(updated_observation["observer"], "tester")
                self.assertEqual(
                    updated_observation["observed_at"], "2026-04-18T00:05:00Z"
                )
            finally:
                store.close()

    def test_delete_site_cascades_related_entities(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SurveyStore(storage_dir=temp_dir)
            try:
                project = store.upsert_project(
                    {"name": "Cascade Project", "region": "Guangxi"}
                )
                site = store.upsert_site(
                    {
                        "project_id": project["project_id"],
                        "name": "Cascade Site",
                        "latitude": 22.45,
                        "longitude": 106.95,
                    }
                )
                route = store.upsert_route(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "name": "Cascade Route",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[106.95, 22.45], [106.951, 22.451]],
                        },
                    }
                )
                event = store.upsert_event(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": route["route_id"],
                        "protocol": "bird_line_transect",
                        "program": "terrestrial_vertebrates",
                        "jurisdiction": "mainland_china",
                        "started_at": "2026-04-18T00:00:00Z",
                        "ended_at": "2026-04-18T00:10:00Z",
                    }
                )
                store.upsert_observation(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": route["route_id"],
                        "event_id": event["event_id"],
                        "scientific_name": "Gorsachius magnificus",
                        "count": 1,
                        "latitude": 22.451,
                        "longitude": 106.951,
                    }
                )
                store.upsert_track(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": route["route_id"],
                        "event_id": event["event_id"],
                        "name": "Cascade Track",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[106.95, 22.45], [106.951, 22.451]],
                        },
                    }
                )

                self.assertTrue(store.delete_entity("site", site["site_id"]))
                self.assertEqual(store.list_sites(project_id=project["project_id"]), [])
                self.assertEqual(
                    store.list_routes(project_id=project["project_id"]), []
                )
                self.assertEqual(
                    store.list_events(project_id=project["project_id"]), []
                )
                self.assertEqual(
                    store.list_observations(project_id=project["project_id"]), []
                )
                self.assertEqual(
                    store.list_tracks(project_id=project["project_id"]), []
                )
            finally:
                store.close()

    def test_route_summary_and_report_export_include_snapped_observations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SurveyStore(storage_dir=temp_dir)
            try:
                project = store.upsert_project(
                    {"name": "Transect Project", "region": "Guangxi"}
                )
                site = store.upsert_site(
                    {
                        "project_id": project["project_id"],
                        "name": "Forest Ridge",
                        "latitude": 22.45,
                        "longitude": 106.95,
                    }
                )
                route = store.upsert_route(
                    {
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
                        "length_m": 300.5,
                    }
                )
                other_route = store.upsert_route(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "name": "Transect B",
                        "route_type": "transect",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[106.96, 22.46], [106.961, 22.461]],
                        },
                    }
                )
                event = store.upsert_event(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": route["route_id"],
                        "program": "terrestrial_vertebrates",
                        "protocol": "bird_line_transect",
                        "jurisdiction": "mainland_china",
                        "started_at": "2026-04-18T00:00:00Z",
                        "ended_at": "2026-04-18T00:15:00Z",
                        "observers": ["Observer A"],
                    }
                )
                other_event = store.upsert_event(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": other_route["route_id"],
                        "program": "terrestrial_vertebrates",
                        "protocol": "bird_line_transect",
                        "jurisdiction": "mainland_china",
                        "started_at": "2026-04-18T00:20:00Z",
                        "ended_at": "2026-04-18T00:25:00Z",
                        "observers": ["Observer C"],
                    }
                )

                store.upsert_observation(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": route["route_id"],
                        "event_id": event["event_id"],
                        "scientific_name": "Gorsachius magnificus",
                        "chinese_name": "海南鳽",
                        "english_name": "White-eared Night Heron",
                        "taxon_group": "birds",
                        "count": 2,
                        "observer": "Observer A",
                        "observed_at": "2026-04-18T00:05:00Z",
                        "extra": {
                            "weather": {
                                "conditions": "Mist",
                                "temperature_c": 19,
                            }
                        },
                    }
                )
                store.upsert_observation(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "snapped_route_id": route["route_id"],
                        "event_id": event["event_id"],
                        "scientific_name": "Lophura nycthemera",
                        "chinese_name": "白鹇",
                        "english_name": "Silver Pheasant",
                        "taxon_group": "birds",
                        "count": 1,
                        "observer": "Observer B",
                        "observed_at": "2026-04-18T00:09:00Z",
                        "extra": {
                            "weather": {
                                "conditions": "Cloudy",
                                "humidity_pct": 92,
                            }
                        },
                    }
                )
                store.upsert_observation(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": other_route["route_id"],
                        "event_id": other_event["event_id"],
                        "scientific_name": "Ignored species",
                        "count": 7,
                        "observer": "Observer C",
                    }
                )
                store.upsert_track(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": route["route_id"],
                        "event_id": event["event_id"],
                        "name": "Morning Walk",
                        "distance_m": 285.4,
                        "duration_s": 900,
                        "started_at": "2026-04-18T00:00:00Z",
                        "ended_at": "2026-04-18T00:15:00Z",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [
                                [106.95, 22.45],
                                [106.951, 22.451],
                                [106.952, 22.452],
                            ],
                        },
                        "extra": {
                            "observer": "Observer A",
                            "weather": {
                                "wind": "Light breeze",
                                "temperature_c": 20,
                            },
                        },
                    }
                )

                summary = store.get_route_summary(route["route_id"])
                self.assertEqual(summary["route"]["route_id"], route["route_id"])
                self.assertEqual(summary["totals"]["observation_count"], 2)
                self.assertEqual(summary["totals"]["individual_count"], 3)
                self.assertEqual(summary["totals"]["unique_species_count"], 2)
                self.assertEqual(summary["totals"]["track_count"], 1)
                self.assertEqual(summary["totals"]["planned_distance_m"], 300.5)
                self.assertEqual(summary["totals"]["walked_distance_m"], 285.4)
                self.assertEqual(summary["totals"]["effort_minutes"], 15.0)
                self.assertEqual(
                    [item["scientific_name"] for item in summary["species"]],
                    ["Gorsachius magnificus", "Lophura nycthemera"],
                )
                self.assertEqual(
                    [item["name"] for item in summary["observers"]],
                    ["Observer A", "Observer B"],
                )
                self.assertEqual(summary["weather"]["samples"], 3)
                self.assertEqual(summary["weather"]["temperature_c"]["avg"], 19.5)
                self.assertIn("Cloudy", summary["weather"]["conditions"])
                self.assertIn("Mist", summary["weather"]["conditions"])

                exported_json = store.export_route_report(route["route_id"], "json")
                exported_payload = json.loads(exported_json["content"])
                self.assertEqual(exported_json["media_type"], "application/json")
                self.assertEqual(
                    exported_payload["summary"]["totals"]["individual_count"], 3
                )

                exported_csv = store.export_route_report(route["route_id"], "csv")
                self.assertEqual(exported_csv["media_type"], "text/csv")
                self.assertIn(
                    "scientific_name,chinese_name,english_name", exported_csv["content"]
                )
                self.assertIn("Gorsachius magnificus", exported_csv["content"])
                self.assertIn("Lophura nycthemera", exported_csv["content"])
            finally:
                store.close()

    def test_design_assets_events_and_export_jobs_share_one_backend_core(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SurveyStore(storage_dir=temp_dir)
            try:
                project = store.upsert_project(
                    {"name": "Unified Core Project", "region": "Taiwan"}
                )
                site = store.upsert_site(
                    {
                        "project_id": project["project_id"],
                        "name": "Wetland Plot",
                        "latitude": 24.123,
                        "longitude": 121.456,
                    }
                )
                asset = store.upsert_design_asset(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "asset_type": "camera_station",
                        "protocol": "herp_infrared_camera",
                        "name": "Camera Station 01",
                        "geometry": {"type": "Point", "coordinates": [121.456, 24.123]},
                    }
                )
                event = store.upsert_event(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "design_asset_id": asset["asset_id"],
                        "protocol": "herp_infrared_camera",
                        "jurisdiction": "taiwan",
                        "started_at": "2026-04-18T00:00:00Z",
                        "ended_at": "2026-04-18T06:00:00Z",
                        "observers": ["observer-a"],
                        "event_payload": {"deployment_mode": "infrared_camera"},
                    }
                )
                observation = store.upsert_observation(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "event_id": event["event_id"],
                        "program": "terrestrial_vertebrates",
                        "protocol": "herp_infrared_camera",
                        "jurisdiction": "taiwan",
                        "scientific_name": "Fejervarya limnocharis",
                        "count": 1,
                        "observed_at": "2026-04-18T02:00:00Z",
                        "latitude": 24.123,
                        "longitude": 121.456,
                        "extra": {
                            "event_id": event["event_id"],
                            "program": "terrestrial_vertebrates",
                            "protocol": "herp_infrared_camera",
                        },
                    }
                )

                export_job = store.create_export_job(
                    "taiwan",
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "program": "terrestrial_vertebrates",
                        "protocol": "herp_infrared_camera",
                    },
                )
                pull_payload = store.sync_pull()

                self.assertEqual(asset["program"], "terrestrial_vertebrates")
                self.assertEqual(event["program"], "terrestrial_vertebrates")
                self.assertEqual(event["design_asset_id"], asset["asset_id"])
                self.assertEqual(export_job["jurisdiction"], "taiwan")
                self.assertEqual(export_job["summary"]["design_asset_count"], 1)
                self.assertEqual(export_job["summary"]["event_count"], 1)
                self.assertEqual(export_job["summary"]["observation_count"], 1)
                self.assertEqual(
                    export_job["bundle"]["observations"][0]["observation_id"],
                    observation["observation_id"],
                )
                self.assertEqual(len(pull_payload["design_assets"]), 1)
                self.assertEqual(len(pull_payload["events"]), 1)
                self.assertEqual(len(pull_payload["export_jobs"]), 1)
            finally:
                store.close()

    def test_mainland_bird_export_bundle_uses_profile_files_and_masks_sensitive_coordinates(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SurveyStore(storage_dir=temp_dir)
            try:
                project = store.upsert_project(
                    {"name": "Bird Export Project", "region": "Guangxi"}
                )
                site = store.upsert_site(
                    {
                        "project_id": project["project_id"],
                        "name": "Forest Transect",
                        "latitude": 22.45,
                        "longitude": 106.95,
                    }
                )
                asset = store.upsert_design_asset(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "asset_type": "route",
                        "program": "terrestrial_vertebrates",
                        "protocol": "bird_line_transect",
                        "name": "Transect 1",
                    }
                )
                event = store.upsert_event(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "design_asset_id": asset["asset_id"],
                        "program": "terrestrial_vertebrates",
                        "protocol": "bird_line_transect",
                        "jurisdiction": "mainland_china",
                        "started_at": "2026-04-19T00:00:00Z",
                        "ended_at": "2026-04-19T00:30:00Z",
                        "weather": {"conditions": "cloudy"},
                        "effort_metrics": {
                            "distance_walked_m": 500,
                            "duration_min": 30,
                        },
                        "event_payload": {
                            "transect_name": "Transect 1",
                            "transect_length_m": 500,
                            "survey_round": 1,
                            "observer_count": 2,
                            "weather": "cloudy",
                            "distance_walked_m": 500,
                            "duration_min": 30,
                        },
                        "observers": ["observer-a", "observer-b"],
                    }
                )
                store.upsert_observation(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "event_id": event["event_id"],
                        "program": "terrestrial_vertebrates",
                        "protocol": "bird_line_transect",
                        "jurisdiction": "mainland_china",
                        "scientific_name": "Gorsachius magnificus",
                        "english_name": "White-eared Night Heron",
                        "taxon_group": "birds",
                        "count": 1,
                        "latitude": 22.451,
                        "longitude": 106.951,
                        "observed_at": "2026-04-19T00:05:00Z",
                        "record_payload": {
                            "taxon_id": "vert-bird-gorsachius-magnificus",
                            "detection_type": "visual",
                            "count": 1,
                            "observation_time": "2026-04-19T00:05:00Z",
                            "route_segment_id": "segment-a",
                        },
                        "extra": {
                            "taxonomy_status_flags": {
                                "mainland_china": {
                                    "is_sensitive": True,
                                    "protection_level": "Class I",
                                }
                            }
                        },
                    }
                )

                export_job = store.create_export_job(
                    "mainland_china",
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "program": "terrestrial_vertebrates",
                        "protocol": "bird_line_transect",
                        "event_id": event["event_id"],
                    },
                )

                self.assertEqual(export_job["summary"]["bundle_file_count"], 4)
                self.assertEqual(export_job["summary"]["masked_observation_count"], 1)
                self.assertEqual(
                    export_job["bundle"]["manifest"]["bundle_outputs"],
                    [
                        "event_summary",
                        "species_list",
                        "effort_summary",
                        "station_or_route_summary",
                    ],
                )
                species_file = next(
                    item
                    for item in export_job["bundle"]["files"]
                    if item["output_id"] == "species_list"
                )
                self.assertEqual(
                    species_file["filename"], "bird_line_transect_species_list_cn.csv"
                )
                self.assertIn("Gorsachius magnificus", species_file["content"])
                self.assertIn("Class I", species_file["content"])
                self.assertIn("True", species_file["content"])
                self.assertIn("taxonomy_status_flags", species_file["content"])
            finally:
                store.close()

    def test_event_filtered_export_excludes_unlinked_tracks_and_exports_track_metadata(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SurveyStore(storage_dir=temp_dir)
            try:
                project = store.upsert_project(
                    {"name": "Track Export Project", "region": "Taiwan"}
                )
                site = store.upsert_site(
                    {
                        "project_id": project["project_id"],
                        "name": "Track Export Site",
                        "latitude": 24.123,
                        "longitude": 121.456,
                    }
                )
                event = store.upsert_event(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "program": "plants",
                        "protocol": "plant_transect",
                        "jurisdiction": "taiwan",
                        "started_at": "2026-04-18T01:00:00Z",
                        "ended_at": "2026-04-18T01:30:00Z",
                    }
                )
                secondary_event = store.upsert_event(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "program": "plants",
                        "protocol": "plant_transect",
                        "jurisdiction": "taiwan",
                        "started_at": "2026-04-18T02:00:00Z",
                        "ended_at": "2026-04-18T02:20:00Z",
                    }
                )
                store.upsert_track(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "event_id": event["event_id"],
                        "name": "Linked Track",
                        "observer": "botanist-a",
                        "weather": {"conditions": "cloudy"},
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[121.456, 24.123], [121.457, 24.124]],
                        },
                    }
                )
                store.upsert_track(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "event_id": secondary_event["event_id"],
                        "name": "Unlinked Track",
                        "observer": "botanist-b",
                        "weather": {"conditions": "sunny"},
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[121.458, 24.125], [121.459, 24.126]],
                        },
                    }
                )

                export_job = store.create_export_job(
                    "taiwan",
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "program": "plants",
                        "protocol": "plant_transect",
                        "event_id": event["event_id"],
                    },
                )
                self.assertEqual(export_job["summary"]["track_count"], 1)
                track_logs = next(
                    item
                    for item in export_job["bundle"]["files"]
                    if item["output_id"] == "track_logs"
                )
                self.assertIn("Linked Track", track_logs["content"])
                self.assertNotIn("Unlinked Track", track_logs["content"])
                self.assertIn("botanist-a", track_logs["content"])
                self.assertIn("cloudy", track_logs["content"])
            finally:
                store.close()

    def test_bird_point_count_exports_confidence_for_mainland_and_taiwan_profiles(self):
        for jurisdiction in ("mainland_china", "taiwan"):
            with self.subTest(jurisdiction=jurisdiction):
                with tempfile.TemporaryDirectory() as temp_dir:
                    store = SurveyStore(storage_dir=temp_dir)
                    try:
                        project = store.upsert_project(
                            {
                                "name": f"Point Count {jurisdiction}",
                                "region": jurisdiction,
                            }
                        )
                        site = store.upsert_site(
                            {
                                "project_id": project["project_id"],
                                "name": "Point Count Site",
                                "latitude": 24.123,
                                "longitude": 121.456,
                            }
                        )
                        asset = store.upsert_design_asset(
                            {
                                "project_id": project["project_id"],
                                "site_id": site["site_id"],
                                "asset_type": "plot",
                                "program": "terrestrial_vertebrates",
                                "protocol": "bird_point_count",
                                "name": "Point A",
                            }
                        )
                        event = store.upsert_event(
                            {
                                "project_id": project["project_id"],
                                "site_id": site["site_id"],
                                "design_asset_id": asset["asset_id"],
                                "program": "terrestrial_vertebrates",
                                "protocol": "bird_point_count",
                                "jurisdiction": jurisdiction,
                                "started_at": "2026-04-20T00:00:00Z",
                                "ended_at": "2026-04-20T00:10:00Z",
                                "weather": {"conditions": "clear"},
                                "effort_metrics": {
                                    "point_duration_min": 10,
                                    "point_radius_m": 50,
                                    "station_count": 4,
                                    "travel_distance_m": 120,
                                },
                                "event_payload": {
                                    "point_id": "P-01",
                                    "point_visit_index": 2,
                                },
                                "observers": ["observer-a"],
                            }
                        )
                        observation = store.upsert_observation(
                            {
                                "project_id": project["project_id"],
                                "site_id": site["site_id"],
                                "event_id": event["event_id"],
                                "program": "terrestrial_vertebrates",
                                "protocol": "bird_point_count",
                                "jurisdiction": jurisdiction,
                                "scientific_name": "Gorsachius magnificus",
                                "english_name": "White-eared Night Heron",
                                "taxon_group": "birds",
                                "count": 2,
                                "latitude": 24.124,
                                "longitude": 121.457,
                                "observed_at": "2026-04-20T00:04:00Z",
                                "record_payload": {
                                    "taxon_id": "vert-bird-gorsachius-magnificus",
                                    "detection_type": "audio",
                                    "count": 2,
                                    "observation_time": "2026-04-20T00:04:00Z",
                                    "point_id": "P-01",
                                    "confidence": 0.87,
                                },
                            }
                        )

                        export_job = store.create_export_job(
                            jurisdiction,
                            {
                                "project_id": project["project_id"],
                                "site_id": site["site_id"],
                                "program": "terrestrial_vertebrates",
                                "protocol": "bird_point_count",
                                "event_id": event["event_id"],
                            },
                        )

                        self.assertEqual(
                            observation["record_payload"]["confidence"], 0.87
                        )
                        self.assertEqual(export_job["summary"]["bundle_file_count"], 4)
                        self.assertEqual(
                            export_job["bundle"]["manifest"]["bundle_outputs"],
                            [
                                "event_summary",
                                "species_list",
                                "effort_summary",
                                "station_or_route_summary",
                            ],
                        )
                        species_file = next(
                            item
                            for item in export_job["bundle"]["files"]
                            if item["output_id"] == "species_list"
                        )
                        self.assertIn("confidence", species_file["columns"])
                        self.assertIn("P-01", species_file["content"])
                        self.assertIn("0.87", species_file["content"])
                    finally:
                        store.close()

    def test_plant_transect_exports_generic_bundle_files_for_mainland(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SurveyStore(storage_dir=temp_dir)
            try:
                project = store.upsert_project(
                    {"name": "Plant Export Project", "region": "Guangxi"}
                )
                site = store.upsert_site(
                    {
                        "project_id": project["project_id"],
                        "name": "Plant Plot",
                        "latitude": 22.45,
                        "longitude": 106.95,
                    }
                )
                route = store.upsert_route(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "name": "Vegetation Transect",
                        "route_type": "transect",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[106.95, 22.45], [106.951, 22.451]],
                        },
                    }
                )
                event = store.upsert_event(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": route["route_id"],
                        "program": "plants",
                        "protocol": "plant_transect",
                        "jurisdiction": "mainland_china",
                        "started_at": "2026-04-21T00:00:00Z",
                        "ended_at": "2026-04-21T00:25:00Z",
                        "observers": ["botanist-a"],
                        "effort_metrics": {
                            "distance_walked_m": 100,
                            "duration_min": 25,
                        },
                        "event_payload": {
                            "segment_length_m": 100,
                            "transect_width_m": 5,
                        },
                    }
                )
                store.upsert_observation(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": route["route_id"],
                        "event_id": event["event_id"],
                        "program": "plants",
                        "protocol": "plant_transect",
                        "jurisdiction": "mainland_china",
                        "scientific_name": "Castanopsis fabri",
                        "chinese_name": "栲树",
                        "taxon_group": "plants",
                        "count": 3,
                        "observed_at": "2026-04-21T00:10:00Z",
                        "record_payload": {"cover_percent": 40, "height_cm": 120},
                    }
                )
                store.upsert_track(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": route["route_id"],
                        "event_id": event["event_id"],
                        "name": "Plant Walk",
                        "started_at": "2026-04-21T00:00:00Z",
                        "ended_at": "2026-04-21T00:25:00Z",
                        "distance_m": 100,
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[106.95, 22.45], [106.951, 22.451]],
                        },
                    }
                )

                export_job = store.create_export_job(
                    "mainland_china",
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "program": "plants",
                        "protocol": "plant_transect",
                        "event_id": event["event_id"],
                        "route_id": route["route_id"],
                    },
                )

                self.assertEqual(export_job["summary"]["taxonomy_package_count"], 1)
                self.assertGreaterEqual(export_job["summary"]["bundle_file_count"], 5)
                self.assertEqual(
                    export_job["bundle"]["manifest"]["bundle_outputs"][:4],
                    [
                        "bundle_manifest",
                        "sampling_events",
                        "species_records",
                        "species_list",
                    ],
                )
                exported_filenames = {
                    item["filename"] for item in export_job["bundle"]["files"]
                }
                self.assertIn("sampling_events.csv", exported_filenames)
                self.assertIn("species_records.csv", exported_filenames)
                self.assertIn("species_list.csv", exported_filenames)
                self.assertIn("route_or_station_summary.csv", exported_filenames)
                bundle_manifest = next(
                    item
                    for item in export_job["bundle"]["files"]
                    if item["filename"] == "bundle_manifest.json"
                )
                bundle_manifest_payload = json.loads(bundle_manifest["content"])
                self.assertEqual(
                    bundle_manifest_payload["taxonomy_packages"][0][
                        "taxonomy_release_id"
                    ],
                    "taxonomy_seed_release_2026_04_23",
                )
                self.assertIn(
                    "checksum", bundle_manifest_payload["taxonomy_packages"][0]
                )
                self.assertIn(
                    "review_status", bundle_manifest_payload["taxonomy_packages"][0]
                )
                species_records = next(
                    item
                    for item in export_job["bundle"]["files"]
                    if item["filename"] == "species_records.csv"
                )
                self.assertIn("Castanopsis fabri", species_records["content"])
            finally:
                store.close()

    def test_insect_transect_export_filters_to_selected_taiwan_route(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SurveyStore(storage_dir=temp_dir)
            try:
                project = store.upsert_project(
                    {"name": "Insect Export Project", "region": "Taiwan"}
                )
                site = store.upsert_site(
                    {
                        "project_id": project["project_id"],
                        "name": "Insect Site",
                        "latitude": 24.123,
                        "longitude": 121.456,
                    }
                )
                primary_route = store.upsert_route(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "name": "Butterfly Transect",
                        "route_type": "transect",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[121.456, 24.123], [121.457, 24.124]],
                        },
                    }
                )
                secondary_route = store.upsert_route(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "name": "Moth Transect",
                        "route_type": "transect",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[121.458, 24.125], [121.459, 24.126]],
                        },
                    }
                )
                primary_event = store.upsert_event(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": primary_route["route_id"],
                        "program": "insects",
                        "protocol": "insect_transect",
                        "jurisdiction": "taiwan",
                        "started_at": "2026-04-22T00:00:00Z",
                        "ended_at": "2026-04-22T00:20:00Z",
                        "observers": ["entomologist-a"],
                        "event_payload": {"transect_width_m": 5},
                    }
                )
                secondary_event = store.upsert_event(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": secondary_route["route_id"],
                        "program": "insects",
                        "protocol": "insect_transect",
                        "jurisdiction": "taiwan",
                        "started_at": "2026-04-22T01:00:00Z",
                        "ended_at": "2026-04-22T01:20:00Z",
                        "observers": ["entomologist-b"],
                        "event_payload": {"transect_width_m": 5},
                    }
                )
                store.upsert_observation(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": primary_route["route_id"],
                        "event_id": primary_event["event_id"],
                        "program": "insects",
                        "protocol": "insect_transect",
                        "jurisdiction": "taiwan",
                        "scientific_name": "Papilio bianor",
                        "taxon_group": "insects",
                        "count": 4,
                        "observed_at": "2026-04-22T00:08:00Z",
                    }
                )
                store.upsert_observation(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": secondary_route["route_id"],
                        "event_id": secondary_event["event_id"],
                        "program": "insects",
                        "protocol": "insect_transect",
                        "jurisdiction": "taiwan",
                        "scientific_name": "Actias ningpoana",
                        "taxon_group": "insects",
                        "count": 2,
                        "observed_at": "2026-04-22T01:08:00Z",
                    }
                )

                export_job = store.create_export_job(
                    "taiwan",
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "program": "insects",
                        "protocol": "insect_transect",
                        "route_id": primary_route["route_id"],
                    },
                )

                self.assertEqual(
                    export_job["summary"]["route_id"], primary_route["route_id"]
                )
                self.assertEqual(export_job["summary"]["taxonomy_package_count"], 1)
                self.assertEqual(export_job["summary"]["observation_count"], 1)
                species_records = next(
                    item
                    for item in export_job["bundle"]["files"]
                    if item["filename"] == "species_records.csv"
                )
                self.assertIn("Papilio bianor", species_records["content"])
                self.assertNotIn("Actias ningpoana", species_records["content"])
            finally:
                store.close()

    def test_direct_upserts_preserve_existing_values_for_omitted_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SurveyStore(storage_dir=temp_dir)
            try:
                project = store.upsert_project(
                    {
                        "name": "Integrity Project",
                        "region": "Guangxi",
                        "team_members": ["alice"],
                        "target_taxa": ["birds"],
                        "survey_window": {"start": "2026-04-01", "end": "2026-04-30"},
                        "notes": "baseline",
                    }
                )
                site = store.upsert_site(
                    {
                        "project_id": project["project_id"],
                        "name": "Forest Site",
                        "latitude": 22.45,
                        "longitude": 106.95,
                        "habitat_type": "evergreen forest",
                        "notes": "site notes",
                    }
                )
                route = store.upsert_route(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "name": "Transect A",
                        "route_type": "transect",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[106.95, 22.45], [106.951, 22.451]],
                        },
                        "point_times": ["2026-04-18T00:00:00Z"],
                    }
                )
                asset = store.upsert_design_asset(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": route["route_id"],
                        "asset_type": "plot",
                        "program": "plants",
                        "protocol": "plant_transect",
                        "name": "Plot A",
                        "notes": "asset notes",
                    }
                )
                event = store.upsert_event(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": route["route_id"],
                        "design_asset_id": asset["asset_id"],
                        "program": "plants",
                        "protocol": "plant_transect",
                        "jurisdiction": "mainland_china",
                        "started_at": "2026-04-18T00:00:00Z",
                        "ended_at": "2026-04-18T00:20:00Z",
                        "weather": {"conditions": "Mist"},
                        "effort_metrics": {"distance_walked_m": 100},
                        "observers": ["observer-a"],
                        "notes": "event notes",
                    }
                )
                observation = store.upsert_observation(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": route["route_id"],
                        "event_id": event["event_id"],
                        "program": "plants",
                        "protocol": "plant_transect",
                        "jurisdiction": "mainland_china",
                        "scientific_name": "Castanopsis fabri",
                        "taxon_group": "plants",
                        "count": 2,
                        "observer": "observer-a",
                        "observed_at": "2026-04-18T00:05:00Z",
                        "extra": {"weather": {"conditions": "Mist"}},
                    }
                )
                track = store.upsert_track(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": route["route_id"],
                        "event_id": event["event_id"],
                        "name": "Walk 1",
                        "started_at": "2026-04-18T00:00:00Z",
                        "ended_at": "2026-04-18T00:20:00Z",
                        "extra": {
                            "observer": "observer-a",
                            "weather": {"wind": "Light breeze"},
                        },
                    }
                )

                updated_project = store.upsert_project(
                    {"project_id": project["project_id"], "region": "Yunnan"}
                )
                updated_site = store.upsert_site(
                    {"site_id": site["site_id"], "notes": "updated site notes"}
                )
                updated_route = store.upsert_route(
                    {"route_id": route["route_id"], "source": "synced"}
                )
                updated_asset = store.upsert_design_asset(
                    {"asset_id": asset["asset_id"], "status": "inactive"}
                )
                updated_event = store.upsert_event(
                    {"event_id": event["event_id"], "notes": "updated event notes"}
                )
                updated_observation = store.upsert_observation(
                    {
                        "observation_id": observation["observation_id"],
                        "extra": {"review": "done"},
                    }
                )
                updated_track = store.upsert_track(
                    {"track_id": track["track_id"], "duration_s": 1200}
                )

                self.assertEqual(updated_project["name"], "Integrity Project")
                self.assertEqual(updated_project["team_members"], ["alice"])
                self.assertEqual(updated_project["region"], "Yunnan")

                self.assertEqual(updated_site["project_id"], project["project_id"])
                self.assertEqual(updated_site["habitat_type"], "evergreen forest")
                self.assertEqual(updated_site["notes"], "updated site notes")

                self.assertEqual(updated_route["project_id"], project["project_id"])
                self.assertEqual(updated_route["site_id"], site["site_id"])
                self.assertEqual(updated_route["point_times"], ["2026-04-18T00:00:00Z"])
                self.assertEqual(updated_route["source"], "synced")

                self.assertEqual(updated_asset["route_id"], route["route_id"])
                self.assertEqual(updated_asset["name"], "Plot A")
                self.assertEqual(updated_asset["status"], "inactive")

                self.assertEqual(updated_event["design_asset_id"], asset["asset_id"])
                self.assertEqual(updated_event["route_id"], route["route_id"])
                self.assertEqual(updated_event["weather"], {"conditions": "Mist"})
                self.assertEqual(
                    updated_event["effort_metrics"], {"distance_walked_m": 100}
                )
                self.assertEqual(updated_event["notes"], "updated event notes")

                self.assertEqual(
                    updated_observation["scientific_name"], "Castanopsis fabri"
                )
                self.assertEqual(updated_observation["count"], 2)
                self.assertEqual(updated_observation["event_id"], event["event_id"])
                self.assertEqual(
                    updated_observation["extra"]["weather"], {"conditions": "Mist"}
                )
                self.assertEqual(updated_observation["extra"]["review"], "done")

                self.assertEqual(updated_track["route_id"], route["route_id"])
                self.assertEqual(updated_track["extra"]["event_id"], event["event_id"])
                self.assertEqual(updated_track["extra"]["observer"], "observer-a")
                self.assertEqual(
                    updated_track["extra"]["weather"], {"wind": "Light breeze"}
                )
                self.assertEqual(updated_track["duration_s"], 1200)
            finally:
                store.close()

    def test_delete_entity_cascades_related_survey_data(self):
        def build_fixture(store: SurveyStore) -> dict:
            project = store.upsert_project(
                {"name": "Cascade Project", "region": "Guangxi"}
            )
            site = store.upsert_site(
                {
                    "project_id": project["project_id"],
                    "name": "Cascade Site",
                    "latitude": 22.45,
                    "longitude": 106.95,
                }
            )
            route = store.upsert_route(
                {
                    "project_id": project["project_id"],
                    "site_id": site["site_id"],
                    "name": "Cascade Route",
                    "route_type": "transect",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[106.95, 22.45], [106.951, 22.451]],
                    },
                }
            )
            asset = store.upsert_design_asset(
                {
                    "project_id": project["project_id"],
                    "site_id": site["site_id"],
                    "route_id": route["route_id"],
                    "asset_type": "plot",
                    "program": "plants",
                    "protocol": "plant_transect",
                    "name": "Cascade Plot",
                }
            )
            event = store.upsert_event(
                {
                    "project_id": project["project_id"],
                    "site_id": site["site_id"],
                    "route_id": route["route_id"],
                    "design_asset_id": asset["asset_id"],
                    "program": "plants",
                    "protocol": "plant_transect",
                    "jurisdiction": "mainland_china",
                    "started_at": "2026-04-18T00:00:00Z",
                    "ended_at": "2026-04-18T00:20:00Z",
                    "observers": ["observer-a"],
                }
            )
            linked_observation = store.upsert_observation(
                {
                    "project_id": project["project_id"],
                    "site_id": site["site_id"],
                    "route_id": route["route_id"],
                    "event_id": event["event_id"],
                    "program": "plants",
                    "protocol": "plant_transect",
                    "jurisdiction": "mainland_china",
                    "scientific_name": "Castanopsis fabri",
                    "taxon_group": "plants",
                    "count": 1,
                    "observed_at": "2026-04-18T00:05:00Z",
                }
            )
            snapped_observation = store.upsert_observation(
                {
                    "project_id": project["project_id"],
                    "site_id": site["site_id"],
                    "snapped_route_id": route["route_id"],
                    "event_id": event["event_id"],
                    "program": "plants",
                    "protocol": "plant_transect",
                    "jurisdiction": "mainland_china",
                    "scientific_name": "Schima superba",
                    "taxon_group": "plants",
                    "count": 1,
                    "observed_at": "2026-04-18T00:08:00Z",
                }
            )
            linked_track = store.upsert_track(
                {
                    "project_id": project["project_id"],
                    "site_id": site["site_id"],
                    "route_id": route["route_id"],
                    "event_id": event["event_id"],
                    "name": "Linked Track",
                    "started_at": "2026-04-18T00:00:00Z",
                    "ended_at": "2026-04-18T00:20:00Z",
                    "extra": {"observer": "observer-a"},
                }
            )
            secondary_event = store.upsert_event(
                {
                    "project_id": project["project_id"],
                    "site_id": site["site_id"],
                    "route_id": route["route_id"],
                    "program": "plants",
                    "protocol": "plant_transect",
                    "jurisdiction": "mainland_china",
                    "started_at": "2026-04-18T00:30:00Z",
                    "ended_at": "2026-04-18T00:40:00Z",
                    "observers": ["observer-b"],
                }
            )
            unlinked_track = store.upsert_track(
                {
                    "project_id": project["project_id"],
                    "site_id": site["site_id"],
                    "route_id": route["route_id"],
                    "event_id": secondary_event["event_id"],
                    "name": "Unlinked Track",
                    "started_at": "2026-04-18T00:30:00Z",
                    "ended_at": "2026-04-18T00:40:00Z",
                    "extra": {"observer": "observer-b"},
                }
            )
            map_package = store.create_map_package(
                {"project_id": project["project_id"], "name": "Offline Package"}
            )
            export_job = store.create_export_job(
                "mainland_china",
                {
                    "project_id": project["project_id"],
                    "site_id": site["site_id"],
                    "program": "plants",
                    "protocol": "plant_transect",
                    "event_id": event["event_id"],
                },
            )
            return {
                "project": project,
                "site": site,
                "route": route,
                "asset": asset,
                "event": event,
                "linked_observation": linked_observation,
                "snapped_observation": snapped_observation,
                "linked_track": linked_track,
                "unlinked_track": unlinked_track,
                "map_package": map_package,
                "export_job": export_job,
            }

        cases = [
            (
                "project",
                "project",
                {
                    "projects": 0,
                    "sites": 0,
                    "routes": 0,
                    "assets": 0,
                    "events": 0,
                    "observations": 0,
                    "tracks": 0,
                    "map_packages": 0,
                    "export_jobs": 0,
                },
            ),
            (
                "site",
                "site",
                {
                    "projects": 1,
                    "sites": 0,
                    "routes": 0,
                    "assets": 0,
                    "events": 0,
                    "observations": 0,
                    "tracks": 0,
                },
            ),
            (
                "route",
                "route",
                {
                    "projects": 1,
                    "sites": 1,
                    "routes": 0,
                    "assets": 0,
                    "events": 0,
                    "observations": 0,
                    "tracks": 0,
                },
            ),
            (
                "event",
                "event",
                {
                    "projects": 1,
                    "sites": 1,
                    "routes": 1,
                    "assets": 1,
                    "events": 1,
                    "observations": 0,
                    "tracks": 1,
                },
            ),
            (
                "design_asset",
                "asset",
                {
                    "projects": 1,
                    "sites": 1,
                    "routes": 1,
                    "assets": 0,
                    "events": 1,
                    "observations": 0,
                    "tracks": 1,
                },
            ),
        ]

        for entity_type, fixture_key, expected_counts in cases:
            with self.subTest(entity_type=entity_type):
                with tempfile.TemporaryDirectory() as temp_dir:
                    store = SurveyStore(storage_dir=temp_dir)
                    try:
                        fixture = build_fixture(store)
                        entity_id = fixture[fixture_key][
                            (
                                f"{entity_type}_id"
                                if entity_type != "design_asset"
                                else "asset_id"
                            )
                        ]
                        self.assertTrue(store.delete_entity(entity_type, entity_id))

                        self.assertEqual(
                            len(store.list_projects()),
                            expected_counts.get("projects", len(store.list_projects())),
                        )
                        self.assertEqual(
                            len(store.list_sites()),
                            expected_counts.get("sites", len(store.list_sites())),
                        )
                        self.assertEqual(
                            len(store.list_routes()),
                            expected_counts.get("routes", len(store.list_routes())),
                        )
                        self.assertEqual(
                            len(store.list_design_assets()),
                            expected_counts.get(
                                "assets", len(store.list_design_assets())
                            ),
                        )
                        self.assertEqual(
                            len(store.list_events()),
                            expected_counts.get("events", len(store.list_events())),
                        )
                        self.assertEqual(
                            len(store.list_observations()),
                            expected_counts.get(
                                "observations", len(store.list_observations())
                            ),
                        )
                        self.assertEqual(
                            len(store.list_tracks()),
                            expected_counts.get("tracks", len(store.list_tracks())),
                        )
                        if "map_packages" in expected_counts:
                            self.assertEqual(
                                len(store.list_map_packages()),
                                expected_counts["map_packages"],
                            )
                        if "export_jobs" in expected_counts:
                            self.assertEqual(
                                len(store.list_export_jobs()),
                                expected_counts["export_jobs"],
                            )
                    finally:
                        store.close()

    def test_event_scoped_generic_export_excludes_unlinked_tracks_and_exports_payload_fields(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SurveyStore(storage_dir=temp_dir)
            try:
                project = store.upsert_project(
                    {"name": "Plant Export Project", "region": "Guangxi"}
                )
                site = store.upsert_site(
                    {
                        "project_id": project["project_id"],
                        "name": "Plant Site",
                        "latitude": 22.45,
                        "longitude": 106.95,
                    }
                )
                route = store.upsert_route(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "name": "Plant Route",
                        "route_type": "transect",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[106.95, 22.45], [106.951, 22.451]],
                        },
                    }
                )
                event = store.upsert_event(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": route["route_id"],
                        "program": "plants",
                        "protocol": "plant_transect",
                        "jurisdiction": "mainland_china",
                        "started_at": "2026-04-21T00:00:00Z",
                        "ended_at": "2026-04-21T00:25:00Z",
                        "observers": ["botanist-a"],
                    }
                )
                secondary_event = store.upsert_event(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": route["route_id"],
                        "program": "plants",
                        "protocol": "plant_transect",
                        "jurisdiction": "mainland_china",
                        "started_at": "2026-04-21T00:30:00Z",
                        "ended_at": "2026-04-21T00:35:00Z",
                        "observers": ["botanist-b"],
                    }
                )
                store.upsert_observation(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": route["route_id"],
                        "event_id": event["event_id"],
                        "program": "plants",
                        "protocol": "plant_transect",
                        "jurisdiction": "mainland_china",
                        "scientific_name": "Castanopsis fabri",
                        "taxon_group": "plants",
                        "count": 3,
                        "observed_at": "2026-04-21T00:10:00Z",
                    }
                )
                store.upsert_track(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": route["route_id"],
                        "event_id": event["event_id"],
                        "name": "Linked Track",
                        "started_at": "2026-04-21T00:00:00Z",
                        "ended_at": "2026-04-21T00:25:00Z",
                        "extra": {
                            "observer": "botanist-a",
                            "weather": {"wind": "Light breeze", "temperature_c": 20},
                        },
                    }
                )
                store.upsert_track(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": route["route_id"],
                        "event_id": secondary_event["event_id"],
                        "name": "Unlinked Track",
                        "started_at": "2026-04-21T00:30:00Z",
                        "ended_at": "2026-04-21T00:35:00Z",
                        "extra": {
                            "observer": "botanist-b",
                            "weather": {"wind": "Still"},
                        },
                    }
                )

                export_job = store.create_export_job(
                    "mainland_china",
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "program": "plants",
                        "protocol": "plant_transect",
                        "event_id": event["event_id"],
                    },
                )

                self.assertEqual(export_job["summary"]["track_count"], 1)
                track_logs = next(
                    item
                    for item in export_job["bundle"]["files"]
                    if item["filename"] == "track_logs.csv"
                )
                self.assertIn("Linked Track", track_logs["content"])
                self.assertNotIn("Unlinked Track", track_logs["content"])
                self.assertIn("botanist-a", track_logs["content"])
                self.assertIn("Light breeze", track_logs["content"])
                self.assertIn("temperature_c", track_logs["content"])
            finally:
                store.close()

    def test_protocol_definitions_are_loaded_from_json_and_include_vertebrate_submodules(
        self,
    ):
        protocol_asset = json.loads(
            (
                Path(__file__).resolve().parents[1] / "data" / "survey_protocols.json"
            ).read_text(encoding="utf-8")
        )
        asset_protocol_ids = {
            item["protocol_id"] for item in protocol_asset["protocols"]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            store = SurveyStore(storage_dir=temp_dir)
            try:
                definitions = store.list_protocol_definitions()
            finally:
                store.close()

        self.assertEqual({item["protocol"] for item in definitions}, asset_protocol_ids)
        vertebrate_submodules = {
            item["protocol"]: item["submodule"]
            for item in definitions
            if item["program"] == "terrestrial_vertebrates"
        }
        self.assertEqual(
            vertebrate_submodules,
            {
                "bird_line_transect": "birds",
                "bird_point_count": "birds",
                "mammal_trap_net": "mammals",
                "herp_infrared_camera": "herpetofauna",
            },
        )

    def test_observation_and_track_require_explicit_event_id_linkage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SurveyStore(storage_dir=temp_dir)
            try:
                project = store.upsert_project(
                    {"name": "Linked Project", "region": "Guangxi"}
                )
                site = store.upsert_site(
                    {
                        "project_id": project["project_id"],
                        "name": "Linked Site",
                        "latitude": 22.45,
                        "longitude": 106.95,
                    }
                )
                route = store.upsert_route(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "name": "Linked Route",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[106.95, 22.45], [106.951, 22.451]],
                        },
                    }
                )

                with self.assertRaisesRegex(ValueError, "event_id"):
                    store.upsert_observation(
                        {
                            "project_id": project["project_id"],
                            "site_id": site["site_id"],
                            "route_id": route["route_id"],
                            "protocol": "bird_line_transect",
                            "program": "terrestrial_vertebrates",
                            "scientific_name": "Gorsachius magnificus",
                            "observed_at": "2026-04-22T00:05:00Z",
                        }
                    )

                with self.assertRaisesRegex(ValueError, "event_id"):
                    store.upsert_track(
                        {
                            "project_id": project["project_id"],
                            "site_id": site["site_id"],
                            "route_id": route["route_id"],
                            "name": "Unlinked Track",
                            "started_at": "2026-04-22T00:00:00Z",
                            "ended_at": "2026-04-22T00:10:00Z",
                            "geometry": {
                                "type": "LineString",
                                "coordinates": [[106.95, 22.45], [106.951, 22.451]],
                            },
                        }
                    )
            finally:
                store.close()

    def test_herp_attachment_metadata_is_stamped_with_event_and_observation_context(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SurveyStore(storage_dir=temp_dir)
            try:
                project = store.upsert_project(
                    {"name": "Herp Project", "region": "Guangxi"}
                )
                site = store.upsert_site(
                    {
                        "project_id": project["project_id"],
                        "name": "Herp Site",
                        "latitude": 22.45,
                        "longitude": 106.95,
                    }
                )
                route = store.upsert_route(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "name": "Camera Route",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[106.95, 22.45], [106.951, 22.451]],
                        },
                    }
                )
                event = store.upsert_event(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": route["route_id"],
                        "program": "terrestrial_vertebrates",
                        "protocol": "herp_infrared_camera",
                        "jurisdiction": "mainland_china",
                        "started_at": "2026-04-22T01:00:00Z",
                        "ended_at": "2026-04-22T06:00:00Z",
                        "observers": ["observer-a"],
                    }
                )

                observation = store.upsert_observation(
                    {
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "route_id": route["route_id"],
                        "event_id": event["event_id"],
                        "program": "terrestrial_vertebrates",
                        "protocol": "herp_infrared_camera",
                        "jurisdiction": "mainland_china",
                        "scientific_name": "Odorrana schmackeri",
                        "taxon_group": "amphibians",
                        "evidence_type": "image",
                        "observed_at": "2026-04-22T03:30:00Z",
                        "media": [
                            {
                                "media_id": "media_001",
                                "name": "camera-frame.jpg",
                                "type": "image/jpeg",
                                "storage_kind": "native_file",
                            }
                        ],
                    }
                )

                self.assertEqual(observation["media"][0]["event_id"], event["event_id"])
                self.assertEqual(
                    observation["media"][0]["observation_id"],
                    observation["observation_id"],
                )
                self.assertEqual(
                    observation["media"][0]["protocol"], "herp_infrared_camera"
                )
                self.assertEqual(
                    observation["record_payload"]["media_file_id"], "media_001"
                )
            finally:
                store.close()

    def test_sync_push_reorders_event_scoped_operations_for_offline_batches(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SurveyStore(storage_dir=temp_dir)
            try:
                project = store.upsert_project(
                    {
                        "project_id": "proj_batch",
                        "name": "Batch Project",
                        "region": "Guangxi",
                    }
                )
                site = store.upsert_site(
                    {
                        "site_id": "site_batch",
                        "project_id": project["project_id"],
                        "name": "Batch Site",
                        "latitude": 22.45,
                        "longitude": 106.95,
                    }
                )
                route = store.upsert_route(
                    {
                        "route_id": "route_batch",
                        "project_id": project["project_id"],
                        "site_id": site["site_id"],
                        "name": "Batch Route",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[106.95, 22.45], [106.951, 22.451]],
                        },
                    }
                )

                result = store.sync_push(
                    device_id="device-batch",
                    user_id="tester",
                    operations=[
                        {
                            "entity_type": "observation",
                            "operation": "upsert",
                            "entity_id": "obs_batch",
                            "payload": {
                                "observation_id": "obs_batch",
                                "project_id": project["project_id"],
                                "site_id": site["site_id"],
                                "route_id": route["route_id"],
                                "event_id": "event_batch",
                                "program": "terrestrial_vertebrates",
                                "protocol": "bird_line_transect",
                                "jurisdiction": "mainland_china",
                                "scientific_name": "Gorsachius magnificus",
                                "count": 1,
                                "evidence_type": "visual",
                                "observed_at": "2026-04-22T00:05:00Z",
                            },
                        },
                        {
                            "entity_type": "track",
                            "operation": "upsert",
                            "entity_id": "track_batch",
                            "payload": {
                                "track_id": "track_batch",
                                "project_id": project["project_id"],
                                "site_id": site["site_id"],
                                "route_id": route["route_id"],
                                "event_id": "event_batch",
                                "program": "terrestrial_vertebrates",
                                "protocol": "bird_line_transect",
                                "jurisdiction": "mainland_china",
                                "name": "Batch Track",
                                "started_at": "2026-04-22T00:00:00Z",
                                "ended_at": "2026-04-22T00:10:00Z",
                                "geometry": {
                                    "type": "LineString",
                                    "coordinates": [[106.95, 22.45], [106.951, 22.451]],
                                },
                            },
                        },
                        {
                            "entity_type": "event",
                            "operation": "upsert",
                            "entity_id": "event_batch",
                            "payload": {
                                "event_id": "event_batch",
                                "project_id": project["project_id"],
                                "site_id": site["site_id"],
                                "route_id": route["route_id"],
                                "program": "terrestrial_vertebrates",
                                "protocol": "bird_line_transect",
                                "jurisdiction": "mainland_china",
                                "started_at": "2026-04-22T00:00:00Z",
                                "ended_at": "2026-04-22T00:10:00Z",
                                "observers": ["observer-a"],
                            },
                        },
                    ],
                )

                self.assertEqual(result["conflict_count"], 0)
                self.assertEqual(result["applied_count"], 3)
                observation = store.list_observations(
                    project_id=project["project_id"], site_id=site["site_id"]
                )[0]
                track = store.list_tracks(
                    project_id=project["project_id"], site_id=site["site_id"]
                )[0]
                self.assertEqual(observation["event_id"], "event_batch")
                self.assertEqual(track["event_id"], "event_batch")
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
