from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


BASE_URL = "http://127.0.0.1:8000"
OUTPUT_DIR = Path("output") / "playwright"


def ensure_output_dir() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


def attach_logging(page: Page, report: dict[str, object]) -> None:
    page.on("console", lambda msg: report["console"].append({"type": msg.type, "text": msg.text}))
    page.on("pageerror", lambda exc: report["page_errors"].append(str(exc)))


def prepare_page(page: Page) -> None:
    page.add_init_script("window.localStorage.setItem('bird_platform_lang', 'en');")


def wait_for_app(page: Page) -> None:
    page.goto(BASE_URL, wait_until="networkidle")
    page.get_by_role("button", name="Dashboard", exact=True).wait_for(timeout=20000)


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
                title: document.title,
            };
        }""",
        label,
    )


def save_snapshot(page: Page, name: str) -> None:
    page.screenshot(path=str(OUTPUT_DIR / name), full_page=True)


def open_more(page: Page) -> None:
    page.get_by_role("button", name="More", exact=True).click()
    page.get_by_text("Field workspace", exact=True).wait_for(timeout=10000)


def main() -> None:
    output_dir = ensure_output_dir()
    report: dict[str, object] = {
        "base_url": BASE_URL,
        "checks": [],
        "screenshots": [],
        "console": [],
        "page_errors": [],
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 393, "height": 852})
        prepare_page(page)
        attach_logging(page, report)
        wait_for_app(page)

        report["checks"].append(collect_view(page, "dashboard-en"))
        save_snapshot(page, "mobile-dashboard-en.png")
        report["screenshots"].append(str(output_dir / "mobile-dashboard-en.png"))

        page.get_by_role("button", name="ZH", exact=True).click()
        page.get_by_role("button", name="总览", exact=True).wait_for(timeout=10000)
        report["checks"].append(collect_view(page, "dashboard-zh"))
        save_snapshot(page, "mobile-dashboard-zh.png")
        report["screenshots"].append(str(output_dir / "mobile-dashboard-zh.png"))

        page.get_by_role("button", name="EN", exact=True).click()
        page.get_by_role("button", name="Dashboard", exact=True).wait_for(timeout=10000)

        page.get_by_role("button", name="Analyze", exact=True).click()
        page.get_by_text("Run species analysis", exact=True).wait_for(timeout=10000)
        report["checks"].append(collect_view(page, "analyze-mobile"))
        save_snapshot(page, "mobile-analyze.png")
        report["screenshots"].append(str(output_dir / "mobile-analyze.png"))

        page.get_by_role("button", name="Review", exact=True).click()
        page.get_by_text("Evidence review desk", exact=False).wait_for(timeout=10000)
        report["checks"].append(collect_view(page, "review-mobile"))
        save_snapshot(page, "mobile-review.png")
        report["screenshots"].append(str(output_dir / "mobile-review.png"))

        page.get_by_role("button", name="Monitor", exact=True).click()
        page.get_by_text("Active monitoring sessions", exact=True).wait_for(timeout=10000)
        report["checks"].append(collect_view(page, "monitor-mobile"))
        save_snapshot(page, "mobile-monitor.png")
        report["screenshots"].append(str(output_dir / "mobile-monitor.png"))

        open_more(page)
        report["checks"].append(collect_view(page, "more-sheet-mobile"))
        save_snapshot(page, "mobile-more-sheet.png")
        report["screenshots"].append(str(output_dir / "mobile-more-sheet.png"))

        page.get_by_role("button", name="Devices", exact=True).click()
        page.get_by_text("Field device registry", exact=False).wait_for(timeout=10000)
        page.get_by_role("button", name="Map view", exact=True).click()
        page.wait_for_timeout(1200)
        page.get_by_role("button", name="Device list", exact=True).click()
        page.wait_for_timeout(500)
        page.get_by_role("button", name="Register device", exact=True).click()
        page.get_by_text("Register a new monitoring device", exact=True).wait_for(timeout=10000)
        report["checks"].append(collect_view(page, "devices-mobile"))
        save_snapshot(page, "mobile-devices.png")
        report["screenshots"].append(str(output_dir / "mobile-devices.png"))

        open_more(page)
        page.get_by_role("button", name="Settings", exact=True).click()
        page.get_by_text("Runtime configuration", exact=True).wait_for(timeout=10000)
        report["checks"].append(collect_view(page, "settings-mobile"))
        save_snapshot(page, "mobile-settings.png")
        report["screenshots"].append(str(output_dir / "mobile-settings.png"))

        browser.close()

    (output_dir / "mobile-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if report["console"] or report["page_errors"]:
        raise RuntimeError(
            f"Mobile smoke found browser issues. console={report['console'][:3]} page={report['page_errors'][:3]}"
        )


if __name__ == "__main__":
    main()
