#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Browser WebSocket edge-case tests: ownership, lease-touch, no-worker errors.

Split from test_hijack_ws.py to keep files under 500 LOC.
"""

from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from undef.terminal.hijack.hub import TermHub

# ---------------------------------------------------------------------------
# Shared helpers (mirrors test_hijack_ws.py)
# ---------------------------------------------------------------------------


def make_app() -> tuple[FastAPI, TermHub]:
    hub = TermHub()
    app = FastAPI()
    app.include_router(hub.create_router())
    return app, hub


def _read_initial_browser_messages(browser) -> tuple[dict, dict]:
    hello = browser.receive_json()
    assert hello["type"] == "hello"
    hijack_state = browser.receive_json()
    assert hijack_state["type"] == "hijack_state"
    return hello, hijack_state


def _read_worker_snapshot_req(worker) -> dict:
    msg = worker.receive_json()
    assert msg["type"] == "snapshot_req"
    return msg


# ---------------------------------------------------------------------------
# Browser — invalid JSON, ownership lease touch, no-worker error paths
# ---------------------------------------------------------------------------


def test_browser_invalid_json_ignored() -> None:
    """Invalid JSON from browser should not crash the connection."""
    app, hub = make_app()
    with TestClient(app) as client, client.websocket_connect("/ws/browser/bot1/term") as browser:
        _read_initial_browser_messages(browser)

        with client.websocket_connect("/ws/worker/bot1/term") as worker:
            _read_worker_snapshot_req(worker)

            browser.send_text("not json {{{{")
            # Connection still alive — send valid message after invalid one
            browser.send_json({"type": "snapshot_req"})
            msg = worker.receive_json()
            assert msg["type"] == "snapshot_req"


def test_browser_snapshot_req_as_owner_touches_lease() -> None:
    """snapshot_req from owner calls _touch_hijack_owner."""
    app, hub = make_app()
    with TestClient(app) as client, client.websocket_connect("/ws/browser/bot1/term") as browser:
        _read_initial_browser_messages(browser)

        with client.websocket_connect("/ws/worker/bot1/term") as worker:
            _read_worker_snapshot_req(worker)

            # Acquire hijack
            browser.send_json({"type": "hijack_request"})
            worker.receive_json()  # pause
            browser.receive_json()  # hijack_state

            # As owner, send snapshot_req — should touch lease
            browser.send_json({"type": "snapshot_req"})
            msg = worker.receive_json()
            assert msg["type"] == "snapshot_req"


def test_browser_analyze_req_as_owner_touches_lease() -> None:
    """analyze_req from owner calls _touch_hijack_owner."""
    app, hub = make_app()
    with TestClient(app) as client, client.websocket_connect("/ws/browser/bot1/term") as browser:
        _read_initial_browser_messages(browser)

        with client.websocket_connect("/ws/worker/bot1/term") as worker:
            _read_worker_snapshot_req(worker)

            # Acquire hijack
            browser.send_json({"type": "hijack_request"})
            worker.receive_json()  # pause
            browser.receive_json()  # hijack_state

            # As owner, send analyze_req — should touch lease
            browser.send_json({"type": "analyze_req"})
            msg = worker.receive_json()
            assert msg["type"] == "analyze_req"


def test_browser_hijack_step_no_worker() -> None:
    """hijack_step as owner with no worker returns error message."""
    app, hub = make_app()
    with TestClient(app) as client, client.websocket_connect("/ws/browser/bot1/term") as browser:
        _read_initial_browser_messages(browser)

        # Acquire hijack with a worker present
        with client.websocket_connect("/ws/worker/bot1/term") as worker:
            _read_worker_snapshot_req(worker)
            browser.send_json({"type": "hijack_request"})
            worker.receive_json()  # pause
            browser.receive_json()  # hijack_state

        # Worker context exited — worker is disconnected now
        # Browser is still owner. Send hijack_step — no worker connected → error
        browser.send_json({"type": "hijack_step"})
        msg = browser.receive_json()
        assert msg["type"] == "error"
        assert "worker" in msg["message"].lower()


def test_browser_input_no_worker() -> None:
    """Input as owner with no worker returns error message."""
    app, hub = make_app()
    with TestClient(app) as client, client.websocket_connect("/ws/browser/bot1/term") as browser:
        _read_initial_browser_messages(browser)

        with client.websocket_connect("/ws/worker/bot1/term") as worker:
            _read_worker_snapshot_req(worker)

            # Acquire hijack
            browser.send_json({"type": "hijack_request"})
            worker.receive_json()  # pause
            browser.receive_json()  # hijack_state

        # Worker is now disconnected (context exited)
        # The browser is still connected and still the owner
        # Send input — worker is gone, should get error
        browser.send_json({"type": "input", "data": "hello\r"})
        # The worker WS is None now, so _send_worker returns False → error sent
        msg = browser.receive_json()
        assert msg["type"] == "error", f"expected error message when worker disconnected, got: {msg}"
        assert "worker" in msg["message"].lower()
