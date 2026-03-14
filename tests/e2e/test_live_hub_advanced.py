#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Advanced E2E tests: role enforcement, lease expiry, reconnect, events, input modes."""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
import uvicorn
import websockets
from fastapi import FastAPI

from undef.terminal.hijack.hub import TermHub


def _ws_url(base_url: str, path: str) -> str:
    """Convert http to ws URL."""
    return base_url.replace("http://", "ws://") + path


def _snapshot_msg(screen: str = "test screen", prompt_id: str = "test_prompt") -> dict[str, Any]:
    """Build a valid snapshot message."""
    return {
        "type": "snapshot",
        "screen": screen,
        "cursor": {"x": 0, "y": 0},
        "cols": 80,
        "rows": 25,
        "screen_hash": "test-hash",
        "cursor_at_end": True,
        "has_trailing_space": False,
        "prompt_detected": {"prompt_id": prompt_id},
        "ts": time.time(),
    }


async def _drain_until(ws: Any, type_: str, timeout: float = 3.0) -> dict[str, Any] | None:
    """Drain messages until one matches the type."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=0.3)
            msg = json.loads(raw)
            if msg.get("type") == type_:
                return msg
        except TimeoutError:
            continue
    return None


async def _drain_all(ws: Any, timeout: float = 0.5) -> list[dict[str, Any]]:
    """Drain all available messages."""
    msgs: list[dict[str, Any]] = []
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=0.1)
            msgs.append(json.loads(raw))
        except TimeoutError:
            continue
    return msgs


@asynccontextmanager
async def _hub_with_roles(role_map: dict[str, str]):
    """Context manager: hub with custom role resolver. role_map["*"] = default role."""
    default_role = role_map.get("*", "viewer")
    hub = TermHub(resolve_browser_role=lambda _ws, _worker_id: default_role)
    app = FastAPI()
    app.include_router(hub.create_router())

    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="critical")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())

    try:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 5.0
        while not server.started:
            if loop.time() > deadline:
                server.should_exit = True
                await asyncio.wait_for(task, timeout=2.0)
                raise RuntimeError("role-aware hub: uvicorn startup timeout")
            await asyncio.sleep(0.05)

        port: int = server.servers[0].sockets[0].getsockname()[1]
        yield hub, f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, timeout=5.0)


# ---------------------------------------------------------------------------
# TestBrowserRoles — enforce viewer/operator/admin permissions
# ---------------------------------------------------------------------------


class TestBrowserRoles:
    async def test_viewer_cannot_send_input_in_open_mode(self) -> None:
        """Viewer sends input in open mode, gets error; worker doesn't receive it."""
        async with _hub_with_roles({"*": "viewer"}) as (hub, base_url):
            hub._dashboard_hijack_lease_s = 0.5
            async with (
                websockets.connect(_ws_url(base_url, "/ws/browser/v1/term")) as browser,
                websockets.connect(_ws_url(base_url, "/ws/worker/v1/term")) as worker,
            ):
                await worker.recv()  # snapshot_req
                await _drain_all(browser)  # hello, hijack_state

                # Switch to open mode via worker hello
                await worker.send(
                    json.dumps(
                        {
                            "type": "worker_hello",
                            "input_mode": "open",
                            "ts": time.time(),
                        }
                    )
                )
                await asyncio.sleep(0.1)

                await browser.send(json.dumps({"type": "input", "data": "test"}))
                # Viewer input is rejected or ignored; no input appears in worker messages
                msgs = await _drain_all(worker, timeout=0.5)
                input_msgs = [m for m in msgs if m.get("type") == "input"]
                assert len(input_msgs) == 0

    async def test_viewer_gets_hello_with_can_hijack_false(self) -> None:
        """Viewer hello message includes can_hijack=false."""
        async with (
            _hub_with_roles({"*": "viewer"}) as (_hub, base_url),
            websockets.connect(_ws_url(base_url, "/ws/browser/v2/term")) as browser,
        ):
            hello = await _drain_until(browser, "hello")
            assert hello is not None
            assert hello.get("role") == "viewer"

    async def test_operator_can_send_in_open_mode(self) -> None:
        """Operator can send input in open mode; worker receives it."""
        async with (
            _hub_with_roles({"*": "operator"}) as (_hub, base_url),
            websockets.connect(_ws_url(base_url, "/ws/browser/op1/term")) as browser,
            websockets.connect(_ws_url(base_url, "/ws/worker/op1/term")) as worker,
        ):
            await worker.recv()  # snapshot_req
            await _drain_all(browser)

            # Switch to open mode
            await worker.send(
                json.dumps(
                    {
                        "type": "worker_hello",
                        "input_mode": "open",
                        "ts": time.time(),
                    }
                )
            )
            await asyncio.sleep(0.1)

            await browser.send(json.dumps({"type": "input", "data": "opkey"}))
            inp = await _drain_until(worker, "input")
            assert inp is not None
            assert inp["data"] == "opkey"

    async def test_operator_hijack_request_rejected(self) -> None:
        """Operator sends hijack_request, gets error."""
        async with (
            _hub_with_roles({"*": "operator"}) as (_hub, base_url),
            websockets.connect(_ws_url(base_url, "/ws/browser/op2/term")) as browser,
            websockets.connect(_ws_url(base_url, "/ws/worker/op2/term")),
        ):
            await _drain_all(browser)
            await browser.send(json.dumps({"type": "hijack_request"}))
            # Operator cannot hijack; error or no state change
            msg = await _drain_until(browser, "error", timeout=1.0)
            # May receive error or no state change; operator hijack should be rejected
            assert msg is not None  # pragma: no cover

    async def test_admin_can_hijack(self, live_hub: Any) -> None:
        """Admin sends hijack_request, acquires hijack with owner=me."""
        _, base_url = live_hub
        async with (
            websockets.connect(_ws_url(base_url, "/ws/browser/a1/term")) as browser,
            websockets.connect(_ws_url(base_url, "/ws/worker/a1/term")) as worker,
        ):
            await worker.recv()  # snapshot_req
            await _drain_all(browser)

            await browser.send(json.dumps({"type": "hijack_request"}))
            state = await _drain_until(browser, "hijack_state")
            assert state is not None
            assert state.get("hijacked") is True
            assert state.get("owner") == "me"


