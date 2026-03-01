#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Playwright smoke tests for the UndefHijack widget.

Requires playwright + a browser install:
    uv add --dev pytest-playwright
    uv run playwright install chromium

Skipped automatically when playwright is not installed.
"""

from __future__ import annotations

import subprocess
import sys
import time

import pytest

playwright = pytest.importorskip("playwright", reason="playwright not installed")

from playwright.sync_api import Page, sync_playwright  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DEMO_PORT = 18765
DEMO_URL = f"http://127.0.0.1:{DEMO_PORT}"


@pytest.fixture(scope="module")
def demo_server():
    """Start the demo_server.py subprocess and wait for it to be ready."""
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "scripts.demo_server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(DEMO_PORT),
        ],
        cwd=str(pytest.importorskip("pathlib").Path(__file__).parent.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Give the server a moment to start
    time.sleep(1.5)
    yield proc
    proc.terminate()
    proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_mobile_keys_toolbar_button_present(demo_server) -> None:  # noqa: ANN001
    """⌨ toggle button must be visible in the hijack widget toolbar."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page: Page = browser.new_page()
        page.goto(f"{DEMO_URL}/hijack/hijack.html?bot=testbot")
        # Wait for the widget DOM to be built
        page.wait_for_selector("#app", timeout=5000)
        # The keyboard toggle button carries title="Mobile key toolbar"
        btn = page.locator('button[title="Mobile key toolbar"]')
        assert btn.count() == 1, "⌨ mobile-keys toggle button not found in toolbar"
        browser.close()


def test_mobile_keys_row_hidden_before_hijack(demo_server) -> None:  # noqa: ANN001
    """The .mobile-keys row must not be visible before the hijack is acquired."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page: Page = browser.new_page()
        page.goto(f"{DEMO_URL}/hijack/hijack.html?bot=testbot")
        page.wait_for_selector("#app", timeout=5000)

        # Click the ⌨ toggle
        btn = page.locator('button[title="Mobile key toolbar"]')
        btn.click()

        # The row should NOT be visible yet (hijack not acquired)
        row = page.locator(".mobile-keys")
        assert not row.is_visible(), ".mobile-keys row must not be visible before hijack is acquired"
        browser.close()
