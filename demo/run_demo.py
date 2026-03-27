#!/usr/bin/env python3
"""
Live SSE + Webhook demo with multiple headed browsers and real telnet sessions.

Starts a undef-terminal FastAPI server, spins up two telnet echo backends,
opens four headed Playwright browser windows (three watching SSE from the same
telnet session to prove fanout, one watching a separate shell session to prove
isolation), then drives data through both sessions and captures screenshots.

Run:
    uv run python demo/run_demo.py
"""

from __future__ import annotations

import asyncio
import json
import socketserver
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from playwright.async_api import async_playwright

# ---------------------------------------------------------------------------
# Path setup — allow importing from repo src trees
# ---------------------------------------------------------------------------

REPO = Path(__file__).resolve().parents[1]
for _p in [
    REPO / "packages/undef-terminal/src",
    REPO / "packages/undef-terminal/tests",
    REPO / "packages/undef-shell/src",
]:
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from undef.terminal.control_channel import encode_control  # noqa: E402
from undef.terminal.server.app import create_server_app  # noqa: E402
from undef.terminal.server.config import config_from_mapping  # noqa: E402
from undef.terminal.transports.telnet_server import _build_telnet_handshake  # noqa: E402  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Telnet echo server
# ---------------------------------------------------------------------------


class _EchoHandler(socketserver.BaseRequestHandler):
    """Telnet echo server: handshake → welcome banner → echo everything back."""

    session_label: str = "?"

    def handle(self) -> None:
        self.request.sendall(_build_telnet_handshake())
        self.request.sendall(f"[{self.server.session_label}] TELNET ECHO READY\r\n".encode())  # type: ignore[attr-defined]
        while True:
            data = self.request.recv(4096)
            if not data:
                return
            self.request.sendall(data)


class _TelnetEchoServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self, addr: tuple[str, int], session_label: str) -> None:
        self.session_label = session_label
        super().__init__(addr, _EchoHandler)


# ---------------------------------------------------------------------------
# Static HTML file server (serves sse_viewer.html)
# ---------------------------------------------------------------------------

DEMO_DIR = Path(__file__).parent


class _StaticHandler(BaseHTTPRequestHandler):
    def log_message(self, *_: Any) -> None:
        pass  # silence

    def do_GET(self) -> None:
        path = DEMO_DIR / "sse_viewer.html"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


# ---------------------------------------------------------------------------
# Control-channel frame builders
# ---------------------------------------------------------------------------


def _snapshot(screen: str, ts: float | None = None) -> str:
    return encode_control(
        {
            "type": "snapshot",
            "screen": screen,
            "cursor": {"x": len(screen), "y": 0},
            "cols": 80,
            "rows": 25,
            "screen_hash": f"demo-{hash(screen) & 0xFFFF:04x}",
            "cursor_at_end": True,
            "has_trailing_space": False,
            "prompt_detected": {"prompt_id": "demo"},
            "ts": ts or time.time(),
        }
    )


def _term(text: str) -> str:
    return encode_control({"type": "term", "data": text, "ts": time.time()})


# ---------------------------------------------------------------------------
# Demo driver (async)
# ---------------------------------------------------------------------------


