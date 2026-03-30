#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Playwright E2E tests: color palette and ANSI art rendering in xterm.js.

Proves ANSI escape sequences survive the full pipeline:
  Worker (raw ANSI text) → TermHub WS → Browser WS → xterm.js renderer

Each test sends ANSI data through a live TermHub server, waits for xterm.js
to render it, asserts colored DOM elements exist, and captures a screenshot.
The animation tests record short videos of animated ANSI output.
"""

from __future__ import annotations

import time

from playwright.sync_api import Page

from tests.playwright._ansi_palettes import (
    build_16_color_palette,
    build_256_color_palette,
    build_animation_frames,
    build_ansi_art,
    build_truecolor_palette,
)
from tests.playwright.conftest import (
    SCREENSHOTS_DIR,
    AnimatedWorker,
    ColorWorker,
    assert_has_colored_spans,
    wait_for_color_data,
)


def _uid() -> str:
    return str(int(time.time() * 1000) % 100000)


def _screenshot(page: Page, name: str) -> None:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SCREENSHOTS_DIR / name), full_page=True)


# ---------------------------------------------------------------------------
# Static palette tests
# ---------------------------------------------------------------------------


class TestColorPalette16:
    """Verify standard 16-color ANSI sequences render in xterm.js through TermHub."""

    def test_16_color_palette_screenshot(self, page: Page, color_server: str) -> None:
        worker_id = f"color16-{_uid()}"
        worker = ColorWorker(color_server, worker_id, build_16_color_palette()).start()
        try:
            page.goto(f"{color_server}/color-test/{worker_id}", wait_until="domcontentloaded")
            wait_for_color_data(page)
            assert_has_colored_spans(page)
            _screenshot(page, "16-color-palette.png")
        finally:
            worker.stop()


class TestColorPalette256:
    """Verify 256-color ANSI sequences render in xterm.js through TermHub."""

    def test_256_color_palette_screenshot(self, page: Page, color_server: str) -> None:
        worker_id = f"color256-{_uid()}"
        worker = ColorWorker(color_server, worker_id, build_256_color_palette()).start()
        try:
            page.goto(f"{color_server}/color-test/{worker_id}", wait_until="domcontentloaded")
            wait_for_color_data(page)
            assert_has_colored_spans(page)
            _screenshot(page, "256-color-palette.png")
        finally:
            worker.stop()


class TestColorPaletteTruecolor:
    """Verify truecolor (24-bit) ANSI sequences render in xterm.js through TermHub."""

    def test_truecolor_palette_screenshot(self, page: Page, color_server: str) -> None:
        worker_id = f"truecolor-{_uid()}"
        worker = ColorWorker(color_server, worker_id, build_truecolor_palette()).start()
        try:
            page.goto(f"{color_server}/color-test/{worker_id}", wait_until="domcontentloaded")
            wait_for_color_data(page)
            assert_has_colored_spans(page)
            _screenshot(page, "truecolor-palette.png")
        finally:
            worker.stop()


class TestAnsiArt:
    """Verify ANSI art (blocks, box drawing, flames, braille) renders in xterm.js."""

    def test_ansi_art_screenshot(self, page: Page, color_server: str) -> None:
        worker_id = f"ansiart-{_uid()}"
        worker = ColorWorker(color_server, worker_id, build_ansi_art()).start()
        try:
            page.goto(f"{color_server}/color-test/{worker_id}", wait_until="domcontentloaded")
            wait_for_color_data(page)
            assert_has_colored_spans(page)
            _screenshot(page, "ansi-art.png")
        finally:
            worker.stop()


class TestColorPaletteCombined:
    """Verify all color modes and ANSI art in a single terminal session."""

    def test_combined_palette_screenshot(self, page: Page, color_server: str) -> None:
        worker_id = f"combined-{_uid()}"
        palette = build_16_color_palette() + build_256_color_palette() + build_truecolor_palette() + build_ansi_art()
        worker = ColorWorker(color_server, worker_id, palette).start()
        try:
            page.goto(f"{color_server}/color-test/{worker_id}", wait_until="domcontentloaded")
            wait_for_color_data(page)
            assert_has_colored_spans(page)
            _screenshot(page, "combined-color-palette.png")
        finally:
            worker.stop()


# ---------------------------------------------------------------------------
# Animation tests — record short videos of animated ANSI output
# ---------------------------------------------------------------------------


class TestAnsiAnimation:
    """Verify animated ANSI output renders as video through TermHub."""

    def test_plasma_animation_video(self, page: Page, color_server: str) -> None:
        """Stream animated plasma frames, capture screenshots per frame as proof."""
        worker_id = f"anim-{_uid()}"
        frames = build_animation_frames(num_frames=20)
        worker = AnimatedWorker(color_server, worker_id, frames, fps=8).start()

        try:
            page.goto(f"{color_server}/color-test/{worker_id}", wait_until="domcontentloaded")
            wait_for_color_data(page)
            assert_has_colored_spans(page)

            # Capture a sequence of frames as proof of animation
            SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            for i in range(6):
                page.wait_for_timeout(250)
                _screenshot(page, f"animation-frame-{i:02d}.png")

            # Final frame
            _screenshot(page, "animation-final.png")
        finally:
            worker.stop()