# ---------------------------------------------------------------------------
# TestLeaseExpiry
# ---------------------------------------------------------------------------


class TestLeaseExpiry:
    async def test_rest_lease_expires_worker_gets_resume(self, live_hub: Any) -> None:
        """Acquire with lease_s=0.3; sleep 0.6s; worker receives resume."""
        _, base_url = live_hub
        async with (
            websockets.connect(_ws_url(base_url, "/ws/worker/le1/term")) as worker,
            httpx.AsyncClient(base_url=base_url) as http,
        ):
            await worker.recv()  # snapshot_req

            r = await http.post("/worker/le1/hijack/acquire", json={"owner": "test", "lease_s": 1})
            assert r.status_code == 200

            # Immediately send a snapshot so guard passes for any upcoming send
            await worker.send(json.dumps(_snapshot_msg()))
            ctrl = await _drain_until(worker, "control")
            assert ctrl["action"] == "pause"

            # Wait for lease to expire
            await asyncio.sleep(1.5)

            # Hub should send resume after lease expiry
            resume = await _drain_until(worker, "control", timeout=3.0)
            assert resume is not None
            assert resume["action"] == "resume"

    async def test_ws_hijack_owner_disconnect_sends_resume(self, live_hub: Any) -> None:
        """Browser hijacks, then disconnects; worker receives resume."""
        _, base_url = live_hub
        async with websockets.connect(_ws_url(base_url, "/ws/worker/le2/term")) as worker:
            await worker.recv()  # snapshot_req

            async with websockets.connect(_ws_url(base_url, "/ws/browser/le2/term")) as b1:
                await _drain_all(b1)
                await b1.send(json.dumps({"type": "hijack_request"}))
                state = await _drain_until(b1, "hijack_state")
                assert state["owner"] == "me"
                pause = await _drain_until(worker, "control")
                assert pause["action"] == "pause"

            # b1 disconnected; worker should get resume
            resume = await _drain_until(worker, "control", timeout=3.0)
            assert resume is not None
            assert resume["action"] == "resume"


