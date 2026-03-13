#!/usr/bin/env python
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""End-to-end walkthrough of the undef-terminal hijack lifecycle.

Starts a real server with a shell session, then drives the full REST API
through session discovery, open-mode input, hijack acquire/send/release,
quick-connect, and recording — narrating each step for human observers.

Usage:
    uv run python scripts/walkthrough.py                # full demo with browser tabs
    uv run python scripts/walkthrough.py --no-browser   # headless narration only
    uv run python scripts/walkthrough.py --port 9000    # custom port
"""

from __future__ import annotations

import argparse
import asyncio
import socket
import sys
import time
import webbrowser
from typing import Any

import httpx
import uvicorn

from undef.terminal.server.app import create_server_app
from undef.terminal.server.config import config_from_mapping

# ── Narration helpers ───────────────────────────────────────────────

_step_counter = 0


def _ts() -> str:
    return time.strftime("%H:%M:%S")


def narrate(label: str, detail: str = "") -> None:
    global _step_counter
    _step_counter += 1
    prefix = f"[{_ts()}] Step {_step_counter}: {label}"
    print(prefix)
    if detail:
        for line in detail.splitlines():
            print(f"           {line}")
    print()


def show(method: str, path: str, body: dict[str, Any] | None = None) -> None:
    parts = [f"  {method} {path}"]
    if body:
        import json

        parts.append(f"  Body: {json.dumps(body, indent=None)}")
    for p in parts:
        print(p)


def result(data: Any, *, keys: list[str] | None = None) -> None:
    if isinstance(data, dict) and keys:
        filtered = {k: data[k] for k in keys if k in data}
        print(f"  -> {filtered}")
    elif isinstance(data, list):
        print(f"  -> {len(data)} item(s)")
        for item in data[:3]:
            if isinstance(item, dict):
                sid = item.get("session_id", "")
                state = item.get("lifecycle_state", "")
                mode = item.get("input_mode", "")
                print(f"     - {sid} ({state}, {mode})")
    else:
        print(f"  -> {data}")
    print()


# ── Free port helper ────────────────────────────────────────────────


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ── Server lifecycle ────────────────────────────────────────────────


def _build_config(port: int) -> dict[str, Any]:
    return {
        "server": {
            "host": "127.0.0.1",
            "port": port,
            "public_base_url": f"http://127.0.0.1:{port}",
        },
        "auth": {"mode": "dev"},
        "recording": {"enabled_by_default": True},
        "sessions": [
            {
                "session_id": "undef-shell",
                "display_name": "Walkthrough Shell",
                "connector_type": "shell",
                "input_mode": "open",
                "auto_start": True,
                "tags": ["shell", "walkthrough"],
            }
        ],
    }


async def _start_server(port: int) -> tuple[uvicorn.Server, asyncio.Task[None]]:
    mapping = _build_config(port)
    config = config_from_mapping(mapping)
    app = create_server_app(config)
    uvi_config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(uvi_config)
    task = asyncio.create_task(server.serve())
    return server, task


async def _wait_healthy(client: httpx.AsyncClient, *, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = await client.get("/api/health")
            if r.status_code == 200 and r.json().get("ready"):
                return
        except httpx.ConnectError:
            pass
        await asyncio.sleep(0.3)
    raise TimeoutError("server did not become healthy")


# ── Walkthrough phases ──────────────────────────────────────────────

SESSION_ID = "undef-shell"


async def phase_setup(client: httpx.AsyncClient, port: int, *, open_browser: bool) -> None:
    narrate("Start server", f"dev auth, shell connector, recording=true, port={port}")

    narrate("Wait for health check")
    show("GET", "/api/health")
    r = await client.get("/api/health")
    result(r.json(), keys=["ok", "ready", "service"])

    dashboard_url = f"http://127.0.0.1:{port}/app/"
    narrate("Dashboard ready", f"URL: {dashboard_url}")
    if open_browser:
        webbrowser.open(dashboard_url)


async def phase_discovery(client: httpx.AsyncClient, port: int, *, open_browser: bool) -> None:
    narrate("List sessions")
    show("GET", "/api/sessions")
    r = await client.get("/api/sessions")
    result(r.json())

    narrate("Get session status")
    show("GET", f"/api/sessions/{SESSION_ID}")
    r = await client.get(f"/api/sessions/{SESSION_ID}")
    result(r.json(), keys=["session_id", "lifecycle_state", "input_mode", "connected"])

    operator_url = f"http://127.0.0.1:{port}/app/operator/{SESSION_ID}"
    narrate("Operator view ready", f"URL: {operator_url}")
    if open_browser:
        webbrowser.open(operator_url)


async def phase_open_mode(client: httpx.AsyncClient) -> None:
    narrate("Ensure open mode")
    show("POST", f"/api/sessions/{SESSION_ID}/mode", {"input_mode": "open"})
    r = await client.post(f"/api/sessions/{SESSION_ID}/mode", json={"input_mode": "open"})
    result(r.json(), keys=["session_id", "input_mode"])

    narrate("Read snapshot (before)")
    show("GET", f"/api/sessions/{SESSION_ID}/snapshot")
    r = await client.get(f"/api/sessions/{SESSION_ID}/snapshot")
    snap = r.json()
    if snap and isinstance(snap, dict):
        screen = snap.get("screen", "")
        lines = screen.splitlines()[-5:] if screen else ["(empty)"]
        print("  -> Last 5 lines of terminal:")
        for ln in lines:
            print(f"     | {ln}")
        print()
    else:
        result(snap)


async def phase_hijack(client: httpx.AsyncClient) -> dict[str, str]:
    narrate("Switch to hijack mode")
    show("POST", f"/api/sessions/{SESSION_ID}/mode", {"input_mode": "hijack"})
    r = await client.post(f"/api/sessions/{SESSION_ID}/mode", json={"input_mode": "hijack"})
    result(r.json(), keys=["session_id", "input_mode"])

    narrate("Acquire hijack lease")
    body = {"owner": "walkthrough", "lease_s": 60}
    show("POST", f"/worker/{SESSION_ID}/hijack/acquire", body)
    r = await client.post(f"/worker/{SESSION_ID}/hijack/acquire", json=body)
    data = r.json()
    result(data, keys=["ok", "hijack_id", "lease_expires_at", "owner"])
    hid = data["hijack_id"]

    narrate("Send command: echo 'hijacked!'")
    send_body: dict[str, Any] = {"keys": "echo 'hijacked!'\r"}
    show("POST", f"/worker/{SESSION_ID}/hijack/{hid}/send", send_body)
    r = await client.post(f"/worker/{SESSION_ID}/hijack/{hid}/send", json=send_body)
    result(r.json(), keys=["ok", "sent"])

    narrate("Wait for shell to process")
    await asyncio.sleep(1.5)

    narrate("Read hijack snapshot")
    show("GET", f"/worker/{SESSION_ID}/hijack/{hid}/snapshot")
    r = await client.get(f"/worker/{SESSION_ID}/hijack/{hid}/snapshot")
    snap = r.json()
    screen = (snap.get("snapshot") or {}).get("screen", "") if isinstance(snap, dict) else ""
    if screen:
        lines = screen.splitlines()[-8:]
        print("  -> Terminal output:")
        for ln in lines:
            print(f"     | {ln}")
        print()
    else:
        result(snap)

    narrate("Send command: date")
    send_body = {"keys": "date\r"}
    show("POST", f"/worker/{SESSION_ID}/hijack/{hid}/send", send_body)
    r = await client.post(f"/worker/{SESSION_ID}/hijack/{hid}/send", json=send_body)
    result(r.json(), keys=["ok", "sent"])

    await asyncio.sleep(1.5)

    narrate("Read updated snapshot")
    show("GET", f"/worker/{SESSION_ID}/hijack/{hid}/snapshot")
    r = await client.get(f"/worker/{SESSION_ID}/hijack/{hid}/snapshot")
    snap = r.json()
    screen = (snap.get("snapshot") or {}).get("screen", "") if isinstance(snap, dict) else ""
    if screen:
        lines = screen.splitlines()[-8:]
        print("  -> Terminal output:")
        for ln in lines:
            print(f"     | {ln}")
        print()

    narrate("Heartbeat — extend lease")
    show("POST", f"/worker/{SESSION_ID}/hijack/{hid}/heartbeat", {"lease_s": 60})
    r = await client.post(f"/worker/{SESSION_ID}/hijack/{hid}/heartbeat", json={"lease_s": 60})
    result(r.json(), keys=["ok", "lease_expires_at"])

    narrate("Read hijack events")
    show("GET", f"/worker/{SESSION_ID}/hijack/{hid}/events")
    r = await client.get(f"/worker/{SESSION_ID}/hijack/{hid}/events")
    events_data = r.json()
    events_list = events_data.get("events", []) if isinstance(events_data, dict) else []
    print(f"  -> {len(events_list)} event(s)")
    for ev in events_list[:5]:
        print(f"     - {ev.get('type', '?')}: {ev.get('data', {})}")
    print()

    return {"hijack_id": hid}


async def phase_release(client: httpx.AsyncClient, hid: str) -> None:
    narrate("Release hijack lease")
    show("POST", f"/worker/{SESSION_ID}/hijack/{hid}/release")
    r = await client.post(f"/worker/{SESSION_ID}/hijack/{hid}/release")
    result(r.json(), keys=["ok", "worker_id", "hijack_id"])

    narrate("Verify session after release")
    show("GET", f"/api/sessions/{SESSION_ID}")
    r = await client.get(f"/api/sessions/{SESSION_ID}")
    result(r.json(), keys=["session_id", "lifecycle_state", "input_mode"])

    narrate("Check recording entries")
    show("GET", f"/api/sessions/{SESSION_ID}/recording/entries?limit=10")
    r = await client.get(f"/api/sessions/{SESSION_ID}/recording/entries", params={"limit": 10})
    entries = r.json() if r.status_code == 200 else []
    if isinstance(entries, list) and entries:
        print(f"  -> {len(entries)} recording entries")
        for entry in entries[:3]:
            etype = entry.get("event", "?")
            print(f"     - {etype}")
    else:
        print("  -> (no recording entries yet)")
    print()


async def phase_quick_connect(client: httpx.AsyncClient) -> None:
    narrate("Create ephemeral session (quick-connect)")
    body: dict[str, Any] = {"connector_type": "shell", "display_name": "Ephemeral Shell"}
    show("POST", "/api/connect", body)
    r = await client.post("/api/connect", json=body)
    data = r.json()
    result(data, keys=["session_id", "url"])

    narrate("List sessions — should show 2")
    show("GET", "/api/sessions")
    r = await client.get("/api/sessions")
    result(r.json())


async def phase_events_and_metrics(client: httpx.AsyncClient) -> None:
    narrate("Session event log")
    show("GET", f"/api/sessions/{SESSION_ID}/events?limit=10")
    r = await client.get(f"/api/sessions/{SESSION_ID}/events", params={"limit": 10})
    events = r.json() if r.status_code == 200 else []
    if isinstance(events, list):
        print(f"  -> {len(events)} event(s)")
        for ev in events[:5]:
            print(f"     - seq={ev.get('seq', '?')} {ev.get('type', '?')}")
    print()

    narrate("Server metrics")
    show("GET", "/api/metrics")
    r = await client.get("/api/metrics")
    metrics = r.json().get("metrics", {}) if r.status_code == 200 else {}
    interesting = [
        "http_requests_total",
        "hijack_acquires_total",
        "hijack_releases_total",
    ]
    for k in interesting:
        if k in metrics:
            print(f"  {k}: {metrics[k]}")
    print()


def phase_summary() -> None:
    narrate(
        "Walkthrough complete",
        "\n".join(
            [
                "Endpoints exercised:",
                "  GET  /api/health",
                "  GET  /api/sessions",
                "  GET  /api/sessions/{id}",
                "  POST /api/sessions/{id}/mode",
                "  GET  /api/sessions/{id}/snapshot",
                "  GET  /api/sessions/{id}/events",
                "  GET  /api/sessions/{id}/recording/entries",
                "  POST /api/connect",
                "  GET  /api/metrics",
                "  POST /worker/{id}/hijack/acquire",
                "  POST /worker/{id}/hijack/{hid}/send",
                "  GET  /worker/{id}/hijack/{hid}/snapshot",
                "  POST /worker/{id}/hijack/{hid}/heartbeat",
                "  GET  /worker/{id}/hijack/{hid}/events",
                "  POST /worker/{id}/hijack/{hid}/release",
                "",
                "Features demonstrated:",
                "  - Server startup with dev auth + shell connector",
                "  - Session discovery and status inspection",
                "  - Open-mode snapshot reading",
                "  - Full hijack lifecycle (acquire/send/snapshot/heartbeat/release)",
                "  - Event log and recording entries",
                "  - Quick-connect ephemeral session creation",
                "  - Server metrics",
            ]
        ),
    )


# ── Main entry point ────────────────────────────────────────────────


async def run_walkthrough(*, port: int = 0, open_browser: bool = True) -> None:
    if port == 0:
        port = _find_free_port()

    print(f"{'=' * 60}")
    print("  undef-terminal walkthrough")
    print(f"  Server: http://127.0.0.1:{port}")
    print(f"{'=' * 60}")
    print()

    server, server_task = await _start_server(port)

    try:
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}",
            headers={"X-Uterm-Principal": "walkthrough", "X-Uterm-Role": "admin"},
            timeout=httpx.Timeout(15.0),
        ) as client:
            await _wait_healthy(client)

            # Give the auto-start session time to connect its worker
            await asyncio.sleep(1.0)

            await phase_setup(client, port, open_browser=open_browser)
            await phase_discovery(client, port, open_browser=open_browser)
            await phase_open_mode(client)

            hijack_result = await phase_hijack(client)
            await phase_release(client, hijack_result["hijack_id"])

            await phase_quick_connect(client)
            await phase_events_and_metrics(client)

        phase_summary()
    finally:
        server.should_exit = True
        # Give the server a moment to shut down gracefully
        try:
            await asyncio.wait_for(server_task, timeout=5.0)
        except (TimeoutError, asyncio.CancelledError):
            server_task.cancel()
            with asyncio.timeout(1.0):
                await server_task


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="walkthrough",
        description="End-to-end walkthrough of the undef-terminal hijack lifecycle",
    )
    parser.add_argument("--port", type=int, default=0, help="Server port (0 = random free port)")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Skip opening browser tabs",
    )
    args = parser.parse_args()

    try:
        asyncio.run(run_walkthrough(port=args.port, open_browser=not args.no_browser))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
    except TimeoutError as exc:
        print(f"\nTimeout: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
