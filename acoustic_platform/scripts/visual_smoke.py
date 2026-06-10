from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import Error, Page, sync_playwright


BASE_URL = "http://127.0.0.1:8000"
OUTPUT_DIR = Path("output") / "playwright"


def ensure_output_dir() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


def prepare_english_ui(page: Page) -> None:
    page.add_init_script("window.localStorage.setItem('bird_platform_lang', 'en');")


def collect_runtime_issues(page: Page, label: str) -> dict:
    return page.evaluate(
        """(name) => {
            const root = document.documentElement;
            const body = document.body;
            const overflowX = root.scrollWidth - window.innerWidth;
            const overflowY = root.scrollHeight - window.innerHeight;
            return {
                label: name,
                title: document.title,
                readyState: document.readyState,
                width: window.innerWidth,
                height: window.innerHeight,
                overflowX,
                overflowY,
                hasHorizontalOverflow: overflowX > 2,
                bodyClasses: body ? body.className : '',
            };
        }""",
        label,
    )


def wait_for_app(page: Page) -> None:
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_function("document.title.includes('Bird Sound Research Workbench')")
    page.wait_for_timeout(2500)


def click_visible_button(page: Page, scope_selector: str, label: str) -> None:
    clicked = page.evaluate(
        """([scopeSelector, targetLabel]) => {
            const scopes = Array.from(document.querySelectorAll(scopeSelector));
            const buttons = scopes.flatMap((scope) => Array.from(scope.querySelectorAll('button')));
            const target = buttons.find((button) => {
                const text = (button.innerText || '').trim();
                const style = window.getComputedStyle(button);
                const visible = button.offsetParent !== null && style.visibility !== 'hidden' && style.display !== 'none';
                return visible && text === targetLabel;
            });
            if (!target) return false;
            target.click();
            return true;
        }""",
        [scope_selector, label],
    )
    if not clicked:
        raise RuntimeError(f"Could not click visible button: {label} within {scope_selector}")


def click_desktop_tab(page: Page, label: str) -> None:
    click_visible_button(page, "body", label)
    page.wait_for_load_state("networkidle")


def click_mobile_primary_tab(page: Page, label: str) -> None:
    click_visible_button(page, ".mobile-bottom-nav", label)
    page.wait_for_load_state("networkidle")


def click_more_sheet_tab(page: Page, label: str) -> None:
    click_visible_button(page, ".fixed.inset-0", label)
    page.wait_for_load_state("networkidle")


def save_snapshot(page: Page, name: str) -> None:
    page.screenshot(path=str(OUTPUT_DIR / name), full_page=True)


def attach_logging(page: Page, report: dict[str, object], scope: str) -> None:
    page.on("console", lambda msg: report["console"].append({"scope": scope, "type": msg.type, "text": msg.text}))
    page.on("pageerror", lambda exc: report["page_errors"].append({"scope": scope, "text": str(exc)}))


def open_page(context, report: dict[str, object], scope: str):
    page = context.new_page()
    prepare_english_ui(page)
    attach_logging(page, report, scope)
    wait_for_app(page)
    return page


def main() -> None:
    output_dir = ensure_output_dir()
    report: dict[str, object] = {"base_url": BASE_URL, "screenshots": [], "console": [], "page_errors": [], "checks": []}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()

        desktop = browser.new_context(viewport={"width": 1440, "height": 1100})
        desktop_page = open_page(desktop, report, "desktop")
        report["checks"].append(collect_runtime_issues(desktop_page, "dashboard-desktop"))
        save_snapshot(desktop_page, "dashboard-desktop.png")
        report["screenshots"].append(str(output_dir / "dashboard-desktop.png"))
        desktop_page.close()

        for label in ["Analyze", "Review", "Monitor", "Devices", "Sites", "Settings"]:
            desktop_page = open_page(desktop, report, "desktop")
            click_desktop_tab(desktop_page, label)
            slug = label.lower().replace(" ", "-")
            report["checks"].append(collect_runtime_issues(desktop_page, f"{slug}-desktop"))
            save_snapshot(desktop_page, f"{slug}-desktop.png")
            report["screenshots"].append(str(output_dir / f"{slug}-desktop.png"))
            desktop_page.close()

        mobile = browser.new_context(viewport={"width": 393, "height": 852})
        mobile_page = open_page(mobile, report, "mobile")
        report["checks"].append(collect_runtime_issues(mobile_page, "dashboard-mobile"))
        save_snapshot(mobile_page, "dashboard-mobile.png")
        report["screenshots"].append(str(output_dir / "dashboard-mobile.png"))
        mobile_page.close()

        for label in ["Analyze", "Review", "Monitor"]:
            mobile_page = open_page(mobile, report, "mobile")
            click_mobile_primary_tab(mobile_page, label)
            slug = label.lower().replace(" ", "-")
            report["checks"].append(collect_runtime_issues(mobile_page, f"{slug}-mobile"))
            save_snapshot(mobile_page, f"{slug}-mobile.png")
            report["screenshots"].append(str(output_dir / f"{slug}-mobile.png"))
            mobile_page.close()

        mobile_page = open_page(mobile, report, "mobile")
        mobile_page.get_by_role("button", name="More").click()
        mobile_page.get_by_text("Field workspace").wait_for(timeout=10000)
        report["checks"].append(collect_runtime_issues(mobile_page, "more-sheet-mobile"))
        save_snapshot(mobile_page, "more-sheet-mobile.png")
        report["screenshots"].append(str(output_dir / "more-sheet-mobile.png"))
        mobile_page.close()

        for label in ["Devices", "Sites", "Settings"]:
            mobile_page = open_page(mobile, report, "mobile")
            mobile_page.get_by_role("button", name="More").click()
            mobile_page.get_by_text("Field workspace").wait_for(timeout=10000)
            try:
                click_more_sheet_tab(mobile_page, label)
            except Error:
                mobile_page.get_by_text(label, exact=True).click()
            mobile_page.wait_for_load_state("networkidle")
            slug = label.lower().replace(" ", "-")
            report["checks"].append(collect_runtime_issues(mobile_page, f"{slug}-mobile"))
            save_snapshot(mobile_page, f"{slug}-mobile.png")
            report["screenshots"].append(str(output_dir / f"{slug}-mobile.png"))
            mobile_page.close()

        desktop.close()
        mobile.close()
        browser.close()

    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
