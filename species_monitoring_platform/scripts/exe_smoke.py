"""
Smoke-test the packaged Windows desktop executable.

Launches the app without auto-opening the browser, waits for the local URL file,
then verifies the main page and key API endpoints.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXE = ROOT / "dist" / "BirdSoundPlatform" / "BirdSoundPlatform.exe"


def fetch_json(url: str, timeout: int = 15) -> dict:
    with urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_text(url: str, timeout: int = 15) -> str:
    with urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def wait_for_url(url_file: Path, timeout: int) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if url_file.exists():
            url = url_file.read_text(encoding="utf-8").strip()
            if url:
                return url
        time.sleep(0.5)
    raise TimeoutError(f"Timed out waiting for {url_file}")


def wait_for_health(url: str, timeout: int) -> dict:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            return fetch_json(f"{url}/api/health", timeout=10)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(1)
    raise TimeoutError(f"Timed out waiting for health endpoint: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the packaged desktop executable")
    parser.add_argument("--exe", default=str(DEFAULT_EXE), help="Path to BirdSoundPlatform.exe")
    parser.add_argument("--timeout", type=int, default=120, help="Overall wait timeout in seconds")
    args = parser.parse_args()

    exe_path = Path(args.exe).resolve()
    if not exe_path.exists():
        raise FileNotFoundError(f"Executable not found: {exe_path}")

    app_dir = exe_path.parent
    url_file = app_dir / "output" / "last-launch-url.txt"
    log_file = app_dir / "output" / "launcher.log"
    db_file = app_dir / "data" / "detections" / "detections.db"

    if url_file.exists():
        url_file.unlink()

    env = os.environ.copy()
    env["BIRD_PLATFORM_OPEN_BROWSER"] = "0"

    proc = subprocess.Popen(
        [str(exe_path)],
        cwd=str(app_dir),
        env=env,
    )

    try:
        url = wait_for_url(url_file, timeout=args.timeout)
        health = wait_for_health(url, timeout=args.timeout)
        html = fetch_text(url, timeout=15)
        species = fetch_json(f"{url}/api/species?limit=1", timeout=15)

        summary = {
            "exe": str(exe_path),
            "url": url,
            "health": {
                "runtime_state": health.get("runtime_state"),
                "num_species_model": health.get("num_species_model"),
                "num_species_db": health.get("num_species_db"),
                "devices_online": health.get("devices_online"),
            },
            "root_ok": "Bird Sound" in html or "Research Workbench" in html or "BirdNET" in html,
            "species_total": species.get("total"),
            "db_exists": db_file.exists(),
            "log_exists": log_file.exists(),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))

        if not summary["root_ok"]:
            raise RuntimeError("Root page did not contain expected app markers")
        if summary["species_total"] is None:
            raise RuntimeError("Species endpoint did not return total")
        if not summary["db_exists"]:
            raise RuntimeError("Packaged detections database was not created")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (TimeoutError, URLError, RuntimeError, FileNotFoundError) as exc:
        print(f"EXE_SMOKE_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
