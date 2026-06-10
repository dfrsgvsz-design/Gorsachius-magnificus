#!/usr/bin/env python3
"""
API Test Suite — Verifies all backend endpoints are functional.

Usage:
    python scripts/test_api_v7.py
    python scripts/test_api_v7.py --base-url http://localhost:8000
"""

import sys
import json
import argparse
import requests
from pathlib import Path


def test_endpoint(base, method, path, expected_status=200, **kwargs):
    """Test a single API endpoint."""
    url = f"{base}{path}"
    try:
        if method == "GET":
            resp = requests.get(url, timeout=30, **kwargs)
        elif method == "POST":
            resp = requests.post(url, timeout=30, **kwargs)
        elif method == "DELETE":
            resp = requests.delete(url, timeout=30, **kwargs)
        else:
            return False, f"Unknown method: {method}"

        if resp.status_code == expected_status:
            return True, resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text[:100]
        else:
            return False, f"Status {resp.status_code}: {resp.text[:200]}"
    except requests.exceptions.ConnectionError:
        return False, "Connection refused — is the backend running?"
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description="Test bird_sound_platform API endpoints")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    print(f"Testing API at: {base}")
    print("=" * 60)

    tests = [
        ("GET", "/api/health", 200, {}, "Health check"),
        ("GET", "/api/species", 200, {}, "Species list"),
        ("GET", "/api/species/orders", 200, {}, "Species orders"),
        ("GET", "/api/species/families", 200, {}, "Species families"),
        ("GET", "/api/species/stats", 200, {}, "Species stats"),
        ("GET", "/api/xc-key-status", 200, {}, "XC key status"),
        ("GET", "/api/birdnet/status", 200, {}, "BirdNET status"),
        ("GET", "/api/devices", 200, {}, "Device list"),
        ("GET", "/api/devices/online", 200, {}, "Online devices"),
        ("GET", "/api/devices/map", 200, {}, "Device map"),
        ("GET", "/api/monitoring/sessions", 200, {}, "Monitoring sessions"),
        ("GET", "/api/monitoring/dashboard", 200, {}, "Monitoring dashboard"),
        ("GET", "/api/detections/unverified", 200, {}, "Unverified detections"),
        ("GET", "/api/detections/stats", 200, {}, "Detection stats"),
        ("GET", "/api/embeddings/stats", 200, {}, "Embedding stats"),
        ("GET", "/api/paper-context", 200, {}, "Paper context"),
        ("GET", "/api/export/detections", 200, {}, "Export CSV"),
    ]

    passed = 0
    failed = 0

    for method, path, status, kwargs, desc in tests:
        ok, result = test_endpoint(base, method, path, status, **kwargs)
        icon = "✓" if ok else "✗"
        color = "" if ok else " [FAIL]"
        print(f"  {icon} {desc:30s} {method} {path}{color}")
        if not ok:
            print(f"    → {result}")
            failed += 1
        else:
            passed += 1

    print(f"\n{'=' * 60}")
    print(f"  Results: {passed} passed, {failed} failed, {passed + failed} total")
    if failed == 0:
        print("  All tests passed!")
    else:
        print(f"  {failed} test(s) failed.")
    print(f"{'=' * 60}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
