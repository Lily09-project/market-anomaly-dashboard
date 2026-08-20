from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit


PAGE_CONTRACTS = {
    "stocks": ("股票分析", "大盤指數"),
    "radar": ("市場雷達", "研究優先序"),
    "anomalies": ("異常偵測展示", "異常偵測展示代號"),
    "compare": ("研究快照比較", "基準快照", "目前快照"),
}
PAGE_LOAD_STATE = "domcontentloaded"


def missing_page_contracts(route: str, body_text: str) -> list[str]:
    """Return stable page-level content requirements for browser smoke QA."""
    requirements = PAGE_CONTRACTS.get(route)
    if requirements is None:
        return ["unknown route"]
    return [required for required in requirements if required not in body_text]


def check_health(base_url: str) -> None:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("UI QA URL must use http(s) with a host")
    health_url = f"{base_url.rstrip('/')}/_stcore/health"
    # The scheme and host are allow-listed before this call.
    with urllib.request.urlopen(health_url, timeout=5) as response:  # nosec B310
        body = response.read(4096).decode("utf-8", errors="replace")
    if "ok" not in body.lower():
        raise RuntimeError(f"Streamlit health check returned unexpected body: {body[:200]}")


def run_browser_checks(base_url: str, screenshot_dir: Path) -> str:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "SKIP: install requirements-e2e.txt to run browser-level checks"

    screenshot_dir.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for name, width, height in (("desktop", 1440, 1000), ("mobile", 390, 844)):
            for route in PAGE_CONTRACTS:
                page = browser.new_page(viewport={"width": width, "height": height})
                console_errors: list[str] = []
                page.on(
                    "console",
                    lambda message, errors=console_errors: errors.append(message.text)
                    if message.type == "error"
                    else None,
                )
                page.on("pageerror", lambda error, errors=console_errors: errors.append(str(error)))
                try:
                    page.goto(
                        f"{base_url.rstrip('/')}/?page={route}",
                        wait_until=PAGE_LOAD_STATE,
                        timeout=60_000,
                    )
                    page.wait_for_timeout(500)
                    body_text = ""
                    for _attempt in range(30):
                        body_text = page.locator("body").inner_text()
                        if not missing_page_contracts(route, body_text):
                            break
                        page.wait_for_timeout(500)
                    missing = missing_page_contracts(route, body_text)
                    if missing:
                        failures.append(f"{name}/{route}: missing content {missing}")
                    overflow = page.evaluate(
                        "document.documentElement.scrollWidth - window.innerWidth"
                    )
                    if overflow > 4:
                        failures.append(f"{name}/{route}: horizontal overflow is {overflow}px")
                    if console_errors:
                        failures.append(f"{name}/{route}: console errors: {console_errors[:3]}")
                    page.screenshot(
                        path=str(screenshot_dir / f"{route}-{name}.png"),
                        full_page=True,
                    )
                except PlaywrightError as exc:
                    failures.append(f"{name}/{route}: browser error: {exc}")
                finally:
                    page.close()
        browser.close()
    if failures:
        raise RuntimeError("; ".join(failures[:12]))
    return "PASS: four-page rendering, responsive overflow, and console checks"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local Streamlit UI smoke checks.")
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--screenshots", default="docs/screenshots/ui-qa")
    args = parser.parse_args()
    try:
        check_health(args.url)
        result = run_browser_checks(args.url, Path(args.screenshots))
    except (OSError, urllib.error.URLError, RuntimeError) as exc:
        print(f"FAIL: {exc}")
        return 1
    print(json.dumps({"health": "PASS", "browser": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