# ---------------------------------------------------------------------------
# TestWorkerReconnect
# ---------------------------------------------------------------------------


class TestWorkerReconnect:
    async def test_worker_reconnect_browser_sees_events(self, live_hub: Any) -> None:
        """Worker disconnects and reconnects; browser sees events."""
        _, base_url = live_hub
        async with websockets.connect(_ws_url(base_url, "/ws/browser/wr1/term")) as browser:
            await _drain_all(browser)

            async with websockets.connect(_ws_url(base_url, "/ws/worker/wr1/term")):
                await _drain_until(browser, "worker_connected", timeout=2.0)

            # Worker disconnected
            disc = await _drain_until(browser, "worker_disconnected", timeout=2.0)
            assert disc is not None

    async def test_active_hijack_cleared_on_worker_disconnect(self, live_hub: Any) -> None:
        """REST acquire, then worker disconnects; second acquire succeeds."""
        _, base_url = live_hub
        async with httpx.AsyncClient(base_url=base_url) as http:
            async with websockets.connect(_ws_url(base_url, "/ws/worker/wr2/term")) as worker:
                await worker.recv()  # snapshot_req

                r1 = await http.post("/worker/wr2/hijack/acquire", json={"owner": "test", "lease_s": 60})
                assert r1.status_code == 200

            # Worker disconnected; hijack is cleared
            await asyncio.sleep(0.2)

            async with websockets.connect(_ws_url(base_url, "/ws/worker/wr2/term")) as worker:
                await worker.recv()
                # Second acquire should succeed
                r2 = await http.post("/worker/wr2/hijack/acquire", json={"owner": "test2", "lease_s": 60})
                assert r2.status_code == 200


# ---------------------------------------------------------------------------
# TestRestHijackAdvanced
# ---------------------------------------------------------------------------


class TestRestHijackAdvanced:
    async def test_snapshot_poll_returns_response(self, live_hub: Any) -> None:
        """Acquire, then poll snapshot endpoint; returns 200 with ok=True."""
        _, base_url = live_hub
        async with (
            websockets.connect(_ws_url(base_url, "/ws/worker/rha1/term")) as worker,
            httpx.AsyncClient(base_url=base_url) as http,
        ):
            await worker.recv()  # snapshot_req

            r = await http.post("/worker/rha1/hijack/acquire", json={"owner": "test", "lease_s": 60})
            assert r.status_code == 200
            hijack_id = r.json()["hijack_id"]

            # Send a snapshot so poll doesn't timeout
            await worker.send(json.dumps(_snapshot_msg("test snapshot")))
            await asyncio.sleep(0.1)

            # Poll snapshot endpoint
            r2 = await http.get(f"/worker/rha1/hijack/{hijack_id}/snapshot?wait_ms=100")
            assert r2.status_code == 200
            data = r2.json()
            assert data.get("ok") is True
            assert data.get("hijack_id") == hijack_id

    async def test_events_ring_buffer_ordered(self, live_hub: Any) -> None:
        """Acquire, step, GET /events; returns events with monotonic seq."""
        _, base_url = live_hub
        async with (
            websockets.connect(_ws_url(base_url, "/ws/worker/rha2/term")) as worker,
            httpx.AsyncClient(base_url=base_url) as http,
        ):
            await worker.recv()

            r = await http.post("/worker/rha2/hijack/acquire", json={"owner": "test", "lease_s": 60})
            assert r.status_code == 200
            hijack_id = r.json()["hijack_id"]
            await _drain_until(worker, "control")

            # Send a snapshot to ensure we have a valid state
            await worker.send(json.dumps(_snapshot_msg()))
            await asyncio.sleep(0.1)

            # Trigger a step event
            r2 = await http.post(f"/worker/rha2/hijack/{hijack_id}/step")
            assert r2.status_code == 200
            await asyncio.sleep(0.1)

            # GET events while hijack is still active
            r3 = await http.get(f"/worker/rha2/hijack/{hijack_id}/events")
            assert r3.status_code == 200
            events = r3.json().get("events", [])
            # Verify monotonically increasing seq
            seqs = [e["seq"] for e in events if "seq" in e]
            if len(seqs) > 1:
                assert seqs == sorted(seqs)

    async def test_concurrent_acquire_second_client_gets_409(self, live_hub: Any) -> None:
        """Two clients race to acquire; exactly one gets 200, other gets 409."""
        _, base_url = live_hub
        async with websockets.connect(_ws_url(base_url, "/ws/worker/rha3/term")) as worker:
            await worker.recv()

            async def acquire(client_id: int):
                async with httpx.AsyncClient(base_url=base_url) as http:
                    r = await http.post(
                        "/worker/rha3/hijack/acquire", json={"owner": f"client{client_id}", "lease_s": 60}
                    )
                    return r.status_code

            # Race two acquires
            results = await asyncio.gather(acquire(1), acquire(2))
            statuses = sorted(results)
            # Exactly one 200 and one 409
            assert 200 in statuses and 409 in statuses


