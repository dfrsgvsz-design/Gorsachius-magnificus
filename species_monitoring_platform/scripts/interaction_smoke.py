from __future__ import annotations

import json
import math
import struct
import sys
import urllib.request
import wave
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import TimeoutError, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.detection_store import DetectionStore


BASE_URL = "http://127.0.0.1:8000"
OUTPUT_DIR = Path("output") / "playwright"
TEST_AUDIO = OUTPUT_DIR / "smoke-tone.wav"
TEST_DEVICE_LABEL = f"SMOKE-{uuid4().hex[:6].upper()}"
TEST_DEVICE_NAME = f"Smoke Device {uuid4().hex[:6].upper()}"
TEST_SESSION_ID = f"smoke-session-{uuid4().hex[:8]}"
TEST_SITE_NAME = f"Smoke Site {uuid4().hex[:6].upper()}"
TEST_SPECIES = "Gorsachius magnificus"
TEST_SPECIES_CN = "海南鳽"


def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def ensure_test_audio() -> Path:
    ensure_output_dir()
    if TEST_AUDIO.exists():
        return TEST_AUDIO

    sample_rate = 22050
    duration_sec = 6
    frequency = 880.0
    amplitude = 0.25

    with wave.open(str(TEST_AUDIO), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)

        frames = []
        for index in range(sample_rate * duration_sec):
            sample = amplitude * math.sin(2 * math.pi * frequency * (index / sample_rate))
            frames.append(struct.pack("<h", int(sample * 32767)))
        wav_file.writeframes(b"".join(frames))

    return TEST_AUDIO


def seed_review_detection() -> str:
    store = DetectionStore()
    detection_id = store.add_detection(
        species=TEST_SPECIES,
        species_chinese=TEST_SPECIES_CN,
        confidence=0.29,
        session_id=TEST_SESSION_ID,
        time_offset=12.4,
        device_id=TEST_DEVICE_LABEL,
        site_name=TEST_SITE_NAME,
        model_version="smoke-test",
    )
    store.save()
    store.close()
    return detection_id


def prepare_english_ui(page) -> None:
    page.add_init_script("window.localStorage.setItem('bird_platform_lang', 'en');")


def wait_for_dashboard(page) -> None:
    page.goto(BASE_URL, wait_until="networkidle")
    page.get_by_text("Bird Sound", exact=False).first.wait_for(timeout=20000)
    page.get_by_role("button", name="Dashboard", exact=True).wait_for(timeout=20000)


def click_top_tab(page, label: str) -> None:
    page.evaluate(
        """(tabLabel) => {
            const buttons = Array.from(document.querySelectorAll('button'));
            const button = buttons.find((item) => (item.innerText || '').trim() === tabLabel);
            if (!button) throw new Error(`Tab not found: ${tabLabel}`);
            button.click();
        }""",
        label,
    )
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1200)


def save_shot(page, name: str) -> None:
    page.screenshot(path=str(OUTPUT_DIR / name), full_page=True)


def click_button_by_text(page, text: str) -> None:
    page.evaluate(
        """(targetText) => {
            const button = Array.from(document.querySelectorAll('button'))
              .find((item) => (item.innerText || '').trim() === targetText);
            if (!button) throw new Error(`Button not found: ${targetText}`);
            button.click();
        }""",
        text,
    )
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)


