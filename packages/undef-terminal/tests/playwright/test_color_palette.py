#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Playwright E2E tests: 256-color and truecolor palette rendering in xterm.js.

Proves ANSI 256-color and truecolor escape sequences survive the full pipeline:
  Worker (raw ANSI text) → TermHub WS → Browser WS → xterm.js renderer

Each test sends a color palette as raw ANSI escape sequences through a live
TermHub server, waits for xterm.js to render it in the browser, then captures
a screenshot for visual verification.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from collections.abc import Generator
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from playwright.sync_api import Page

from undef.terminal.control_channel import encode_control
from undef.terminal.hijack.hub import TermHub

# ---------------------------------------------------------------------------
# ANSI palette generators
# ---------------------------------------------------------------------------

_XTERM_CDN = "https://cdn.jsdelivr.net/npm/@xterm/xterm@6.0.0"
_FIT_CDN = "https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.11.0"

_SCREENSHOTS_DIR = Path("packages/undef-terminal/tests/playwright/screenshots")


_16_NAMES = [
    "black",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "white",
    "bright black",
    "bright red",
    "bright green",
    "bright yellow",
    "bright blue",
    "bright magenta",
    "bright cyan",
    "bright white",
]


def _build_16_color_palette() -> str:
    """Build a 16-color palette using standard SGR codes (30-37, 40-47, 90-97, 100-107)."""
    lines: list[str] = []
    lines.append("\x1b[1;37m 16-Color Palette (Standard SGR)\x1b[0m\r\n\r\n")

    # Foreground colors (text on dark background)
    lines.append(" Foreground:\r\n")
    row = " "
    for code in range(30, 38):
        row += f"\x1b[{code}m {_16_NAMES[code - 30]:>7s} \x1b[0m"
    lines.append(f"{row}\r\n")
    row = " "
    for code in range(90, 98):
        row += f"\x1b[{code}m {_16_NAMES[code - 82]:>7s} \x1b[0m"
    lines.append(f"{row}\r\n\r\n")

    # Background colors (white text on colored background)
    lines.append(" Background:\r\n")
    row = " "
    for code in range(40, 48):
        row += f"\x1b[{code};37m {_16_NAMES[code - 40]:>7s} \x1b[0m"
    lines.append(f"{row}\r\n")
    row = " "
    for code in range(100, 108):
        row += f"\x1b[{code};30m {_16_NAMES[code - 92]:>7s} \x1b[0m"
    lines.append(f"{row}\r\n\r\n")

    # Attributes (bold, underline, blink, reverse)
    lines.append(" Attributes:\r\n")
    lines.append(" \x1b[1mBold\x1b[0m  \x1b[4mUnderline\x1b[0m  \x1b[5mBlink\x1b[0m  \x1b[7mReverse\x1b[0m")
    lines.append("  \x1b[1;31mBold Red\x1b[0m  \x1b[4;32mUnder Green\x1b[0m  \x1b[7;34mRev Blue\x1b[0m\r\n")

    return "".join(lines)


def _build_256_color_palette() -> str:
    """Build a 256-color palette using SGR 38;5;N (fg) and 48;5;N (bg) codes."""
    lines: list[str] = []
    lines.append("\x1b[1;37m 256-Color Palette (ESC[48;5;Nm)\x1b[0m\r\n\r\n")

    # Standard 0-7
    row = ""
    for n in range(8):
        row += f"\x1b[48;5;{n}m  \x1b[0m"
    lines.append(f" {row}  standard 0-7\r\n")

    # Bright 8-15
    row = ""
    for n in range(8, 16):
        row += f"\x1b[48;5;{n}m  \x1b[0m"
    lines.append(f" {row}  bright 8-15\r\n\r\n")

    # 216-color cube (16-231) in 6 rows of 36
    for block in range(6):
        row = ""
        for i in range(36):
            n = 16 + block * 36 + i
            row += f"\x1b[48;5;{n}m \x1b[0m"
        lines.append(f" {row}\r\n")
    lines.append("\r\n")

    # Grayscale 232-255
    row = ""
    for n in range(232, 256):
        row += f"\x1b[48;5;{n}m  \x1b[0m"
    lines.append(f" {row}  grayscale\r\n\r\n")

    # Foreground text samples (38;5;N)
    lines.append(" \x1b[1;37mForeground text (ESC[38;5;Nm):\x1b[0m\r\n")
    lines.extend(
        f" \x1b[38;5;{n}m Color {n:>3d}: The quick brown fox \x1b[0m\r\n" for n in [196, 208, 220, 46, 51, 21, 93, 201]
    )

    return "".join(lines)


