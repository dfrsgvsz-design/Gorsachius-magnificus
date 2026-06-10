from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output" / "playwright"
INVALID_FILE = OUTPUT_DIR / "invalid-upload.txt"
BASE_URL = "http://127.0.0.1:8000"


def ensure_invalid_file() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    INVALID_FILE.write_text("this is not audio", encoding="utf-8")
    return INVALID_FILE


def prepare_page(page: Page) -> None:
    page.add_init_script("window.localStorage.setItem('bird_platform_lang', 'en');")


def wait_for_home(page: Page) -> None:
    page.goto(BASE_URL, wait_until="networkidle")
    page.get_by_role("button", name="Dashboard", exact=True).wait_for(timeout=20000)
    page.wait_for_timeout(1200)


def click_desktop_tab(page: Page, label: str) -> None:
    page.evaluate(
        """(tabLabel) => {
            const button = Array.from(document.querySelectorAll('button'))
              .find((item) => (item.innerText || '').trim() === tabLabel);
            if (!button) throw new Error(`Tab not found: ${tabLabel}`);
            button.click();
        }""",
        label,
    )
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(800)


def open_more(page: Page) -> None:
    page.get_by_role("button", name="More", exact=True).click()
    page.get_by_text("Field workspace", exact=True).wait_for(timeout=10000)


def collect_view(page: Page, label: str) -> dict:
    return page.evaluate(
        """(name) => {
            const root = document.documentElement;
            return {
                label: name,
                width: window.innerWidth,
                height: window.innerHeight,
                overflowX: root.scrollWidth - window.innerWidth,
                overflowY: root.scrollHeight - window.innerHeight,
            };
        }""",
        label,
    )


def main() -> None:
    invalid_path = ensure_invalid_file()
    report: dict[str, object] = {
        "base_url": BASE_URL,
        "checks": [],
        "console": [],
        "page_errors": [],
        "screenshots": [],
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()

        desktop = browser.new_page(viewport={"width": 1440, "height": 1100})
        prepare_page(desktop)
        desktop.on("console", lambda msg: report["console"].append({"scope": "desktop", "type": msg.type, "text": msg.text}))
        desktop.on("pageerror", lambda exc: report["page_errors"].append({"scope": "desktop", "text": str(exc)}))
        wait_for_home(desktop)

        desktop.context.set_offline(True)
        desktop.wait_for_timeout(1200)
        desktop.get_by_text(
            "You are offline. Cached pages remain available, but uploads and live monitoring may pause.",
            exact=True,
        ).wait_for(timeout=10000)
        desktop.screenshot(path=str(OUTPUT_DIR / "edge-offline-banner-desktop.png"), full_page=False)
        report["screenshots"].append(str(OUTPUT_DIR / "edge-offline-banner-desktop.png"))
        report["checks"].append(collect_view(desktop, "desktop-offline-banner"))
        desktop.context.set_offline(False)
        desktop.wait_for_timeout(1200)

        click_desktop_tab(desktop, "Analyze")
        desktop.get_by_role("button", name="Run species analysis", exact=True).wait_for(timeout=10000)
        desktop.locator("#audio-input").set_input_files(str(invalid_path))
        desktop.get_by_role("button", name="Run species analysis", exact=True).click()
        desktop.locator("text=Invalid audio file").wait_for(timeout=30000)
        desktop.screenshot(path=str(OUTPUT_DIR / "edge-invalid-upload-desktop.png"), full_page=True)
        report["screenshots"].append(str(OUTPUT_DIR / "edge-invalid-upload-desktop.png"))
        report["checks"].append(collect_view(desktop, "desktop-invalid-upload"))
        desktop.close()

        mobile = browser.new_page(viewport={"width": 393, "height": 852})
        prepare_page(mobile)
        mobile.on("console", lambda msg: report["console"].append({"scope": "mobile", "type": msg.type, "text": msg.text}))
        mobile.on("pageerror", lambda exc: report["page_errors"].append({"scope": "mobile", "text": str(exc)}))
        wait_for_home(mobile)

        mobile.context.set_offline(True)
        mobile.wait_for_timeout(1200)
        mobile.get_by_text(
            "You are offline. Cached pages remain available, but uploads and live monitoring may pause.",
            exact=True,
        ).wait_for(timeout=10000)
        mobile.screenshot(path=str(OUTPUT_DIR / "edge-offline-banner-mobile.png"), full_page=False)
        report["screenshots"].append(str(OUTPUT_DIR / "edge-offline-banner-mobile.png"))
        report["checks"].append(collect_view(mobile, "mobile-offline-banner"))
        mobile.context.set_offline(False)
        mobile.wait_for_timeout(1200)

        mobile.get_by_role("button", name="Analyze", exact=True).click()
        mobile.get_by_role("button", name="Run species analysis", exact=True).wait_for(timeout=10000)
        mobile.locator("#audio-input").set_input_files(str(invalid_path))
        mobile.get_by_role("button", name="Run species analysis", exact=True).click()
        mobile.locator("text=Invalid audio file").wait_for(timeout=30000)
        mobile.screenshot(path=str(OUTPUT_DIR / "edge-invalid-upload-mobile.png"), full_page=True)
        report["screenshots"].append(str(OUTPUT_DIR / "edge-invalid-upload-mobile.png"))
        report["checks"].append(collect_view(mobile, "mobile-invalid-upload"))

        open_more(mobile)
        mobile.get_by_role("button", name="Devices", exact=True).click()
        mobile.get_by_role("button", name="Register device", exact=True).click()
        mobile.get_by_text("Register a new monitoring device", exact=True).wait_for(timeout=10000)
        mobile.screenshot(path=str(OUTPUT_DIR / "edge-mobile-device-form.png"), full_page=True)
        report["screenshots"].append(str(OUTPUT_DIR / "edge-mobile-device-form.png"))
        report["checks"].append(collect_view(mobile, "mobile-device-form"))
        mobile.close()

        browser.close()

    (OUTPUT_DIR / "edge-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    unexpected_console = [
        item for item in report["console"]
        if "status of 400" not in item.get("text", "")
    ]

    if unexpected_console or report["page_errors"]:
        raise RuntimeError(
            f"edge_case_smoke found browser issues. console={unexpected_console[:3]} page={report['page_errors'][:3]}"
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"edge_case_smoke failed: {exc}", file=sys.stderr)
        raise