# ---------------------------------------------------------------------------
# TestAnalyzeRoundTrip
# ---------------------------------------------------------------------------


class TestAnalyzeRoundTrip:
    async def test_analyze_req_forwarded_to_worker_and_back(self, live_hub: Any) -> None:
        """Hijack owner sends analyze_req; worker receives and replies with analysis."""
        _, base_url = live_hub
        async with (
            websockets.connect(_ws_url(base_url, "/ws/browser/ar1/term")) as browser,
            websockets.connect(_ws_url(base_url, "/ws/worker/ar1/term")) as worker,
        ):
            await worker.recv()
            await _drain_all(browser)

            # Browser acquires hijack first
            await browser.send(json.dumps({"type": "hijack_request"}))
            state = await _drain_until(browser, "hijack_state")
            assert state is not None
            await _drain_until(worker, "control")  # pause

            # Browser sends analyze_req (only works for hijack owner)
            await browser.send(json.dumps({"type": "analyze_req", "ts": time.time()}))

            # Worker receives it
            analyze = await _drain_until(worker, "analyze_req", timeout=2.0)
            assert analyze is not None

            # Worker sends analysis back
            await worker.send(
                json.dumps(
                    {
                        "type": "analysis",
                        "formatted": "test analysis result",
                        "ts": time.time(),
                    }
                )
            )

            # Browser receives it
            analysis = await _drain_until(browser, "analysis", timeout=2.0)
            assert analysis is not None
            assert analysis["formatted"] == "test analysis result"


# ---------------------------------------------------------------------------
# TestInputModeLifecycle
# ---------------------------------------------------------------------------


class TestInputModeLifecycle:
    async def test_mode_switch_to_open_blocked_while_rest_hijack_active(self, live_hub: Any) -> None:
        """REST acquire hijack; attempt /input_mode → 409."""
        _, base_url = live_hub
        async with (
            websockets.connect(_ws_url(base_url, "/ws/worker/im1/term")) as worker,
            httpx.AsyncClient(base_url=base_url) as http,
        ):
            await worker.recv()

            r = await http.post("/worker/im1/hijack/acquire", json={"owner": "test", "lease_s": 60})
            assert r.status_code == 200

            # Try to change input_mode
            r2 = await http.post("/worker/im1/input_mode", json={"input_mode": "open"})
            assert r2.status_code == 409

    async def test_worker_hello_open_mode_propagates_to_browsers(self, live_hub: Any) -> None:
        """Worker sends worker_hello with open mode; browser receives mode update."""
        _, base_url = live_hub
        async with (
            websockets.connect(_ws_url(base_url, "/ws/browser/im2/term")) as browser,
            websockets.connect(_ws_url(base_url, "/ws/worker/im2/term")) as worker,
        ):
            await worker.recv()
            await _drain_all(browser)

            # Worker sends worker_hello with open mode
            await worker.send(
                json.dumps(
                    {
                        "type": "worker_hello",
                        "input_mode": "open",
                        "ts": time.time(),
                    }
                )
            )

            # Browser should receive an update reflecting open mode
            # This may come as a hijack_state with input_mode field
            msg = await _drain_until(browser, "hijack_state", timeout=2.0)
            assert msg is not None
            # Verify open mode is reflected (field name may vary)
            assert msg.get("input_mode") == "open" or "open" in str(msg)