def _build_truecolor_palette() -> str:
    """Build a truecolor gradient using SGR 48;2;R;G;B (background) codes."""
    lines: list[str] = []
    width = 64

    lines.append("\r\n\x1b[1;37m Truecolor Palette (ESC[48;2;R;G;Bm)\x1b[0m\r\n\r\n")

    # Red gradient
    row = ""
    for i in range(width):
        r = int(i * 255 / (width - 1))
        row += f"\x1b[48;2;{r};0;0m \x1b[0m"
    lines.append(f" {row} red\r\n")

    # Green gradient
    row = ""
    for i in range(width):
        g = int(i * 255 / (width - 1))
        row += f"\x1b[48;2;0;{g};0m \x1b[0m"
    lines.append(f" {row} green\r\n")

    # Blue gradient
    row = ""
    for i in range(width):
        b = int(i * 255 / (width - 1))
        row += f"\x1b[48;2;0;0;{b}m \x1b[0m"
    lines.append(f" {row} blue\r\n")

    # Rainbow (hue sweep)
    row = ""
    for i in range(width):
        hue = i / width
        h = hue * 6
        c = 255
        x = int(255 * (1 - abs(h % 2 - 1)))
        if h < 1:
            r, g, b = c, x, 0
        elif h < 2:
            r, g, b = x, c, 0
        elif h < 3:
            r, g, b = 0, c, x
        elif h < 4:
            r, g, b = 0, x, c
        elif h < 5:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x
        row += f"\x1b[48;2;{r};{g};{b}m \x1b[0m"
    lines.append(f" {row} rainbow\r\n")

    # Grayscale gradient
    row = ""
    for i in range(width):
        v = int(i * 255 / (width - 1))
        row += f"\x1b[48;2;{v};{v};{v}m \x1b[0m"
    lines.append(f" {row} grayscale\r\n")

    return "".join(lines)


# ---------------------------------------------------------------------------
# Color palette worker — sends ANSI data through TermHub
# ---------------------------------------------------------------------------


class ColorWorker:
    """Background-thread worker that connects to TermHub and sends ANSI color data.

    Sends data in a loop (once per second) so the browser always receives it,
    regardless of when it connects.
    """

    def __init__(self, base_url: str, worker_id: str, ansi_data: str) -> None:
        self._base_url = base_url
        self._worker_id = worker_id
        self._ansi_data = ansi_data
        self._connected = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> ColorWorker:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if not self._connected.wait(timeout=5.0):
            raise RuntimeError(f"ColorWorker: worker {self._worker_id!r} failed to connect")
        return self

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._connect())
        finally:
            loop.close()

    async def _connect(self) -> None:
        import websockets

        ws_url = self._base_url.replace("http://", "ws://") + f"/ws/worker/{self._worker_id}/term"
        try:
            async with websockets.connect(ws_url) as ws:
                self._connected.set()

                # Send initial snapshot with the palette embedded
                snapshot = {
                    "type": "snapshot",
                    "screen": self._ansi_data,
                    "cursor": {"x": 0, "y": 0},
                    "cols": 120,
                    "rows": 40,
                    "screen_hash": "color-palette",
                    "cursor_at_end": True,
                    "has_trailing_space": False,
                    "ts": time.time(),
                }
                await ws.send(encode_control(snapshot))

                # Also send as raw terminal data for live rendering.
                # Repeat periodically so browsers connecting later still get it.
                send_count = 0
                while not self._stop.is_set():
                    if send_count < 5:
                        await ws.send(self._ansi_data)
                        send_count += 1
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=0.5)
                    except TimeoutError:
                        continue
                    except Exception:
                        break
        except Exception:
            self._connected.set()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)