async def drive_demo(base_url: str, _pages: list[Any], webhook_hits: list[dict]) -> None:
    """Run the demo scenarios after browsers are open."""
    import websockets

    ws_base = base_url.replace("http://", "ws://")

    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as http:
        # ── Scenario 1: three browsers watch "telnet-alpha", one watches "shell-beta"
        print("\n[demo] Scenario 1 — three browsers on telnet-alpha, one on shell-beta")

        # Register a webhook on telnet-alpha so we can prove delivery
        wh = (
            await http.post(
                "/api/sessions/telnet-alpha/webhooks",
                json={"url": "http://127.0.0.1:9988/hook", "event_types": ["snapshot"]},
            )
        ).json()
        print(f"[demo]   webhook registered: {wh['webhook_id'][:8]}…")

        await asyncio.sleep(0.5)

        # ── Connect telnet-alpha worker and fire three snapshots
        print("[demo] Connecting worker WS for telnet-alpha…")
        async with websockets.connect(f"{ws_base}/ws/worker/telnet-alpha/term") as ws:
            # drain snapshot_req
            with __import__("contextlib").suppress(Exception):
                await asyncio.wait_for(ws.recv(), timeout=1.0)

            for i, cmd in enumerate(["ls -la", "ps aux | head -5", "echo 'SSE fanout works!'"]):
                screen = f"$ {cmd}\n(output line {i + 1} from telnet-alpha)"
                await ws.send(_snapshot(screen))
                await asyncio.sleep(0.6)
                print(f"[demo]   sent snapshot #{i + 1}: {cmd!r}")

            # Also send a raw term frame
            await ws.send(_term("\x1b[32mGREEN TEXT\x1b[0m\r\n"))
            await asyncio.sleep(0.4)

        await asyncio.sleep(1.0)

        # ── Scenario 2: shell-beta gets its own snapshots — browsers watching alpha see nothing
        print("\n[demo] Scenario 2 — shell-beta isolation")
        async with websockets.connect(f"{ws_base}/ws/worker/shell-beta/term") as ws:
            with __import__("contextlib").suppress(Exception):
                await asyncio.wait_for(ws.recv(), timeout=1.0)

            await ws.send(_snapshot("$ echo 'only shell-beta browsers see this'"))
            await asyncio.sleep(0.6)
            await ws.send(_snapshot("$ python3 -c \"print('hello from shell-beta')\""))
            await asyncio.sleep(0.6)
            print("[demo]   sent 2 snapshots to shell-beta")

        await asyncio.sleep(1.0)

        # ── Scenario 3: second telnet session (telnet-gamma) — new worker connects
        print("\n[demo] Scenario 3 — telnet-gamma (second telnet connection)")
        async with websockets.connect(f"{ws_base}/ws/worker/telnet-gamma/term") as ws:
            with __import__("contextlib").suppress(Exception):
                await asyncio.wait_for(ws.recv(), timeout=1.0)

            await ws.send(_snapshot("$ whoami\nroot"))
            await asyncio.sleep(0.4)
            await ws.send(_snapshot("$ uptime\n 12:34:56 up 42 days, load avg 0.01 0.03 0.05"))
            await asyncio.sleep(0.4)
            print("[demo]   sent 2 snapshots to telnet-gamma")

        await asyncio.sleep(1.0)

        # ── Print webhook hit summary
        print(f"\n[demo] Webhook hits received: {len(webhook_hits)}")
        for hit in webhook_hits[:5]:
            ev = hit.get("event", {})
            print(f"[demo]   → type={ev.get('type')} session={hit.get('session_id')[:12]}…")


# ---------------------------------------------------------------------------
# Mini webhook receiver
# ---------------------------------------------------------------------------


