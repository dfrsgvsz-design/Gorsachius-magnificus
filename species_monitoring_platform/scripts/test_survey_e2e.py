#!/usr/bin/env python3
"""
End-to-end API test for the full field survey workflow.

Flow:
  1. Health check
  2. Create project
  3. Create site (linked to project)
  4. Create route (linked to project + site, with LineString geometry)
  5. Create sampling event (linked to project + site + route, with protocol)
  6. Create track (linked to event, with GPS coordinates)
  7. Create observation (linked to event, with species data)
  8. Get route summary
  9. Export route as GeoJSON
 10. Create export job (protocol bundle)

Usage:
  python scripts/test_survey_e2e.py [--base-url http://localhost:8000]
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "http://localhost:8000"
TIMEOUT = 10


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def api(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        print(f"  ✗ {method} {path} → HTTP {exc.code}")
        print(f"    {err_body[:500]}")
        raise


def step(label: str):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")


def assert_ok(resp: dict, key: str | None = None):
    assert resp.get("status") == "ok", f"Expected status=ok, got {resp.get('status')}"
    if key:
        assert key in resp, f"Missing key '{key}' in response"
    return resp


def assert_field(obj: dict, field: str, expected=None):
    val = obj.get(field)
    if expected is not None:
        assert val == expected, f"  {field}: expected {expected!r}, got {val!r}"
    else:
        assert val not in (None, ""), f"  {field}: expected non-empty, got {val!r}"
    return val


# ─── Test data ───────────────────────────────────────────────

PROJECT_DATA = {
    "name": "海南鳽样线监测试验项目",
    "team_members": ["张三", "李四"],
    "target_taxa": ["birds"],
    "region": "广西弄岗",
    "notes": "E2E test project",
}

SITE_DATA = {
    "name": "弄岗保护区A样点",
    "latitude": 22.45,
    "longitude": 107.05,
    "habitat_type": "evergreen_broadleaf_forest",
    "admin_region": "广西崇左",
    "notes": "E2E test site",
}

ROUTE_COORDS = [
    [107.050, 22.450],
    [107.051, 22.451],
    [107.052, 22.452],
    [107.053, 22.453],
    [107.054, 22.454],
]

ROUTE_DATA = {
    "name": "弄岗1号样线",
    "route_type": "transect",
    "geometry": {"type": "LineString", "coordinates": ROUTE_COORDS},
    "source": "manual",
}

EVENT_DATA = {
    "protocol": "bird_line_transect",
    "program": "terrestrial_vertebrates",
    "jurisdiction": "mainland_china",
    "started_at": _ts(),
    "weather": {"condition": "cloudy", "temperature": 22, "wind": "light"},
    "effort_metrics": {"distance_m": 500, "duration_min": 45},
    "observers": ["张三"],
    "notes": "E2E test event",
}

TRACK_COORDS = [
    [107.0500, 22.4500],
    [107.0505, 22.4505],
    [107.0510, 22.4510],
    [107.0515, 22.4515],
    [107.0520, 22.4520],
]

OBSERVATION_DATA = {
    "scientific_name": "Gorsachius magnificus",
    "chinese_name": "海南鳽",
    "english_name": "White-eared Night Heron",
    "taxon_group": "birds",
    "count": 2,
    "evidence_type": "visual",
    "behavior": "foraging",
    "confidence": 0.95,
    "certainty": "confirmed",
    "latitude": 22.451,
    "longitude": 107.051,
    "observer": "张三",
    "observed_at": _ts(),
}


# ─── Main test ───────────────────────────────────────────────

def run_tests():
    results = {"pass": 0, "fail": 0, "errors": []}

    def check(label: str, fn):
        try:
            fn()
            results["pass"] += 1
            print(f"  ✓ {label}")
        except Exception as exc:
            results["fail"] += 1
            results["errors"].append(f"{label}: {exc}")
            print(f"  ✗ {label}: {exc}")

    # ─── Step 1: Health ─────────────────────────────────────
    step("1. Health Check")
    health = None
    try:
        health = api("GET", "/api/health")
        print(f"  Status: {health.get('status')}")
        print(f"  Species DB: {health.get('num_species_db', '?')}")
    except Exception as exc:
        print(f"  ✗ Backend unreachable: {exc}")
        print(f"\n请先启动后端: cd backend && python main.py")
        sys.exit(1)
    check("health status is ok", lambda: assert_field(health, "status", "ok"))

    # ─── Step 2: Create Project ─────────────────────────────
    step("2. Create Project")
    resp = api("POST", "/api/surveys/projects", PROJECT_DATA)
    assert_ok(resp, "project")
    project = resp["project"]
    project_id = project["project_id"]
    print(f"  project_id: {project_id}")
    check("project_id assigned", lambda: assert_field(project, "project_id"))
    check("project name", lambda: assert_field(project, "name", PROJECT_DATA["name"]))

    # ─── Step 3: Create Site ────────────────────────────────
    step("3. Create Site")
    site_payload = {**SITE_DATA, "project_id": project_id}
    resp = api("POST", "/api/surveys/sites", site_payload)
    assert_ok(resp, "site")
    site = resp["site"]
    site_id = site["site_id"]
    print(f"  site_id: {site_id}")
    check("site_id assigned", lambda: assert_field(site, "site_id"))
    check("site name", lambda: assert_field(site, "name", SITE_DATA["name"]))
    check("site latitude", lambda: assert_field(site, "latitude", SITE_DATA["latitude"]))
    check("site geometry auto-built",
          lambda: assert_field(site, "geometry"))

    # ─── Step 4: Create Route ───────────────────────────────
    step("4. Create Route")
    route_payload = {**ROUTE_DATA, "project_id": project_id, "site_id": site_id}
    resp = api("POST", "/api/surveys/routes", route_payload)
    assert_ok(resp, "route")
    route = resp["route"]
    route_id = route["route_id"]
    print(f"  route_id: {route_id}")
    print(f"  length_m: {route.get('length_m')}")
    check("route_id assigned", lambda: assert_field(route, "route_id"))
    check("route name", lambda: assert_field(route, "name", ROUTE_DATA["name"]))
    check("route has geometry", lambda: assert_field(route, "geometry"))
    check("route length > 0",
          lambda: (None if route.get("length_m", 0) > 0 else (_ for _ in ()).throw(AssertionError("length_m is 0"))))

    # ─── Step 5: Create Sampling Event ──────────────────────
    step("5. Create Sampling Event")
    event_payload = {
        **EVENT_DATA,
        "project_id": project_id,
        "site_id": site_id,
        "route_id": route_id,
    }
    resp = api("POST", "/api/surveys/events", event_payload)
    assert_ok(resp, "event")
    event = resp["event"]
    event_id = event["event_id"]
    print(f"  event_id: {event_id}")
    print(f"  protocol: {event.get('protocol')}")
    print(f"  program: {event.get('program')}")
    check("event_id assigned", lambda: assert_field(event, "event_id"))
    check("event protocol", lambda: assert_field(event, "protocol", "bird_line_transect"))
    check("event program", lambda: assert_field(event, "program", "terrestrial_vertebrates"))
    check("event jurisdiction", lambda: assert_field(event, "jurisdiction", "mainland_china"))

    # ─── Step 6: Create Track ───────────────────────────────
    step("6. Create Track (GPS trail)")
    now = _ts()
    track_payload = {
        "project_id": project_id,
        "site_id": site_id,
        "route_id": route_id,
        "event_id": event_id,
        "name": "弄岗1号样线轨迹",
        "geometry": {"type": "LineString", "coordinates": TRACK_COORDS},
        "point_times": [_ts() for _ in TRACK_COORDS],
        "started_at": EVENT_DATA["started_at"],
        "ended_at": now,
        "observer": "张三",
        "weather": EVENT_DATA["weather"],
    }
    resp = api("POST", "/api/surveys/tracks", track_payload)
    assert_ok(resp, "track")
    track = resp["track"]
    track_id = track["track_id"]
    print(f"  track_id: {track_id}")
    print(f"  distance_m: {track.get('distance_m')}")
    print(f"  duration_s: {track.get('duration_s')}")
    check("track_id assigned", lambda: assert_field(track, "track_id"))
    check("track has geometry", lambda: assert_field(track, "geometry"))
    check("track event linkage", lambda: assert_field(track, "event_id", event_id))

    # ─── Step 7: Create Observation ─────────────────────────
    step("7. Create Observation (Gorsachius magnificus)")
    obs_payload = {
        **OBSERVATION_DATA,
        "project_id": project_id,
        "site_id": site_id,
        "route_id": route_id,
        "event_id": event_id,
    }
    resp = api("POST", "/api/surveys/observations", obs_payload)
    assert_ok(resp, "observation")
    obs = resp["observation"]
    obs_id = obs["observation_id"]
    print(f"  observation_id: {obs_id}")
    check("observation_id assigned", lambda: assert_field(obs, "observation_id"))
    check("species name", lambda: assert_field(obs, "scientific_name", "Gorsachius magnificus"))
    check("chinese name", lambda: assert_field(obs, "chinese_name", "海南鳽"))
    check("count", lambda: assert_field(obs, "count", 2))
    check("event linkage", lambda: assert_field(obs, "event_id", event_id))

    # Create a second observation for diversity
    step("7b. Create Second Observation (Gorsachius melanolophus)")
    obs2_payload = {
        "project_id": project_id,
        "site_id": site_id,
        "route_id": route_id,
        "event_id": event_id,
        "scientific_name": "Gorsachius melanolophus",
        "chinese_name": "黑冠鳽",
        "english_name": "Malayan Night Heron",
        "taxon_group": "birds",
        "count": 1,
        "evidence_type": "audio",
        "behavior": "calling",
        "confidence": 0.8,
        "certainty": "probable",
        "latitude": 22.452,
        "longitude": 107.052,
        "observer": "李四",
        "observed_at": _ts(),
    }
    resp = api("POST", "/api/surveys/observations", obs2_payload)
    assert_ok(resp, "observation")
    obs2 = resp["observation"]
    print(f"  observation_id: {obs2['observation_id']}")
    check("second obs saved", lambda: assert_field(obs2, "scientific_name", "Gorsachius melanolophus"))

    # ─── Step 8: Route Summary ──────────────────────────────
    step("8. Get Route Summary")
    resp = api("GET", f"/api/surveys/routes/{route_id}/summary")
    assert_ok(resp, "summary")
    summary = resp["summary"]
    totals = summary.get("totals", {})
    print(f"  observations: {totals.get('observation_count')}")
    print(f"  individuals: {totals.get('individual_count')}")
    print(f"  unique species: {totals.get('unique_species_count')}")
    print(f"  tracks: {totals.get('track_count')}")
    print(f"  walked_distance_m: {totals.get('walked_distance_m')}")
    check("obs count = 2", lambda: (
        None if totals.get("observation_count") == 2
        else (_ for _ in ()).throw(AssertionError(f"expected 2, got {totals.get('observation_count')}"))
    ))
    check("individual count = 3", lambda: (
        None if totals.get("individual_count") == 3
        else (_ for _ in ()).throw(AssertionError(f"expected 3, got {totals.get('individual_count')}"))
    ))
    check("unique species = 2", lambda: (
        None if totals.get("unique_species_count") == 2
        else (_ for _ in ()).throw(AssertionError(f"expected 2, got {totals.get('unique_species_count')}"))
    ))

    # ─── Step 9: Export Route ───────────────────────────────
    step("9. Export Route as GeoJSON")
    url = f"{BASE_URL}/api/surveys/routes/{route_id}/export?format=geojson"
    req = Request(url, method="GET")
    with urlopen(req, timeout=TIMEOUT) as resp_raw:
        geojson_text = resp_raw.read().decode("utf-8")
        geojson = json.loads(geojson_text)
    print(f"  type: {geojson.get('type')}")
    features = geojson.get("features", [])
    print(f"  features: {len(features)}")
    check("GeoJSON is FeatureCollection",
          lambda: assert_field(geojson, "type", "FeatureCollection"))
    check("has features", lambda: (
        None if len(features) > 0
        else (_ for _ in ()).throw(AssertionError("no features"))
    ))

    # ─── Step 10: Protocol Export ───────────────────────────
    step("10. Create Export Job (mainland_china)")
    export_payload = {
        "project_id": project_id,
        "site_id": site_id,
        "program": "terrestrial_vertebrates",
        "protocol": "bird_line_transect",
        "event_id": event_id,
        "format": "json",
    }
    resp = api("POST", "/api/surveys/exports/mainland_china", export_payload)
    assert_ok(resp, "export_job")
    export_job = resp["export_job"]
    print(f"  export_job_id: {export_job.get('export_job_id')}")
    bundle = export_job.get("bundle", {})
    bundle_summary = bundle.get("summary", {})
    print(f"  events: {bundle_summary.get('event_count')}")
    print(f"  observations: {bundle_summary.get('observation_count')}")
    print(f"  tracks: {bundle_summary.get('track_count')}")
    check("export status", lambda: assert_field(export_job, "status", "ready"))
    check("export has bundle", lambda: assert_field(export_job, "bundle"))

    # ─── Step 11: List endpoints ────────────────────────────
    step("11. Verify List Endpoints")
    projects = api("GET", "/api/surveys/projects")
    check("list projects", lambda: (
        None if projects.get("total", 0) >= 1
        else (_ for _ in ()).throw(AssertionError(f"total={projects.get('total')}"))
    ))

    sites = api("GET", f"/api/surveys/sites?project_id={project_id}")
    check("list sites", lambda: (
        None if sites.get("total", 0) >= 1
        else (_ for _ in ()).throw(AssertionError(f"total={sites.get('total')}"))
    ))

    routes = api("GET", f"/api/surveys/routes?project_id={project_id}&site_id={site_id}")
    check("list routes", lambda: (
        None if routes.get("total", 0) >= 1
        else (_ for _ in ()).throw(AssertionError(f"total={routes.get('total')}"))
    ))

    events = api("GET", f"/api/surveys/events?project_id={project_id}")
    check("list events", lambda: (
        None if events.get("total", 0) >= 1
        else (_ for _ in ()).throw(AssertionError(f"total={events.get('total')}"))
    ))

    observations = api("GET", f"/api/surveys/observations?project_id={project_id}&site_id={site_id}")
    check("list observations", lambda: (
        None if observations.get("total", 0) >= 2
        else (_ for _ in ()).throw(AssertionError(f"total={observations.get('total')}"))
    ))

    tracks = api("GET", f"/api/surveys/tracks?project_id={project_id}&site_id={site_id}")
    check("list tracks", lambda: (
        None if tracks.get("total", 0) >= 1
        else (_ for _ in ()).throw(AssertionError(f"total={tracks.get('total')}"))
    ))

    # ─── Summary ────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  RESULTS: {results['pass']} passed, {results['fail']} failed")
    print(f"{'='*60}")
    if results["errors"]:
        print("\nFailed checks:")
        for err in results["errors"]:
            print(f"  ✗ {err}")
    print()
    return results["fail"] == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="E2E survey API test")
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    BASE_URL = args.base_url.rstrip("/")
    print(f"Target: {BASE_URL}")
    ok = run_tests()
    sys.exit(0 if ok else 1)