def fetch_json(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_device_in_api(name: str, should_exist: bool, timeout_ms: int = 20000) -> None:
    import time

    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        payload = fetch_json("/api/devices")
        names = {item.get("name") for item in payload.get("devices", [])}
        exists = name in names
        if exists == should_exist:
            return
        time.sleep(0.75)
    raise RuntimeError(f"Device state did not converge for {name}. should_exist={should_exist}")


def delete_device_by_name(name: str) -> None:
    payload = fetch_json("/api/devices")
    device = next((item for item in payload.get("devices", []) if item.get("name") == name), None)
    if not device:
        return
    request = urllib.request.Request(
        f"{BASE_URL}/api/devices/{device['device_id']}",
        method="DELETE",
    )
    with urllib.request.urlopen(request, timeout=30):
        pass


def wait_for_detection_status(detection_id: str, expected: str, timeout_ms: int = 20000) -> None:
    import time

    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        store = DetectionStore()
        try:
            rows = [item for item in store.get_all_detections() if item["detection_id"] == detection_id]
        finally:
            store.close()
        if rows and rows[0]["verification"] == expected:
            return
        time.sleep(0.75)
    raise RuntimeError(f"Detection {detection_id} did not reach status {expected}")


def desktop_flow() -> None:
    audio_path = ensure_test_audio()
    seeded_detection_id = seed_review_detection()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        prepare_english_ui(page)

        errors: list[str] = []
        console_errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        wait_for_dashboard(page)
        save_shot(page, "interaction-dashboard.png")

        click_top_tab(page, "Devices")
        page.get_by_role("button", name="Register device", exact=True).click()
        page.get_by_placeholder("External device label, e.g. ARU-001").fill(TEST_DEVICE_LABEL)
        page.get_by_placeholder("Human-readable site or device name").fill(TEST_DEVICE_NAME)
        page.get_by_placeholder("Latitude, e.g. 22.4500").fill("22.4510")
        page.get_by_placeholder("Longitude, e.g. 106.9600").fill("106.9620")
        page.locator("select").select_option("audiomoth")
        click_button_by_text(page, "Save device")
        wait_for_device_in_api(TEST_DEVICE_NAME, should_exist=True)
        save_shot(page, "interaction-devices-added.png")

        click_top_tab(page, "Review")
        page.get_by_role("heading", name="Evidence review desk", exact=True).wait_for(timeout=20000)
        review_card = page.locator("button.glass-card", has_text=TEST_SITE_NAME).first
        review_card.wait_for(timeout=20000)
        review_card.get_by_role("button", name="Confirm", exact=True).click()
        wait_for_detection_status(seeded_detection_id, "confirmed")
        save_shot(page, "interaction-review-confirmed.png")

        click_top_tab(page, "Analyze")
        page.locator("#audio-input").set_input_files(str(audio_path.resolve()))
        page.get_by_role("button", name="Run species analysis", exact=True).click()
        try:
            page.get_by_text("Interpretation snapshot", exact=True).wait_for(timeout=120000)
        except TimeoutError as exc:
            body_text = page.locator("body").inner_text()
            raise RuntimeError(
                f"Analyze flow did not finish successfully. Body excerpt: {body_text[:1200]}"
            ) from exc
        save_shot(page, "interaction-analyze-complete.png")

        click_top_tab(page, "Settings")
        page.get_by_role("button", name="Refresh runtime", exact=True).click()
        page.get_by_text("System information", exact=True).wait_for(timeout=20000)
        save_shot(page, "interaction-settings.png")

        delete_device_by_name(TEST_DEVICE_NAME)
        wait_for_device_in_api(TEST_DEVICE_NAME, should_exist=False)
        wait_for_dashboard(page)
        click_top_tab(page, "Devices")
        save_shot(page, "interaction-devices-removed.png")

        mobile = browser.new_page(viewport={"width": 393, "height": 852})
        prepare_english_ui(mobile)
        wait_for_dashboard(mobile)
        mobile.get_by_role("button", name="More", exact=True).click()
        mobile.get_by_text("Field workspace", exact=True).wait_for(timeout=10000)
        mobile.get_by_role("button", name="Devices", exact=True).click()
        mobile.get_by_text("Field device registry", exact=False).wait_for(timeout=20000)
        save_shot(mobile, "interaction-mobile-devices.png")

        mobile.get_by_role("button", name="More", exact=True).click()
        mobile.get_by_role("button", name="Settings", exact=True).click()
        mobile.get_by_text("Runtime configuration", exact=False).wait_for(timeout=20000)
        save_shot(mobile, "interaction-mobile-settings.png")

        mobile.close()
        page.close()
        browser.close()

        if errors or console_errors:
            raise RuntimeError(
                f"Browser errors during interaction smoke. console={console_errors[:3]} page={errors[:3]}"
            )

        wait_for_detection_status(seeded_detection_id, "confirmed")


if __name__ == "__main__":
    desktop_flow()