# ---------------------------------------------------------------------------
# Test page HTML — minimal xterm.js terminal with direct WS to TermHub
# ---------------------------------------------------------------------------


def _color_test_html(worker_id: str) -> str:
    """Generate a minimal HTML page that creates xterm.js and connects to TermHub.

    Uses the TermHub browser WS endpoint directly (no hijack widget).
    Decodes the control channel framing (DLE+STX) to extract terminal data.
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Color Palette Test</title>
  <link rel="stylesheet" href="{_XTERM_CDN}/css/xterm.css">
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    html, body {{ width: 100%; height: 100vh; background: #0b0f14; }}
    #term {{ width: 100%; height: 100%; }}
  </style>
</head>
<body>
<div id="term"></div>
<script src="{_XTERM_CDN}/lib/xterm.js"></script>
<script src="{_FIT_CDN}/lib/addon-fit.js"></script>
<script>
(function() {{
  var DLE = "\\x10", STX = "\\x02";
  var term = new Terminal({{ rows: 40, cols: 120, convertEol: false }});
  term.open(document.getElementById("term"));
  var fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  try {{ fit.fit(); }} catch(e) {{}}
  window._term = term;
  window._colorDataReceived = false;

  // Connect to TermHub browser WS
  var proto = location.protocol === "https:" ? "wss:" : "ws:";
  var wsUrl = proto + "//" + location.host + "/ws/browser/{worker_id}/term";
  var ws = new WebSocket(wsUrl);

  ws.onmessage = function(event) {{
    var raw = event.data;
    // Parse control channel framing: DLE+STX+8hex+':'+JSON, or plain data
    var pos = 0;
    while (pos < raw.length) {{
      if (raw[pos] === DLE && pos + 1 < raw.length && raw[pos+1] === STX) {{
        // Control frame: DLE STX <8 hex digits> : <json>
        var lenHex = raw.substring(pos + 2, pos + 10);
        var jsonLen = parseInt(lenHex, 16);
        var jsonStart = pos + 11; // after ':'
        var jsonStr = raw.substring(jsonStart, jsonStart + jsonLen);
        try {{
          var msg = JSON.parse(jsonStr);
          if (msg.type === "term" && msg.data) {{
            term.write(msg.data);
            window._colorDataReceived = true;
          }} else if (msg.type === "snapshot" && msg.screen) {{
            term.write(msg.screen.replace(/\\n/g, "\\r\\n"));
            window._colorDataReceived = true;
          }}
        }} catch(e) {{}}
        pos = jsonStart + jsonLen;
      }} else {{
        // Raw data chunk — find next DLE or end
        var next = raw.indexOf(DLE, pos + 1);
        if (next === -1) next = raw.length;
        var chunk = raw.substring(pos, next);
        if (chunk) {{
          term.write(chunk);
          window._colorDataReceived = true;
        }}
        pos = next;
      }}
    }}
  }};

  ws.onopen = function() {{
    window._wsConnected = true;
    console.log("WS connected to " + wsUrl);
  }};
  ws.onerror = function(e) {{ console.error("WS error", e); }};
}})();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Server fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def color_server() -> Generator[str, None, None]:
    """Module-scoped server with TermHub and xterm.js color test page."""
    hub = TermHub(resolve_browser_role=lambda _ws, _worker_id: "admin")
    app = FastAPI()
    app.include_router(hub.create_router())

    @app.get("/color-test/{worker_id}", response_class=HTMLResponse)
    async def color_test_page(worker_id: str) -> str:
        return _color_test_html(worker_id)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="critical")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 10.0
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("color_server: uvicorn failed to start within 10 s")
        time.sleep(0.05)

    base_url = f"http://127.0.0.1:{port}"
    yield base_url

    server.should_exit = True
    thread.join(timeout=5)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wait_for_color_data(page: Page) -> None:
    """Wait for xterm.js to receive and render color data."""
    page.wait_for_selector(".xterm-rows", timeout=10000)
    page.wait_for_function("window._colorDataReceived === true", timeout=15000)
    # Extra time for DOM rendering
    page.wait_for_timeout(500)


def _assert_has_colored_spans(page: Page) -> None:
    """Assert that the xterm DOM contains styled spans (proof of color rendering).

    xterm.js DOM renderer uses two mechanisms:
    - 256-color: CSS classes like ``xterm-fg-196``, ``xterm-bg-42``
    - Truecolor: inline ``style="background-color:#rrggbb"``
    """
    colored = page.evaluate("""() => {
        const rows = document.querySelector('.xterm-rows');
        if (!rows) return 0;
        const spans = rows.querySelectorAll('span');
        let count = 0;
        for (const s of spans) {
            // Truecolor: inline style
            if (s.style.backgroundColor || s.style.color) { count++; continue; }
            // 256-color: CSS class xterm-fg-N or xterm-bg-N
            if (/xterm-(fg|bg)-\\d+/.test(s.className)) { count++; continue; }
        }
        return count;
    }""")
    assert colored > 0, f"Expected colored spans in xterm DOM, found {colored}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestColorPalette16:
    """Verify standard 16-color ANSI sequences render in xterm.js through TermHub."""

    def test_16_color_palette_screenshot(self, page: Page, color_server: str) -> None:
        """Send 16-color palette through TermHub -> browser xterm.js, capture screenshot."""
        worker_id = f"color16-{int(time.time() * 1000) % 100000}"
        palette = _build_16_color_palette()
        worker = ColorWorker(color_server, worker_id, palette).start()

        try:
            page.goto(f"{color_server}/color-test/{worker_id}", wait_until="domcontentloaded")
            _wait_for_color_data(page)
            _assert_has_colored_spans(page)

            _SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(_SCREENSHOTS_DIR / "16-color-palette.png"), full_page=True)
        finally:
            worker.stop()


class TestColorPalette256:
    """Verify 256-color ANSI sequences render in xterm.js through TermHub."""

    def test_256_color_palette_screenshot(self, page: Page, color_server: str) -> None:
        """Send 256-color palette through TermHub -> browser xterm.js, capture screenshot."""
        worker_id = f"color256-{int(time.time() * 1000) % 100000}"
        palette = _build_256_color_palette()
        worker = ColorWorker(color_server, worker_id, palette).start()

        try:
            page.goto(f"{color_server}/color-test/{worker_id}", wait_until="domcontentloaded")
            _wait_for_color_data(page)
            _assert_has_colored_spans(page)

            _SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(_SCREENSHOTS_DIR / "256-color-palette.png"), full_page=True)
        finally:
            worker.stop()


class TestColorPaletteTruecolor:
    """Verify truecolor (24-bit) ANSI sequences render in xterm.js through TermHub."""

    def test_truecolor_palette_screenshot(self, page: Page, color_server: str) -> None:
        """Send truecolor gradients through TermHub -> browser xterm.js, capture screenshot."""
        worker_id = f"truecolor-{int(time.time() * 1000) % 100000}"
        palette = _build_truecolor_palette()
        worker = ColorWorker(color_server, worker_id, palette).start()

        try:
            page.goto(f"{color_server}/color-test/{worker_id}", wait_until="domcontentloaded")
            _wait_for_color_data(page)
            _assert_has_colored_spans(page)

            _SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(_SCREENSHOTS_DIR / "truecolor-palette.png"), full_page=True)
        finally:
            worker.stop()


class TestColorPaletteCombined:
    """Verify 16-color, 256-color, and truecolor in a single terminal session."""

    def test_combined_palette_screenshot(self, page: Page, color_server: str) -> None:
        """Send all palettes through TermHub -> browser xterm.js, capture screenshot."""
        worker_id = f"combined-{int(time.time() * 1000) % 100000}"
        palette = _build_16_color_palette() + _build_256_color_palette() + _build_truecolor_palette()
        worker = ColorWorker(color_server, worker_id, palette).start()

        try:
            page.goto(f"{color_server}/color-test/{worker_id}", wait_until="domcontentloaded")
            _wait_for_color_data(page)
            _assert_has_colored_spans(page)

            _SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(_SCREENSHOTS_DIR / "combined-color-palette.png"), full_page=True)
        finally:
            worker.stop()
