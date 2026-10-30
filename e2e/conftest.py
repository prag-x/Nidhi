"""Browser end-to-end tests. Start the API (port 8000) and the web app (port 5173) with the demo data first.

    pip install playwright pytest      (already in backend/requirements-dev.txt)
    python -m pytest -q e2e

The tests use your installed Google Chrome. To use another Chromium build set NIDHI_E2E_CHROME to its path,
or run `python -m playwright install chromium` once. NIDHI_E2E_URL overrides the app address.
"""

import contextlib
import os
import re

import pytest
from playwright.sync_api import Page, sync_playwright

BASE = os.environ.get("NIDHI_E2E_URL", "http://localhost:5173").rstrip("/")
PASSWORD = "Demo@2026"


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("NIDHI_E2E_CHROME")
        if exe:
            b = pw.chromium.launch(executable_path=exe)
        else:
            try:
                b = pw.chromium.launch(channel="chrome")
            except Exception:  # noqa: BLE001 - fall back to Playwright's own Chromium
                b = pw.chromium.launch()
        yield b
        b.close()


class Session:
    """A signed-in browser tab that records page errors and failed API calls."""

    def __init__(self, page: Page):
        self.page, self.errors = page, []
        page.on("pageerror", lambda e: self.errors.append(f"page error: {e}"))
        page.on("response", lambda r: self.errors.append(f"{r.status} {r.url}")
                if "/api/" in r.url and r.status >= 500 else None)

    def go(self, path: str):
        self.page.goto(BASE + path)
        self.settle()
        return self.page

    def settle(self, ms: int = 600):
        # The live-update stream can keep the network busy, so networkidle may never come.
        with contextlib.suppress(Exception):
            self.page.wait_for_load_state("networkidle", timeout=15000)
        self.page.wait_for_timeout(ms)

    def text(self) -> str:
        return self.page.inner_text("body")


@pytest.fixture
def signin(browser):
    contexts = []

    def _signin(handle: str) -> Session:
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        contexts.append(ctx)
        s = Session(ctx.new_page())
        s.page.goto(f"{BASE}/login")
        s.page.fill("input[type=email]", f"{handle}@nidhi.test")
        s.page.fill("input[type=password]", PASSWORD)
        s.page.click("button[type=submit]")
        s.page.wait_for_url(re.compile(r"^(?!.*login).*$"), timeout=20000)
        s.settle()
        return s

    yield _signin
    for c in contexts:
        c.close()


@pytest.fixture
def anon(browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    yield Session(ctx.new_page())
    ctx.close()