def _start_webhook_receiver(hits: list[dict]) -> None:
    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: Any) -> None:
            pass

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            with __import__("contextlib").suppress(Exception):
                hits.append(json.loads(body))
            self.send_response(200)
            self.end_headers()

    srv = HTTPServer(("127.0.0.1", 9988), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    # Start webhook receiver
    webhook_hits: list[dict] = []
    _start_webhook_receiver(webhook_hits)

    # Start two telnet echo backends
    telnet_a = _TelnetEchoServer(("127.0.0.1", 0), "alpha")
    telnet_b = _TelnetEchoServer(("127.0.0.1", 0), "gamma")
    for srv in (telnet_a, telnet_b):
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    port_a = telnet_a.server_address[1]
    port_b = telnet_b.server_address[1]
    print(f"[demo] Telnet echo servers: alpha={port_a} gamma={port_b}")

    # Start static HTML server
    static_srv = HTTPServer(("127.0.0.1", 9987), _StaticHandler)
    threading.Thread(target=static_srv.serve_forever, daemon=True).start()
    print("[demo] Static HTML server: http://127.0.0.1:9987/")

    # Build server config with four pre-defined sessions
    cfg = config_from_mapping(
        {
            "server": {"host": "127.0.0.1", "port": 8766, "allowed_origins": ["http://127.0.0.1:9987"]},
            "auth": {"mode": "dev"},
            "sessions": [
                {
                    "session_id": "telnet-alpha",
                    "display_name": "Telnet Alpha",
                    "connector_type": "telnet",
                    "auto_start": False,
                    "connector_config": {"host": "127.0.0.1", "port": port_a},
                },
                {
                    "session_id": "shell-beta",
                    "display_name": "Shell Beta",
                    "connector_type": "shell",
                    "auto_start": False,
                },
                {
                    "session_id": "telnet-gamma",
                    "display_name": "Telnet Gamma",
                    "connector_type": "telnet",
                    "auto_start": False,
                    "connector_config": {"host": "127.0.0.1", "port": port_b},
                },
            ],
        }
    )
    app = create_server_app(cfg)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8766, log_level="warning"))
    srv_task = asyncio.create_task(server.serve())

    # Wait for server ready
    deadline = asyncio.get_running_loop().time() + 10.0
    while not server.started:
        if asyncio.get_running_loop().time() > deadline:
            raise RuntimeError("uvicorn startup timeout")
        await asyncio.sleep(0.05)
    print("[demo] FastAPI server ready: http://127.0.0.1:8766/")

    # Attach EventBus for SSE delivery
    from undef.terminal.hijack.hub import EventBus

    hub = app.state.uterm_registry._hub
    hub._event_bus = EventBus()

    # ── Open Playwright browsers ──────────────────────────────────────────────
    api = "http://127.0.0.1:8766"
    viewer = "http://127.0.0.1:9987"

    screenshots_dir = DEMO_DIR / "screenshots"
    screenshots_dir.mkdir(exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=80)

        def viewer_url(session: str, label: str) -> str:
            return f"{viewer}/?session={session}&base={api}&label={label}"

        # Open 4 contexts (each is its own browser window)
        ctx_alpha1 = await browser.new_context(viewport={"width": 900, "height": 600})
        ctx_alpha2 = await browser.new_context(viewport={"width": 900, "height": 600})
        ctx_alpha3 = await browser.new_context(viewport={"width": 900, "height": 600})
        ctx_beta = await browser.new_context(viewport={"width": 900, "height": 600})

        page_a1 = await ctx_alpha1.new_page()
        page_a2 = await ctx_alpha2.new_page()
        page_a3 = await ctx_alpha3.new_page()
        page_b = await ctx_beta.new_page()

        pages = [page_a1, page_a2, page_a3, page_b]
        labels = ["alpha-browser-1", "alpha-browser-2", "alpha-browser-3", "beta-browser"]

        # Navigate all four windows
        await asyncio.gather(
            page_a1.goto(viewer_url("telnet-alpha", "telnet-alpha [browser 1]")),
            page_a2.goto(viewer_url("telnet-alpha", "telnet-alpha [browser 2]")),
            page_a3.goto(viewer_url("telnet-alpha", "telnet-alpha [browser 3]")),
            page_b.goto(viewer_url("shell-beta", "shell-beta  [browser 4]")),
        )
        await asyncio.sleep(1.5)  # let SSE connections establish

        print("[demo] Four browser windows open. Starting event stream…")

        # Screenshot 1 — all browsers connected, no events yet
        for pg, lbl in zip(pages, labels, strict=True):
            await pg.screenshot(path=str(screenshots_dir / f"01_connected_{lbl}.png"))
        print("[demo] Screenshot 1: browsers connected (empty)")

        # ── Drive the demo ────────────────────────────────────────────────────
        await drive_demo(api, pages, webhook_hits)

        # Screenshot 2 — events visible in alpha browsers, not in beta
        await asyncio.sleep(0.5)
        for pg, lbl in zip(pages, labels, strict=True):
            await pg.screenshot(path=str(screenshots_dir / f"02_events_{lbl}.png"))
        print("[demo] Screenshot 2: events visible")

        # Open a 5th window showing telnet-gamma
        ctx_gamma = await browser.new_context(viewport={"width": 900, "height": 600})
        page_g = await ctx_gamma.new_page()
        await page_g.goto(viewer_url("telnet-gamma", "telnet-gamma [browser 5]"))
        await asyncio.sleep(1.0)
        await page_g.screenshot(path=str(screenshots_dir / "03_gamma_browser.png"))
        print("[demo] Screenshot 3: gamma session window")

        print(f"\n[demo] ✓ Screenshots saved to {screenshots_dir}/")
        print("[demo] Browsers open for 10 seconds — press Ctrl-C to quit early")
        await asyncio.sleep(10)

        await browser.close()

    server.should_exit = True
    await asyncio.wait_for(srv_task, timeout=5.0)
    print("[demo] Done.")


if __name__ == "__main__":
    asyncio.run(main())
