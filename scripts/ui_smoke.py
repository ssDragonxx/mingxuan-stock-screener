"""Optional browser smoke test (requires Playwright).

    pip install playwright
    python -m playwright install chromium
    python scripts/ui_smoke.py [base_url]
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright is not installed. Run: pip install playwright && python -m playwright install chromium")
    sys.exit(2)

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")


def main() -> int:
    errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        page.on(
            "console",
            lambda message: errors.append(f"console {message.type}: {message.text}")
            if message.type in ("error", "warning")
            else None,
        )
        page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))

        page.goto(BASE, wait_until="networkidle")
        page.locator("#parseBtn").click()
        page.wait_for_selector("#view-workbench", state="visible", timeout=15000)
        page.wait_for_timeout(1000)
        page.locator("#screenBtn").click()
        page.wait_for_selector("#view-results", state="visible", timeout=30000)
        page.wait_for_selector("#view-results tbody tr", timeout=15000)
        page.locator("#view-results tbody tr").first.click()
        page.wait_for_selector("#drawer", state="visible", timeout=5000)
        title = page.locator(".drawer-title h2").inner_text()
        print("drawer:", title)
        Path("data").mkdir(exist_ok=True)
        page.screenshot(path=str(Path("data") / "ui_smoke.png"), full_page=True)
        browser.close()

    print("console errors:", errors[:10])
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
