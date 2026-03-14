#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Advanced E2E edge cases: rate limits, validation, guards, errors."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
import websockets


def _ws_url(base_url: str, path: str) -> str:
    """Convert http to ws URL."""
    return base_url.replace("http://", "ws://") + path


def _snapshot_msg(screen: str = "test", prompt_id: str = "test_p") -> dict[str, Any]:
    """Build a valid snapshot message."""
    return {
        "type": "snapshot",
        "screen": screen,
        "cursor": {"x": 0, "y": 0},
        "cols": 80,
        "rows": 25,
        "screen_hash": "hash",
        "cursor_at_end": True,
        "has_trailing_space": False,
        "prompt_detected": {"prompt_id": prompt_id},
        "ts": time.time(),
    }


async def _drain_until(ws: Any, type_: str, timeout: float = 2.0) -> dict[str, Any] | None:
    """Drain until message type found."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=0.2)
            msg = json.loads(raw)
            if msg.get("type") == type_:
                return msg
        except TimeoutError:
            continue
    return None


async def _drain_all(ws: Any, timeout: float = 0.3) -> list[dict[str, Any]]:
    """Drain all messages."""
    msgs: list[dict[str, Any]] = []
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=0.1)
            msgs.append(json.loads(raw))
        except TimeoutError:
            continue
    return msgs


# ---------------------------------------------------------------------------
# TestInputValidation — input length, format
# ---------------------------------------------------------------------------


class TestInputValidation:
    async def test_rest_send_validates_key_length(self, live_hub: Any) -> None:
        """REST send validates that keys don't exceed max length."""
        _, base_url = live_hub
        async with (
            websockets.connect(_ws_url(base_url, "/ws/worker/iv2/term")) as worker,
            httpx.AsyncClient(base_url=base_url) as http,
        ):
            await worker.recv()

            r = await http.post("/worker/iv2/hijack/acquire", json={"owner": "test", "lease_s": 60})
            hijack_id = r.json()["hijack_id"]

            # Send oversized keys (REST validates max 10_000 per HijackSendRequest)
            huge_keys = "x" * 15000
            r2 = await http.post(
                f"/worker/iv2/hijack/{hijack_id}/send",
                json={"keys": huge_keys, "timeout_ms": 1000},
            )
            # Should fail validation (400 or 422 depending on pydantic version)
            assert r2.status_code in (400, 422)


# ---------------------------------------------------------------------------
# TestGuardChecking — expect_prompt_id, expect_regex
# ---------------------------------------------------------------------------


class TestGuardChecking:
    async def test_send_guard_prompt_id_mismatch(self, live_hub: Any) -> None:
        """Send with expect_prompt_id that doesn't match returns 409."""
        _, base_url = live_hub
        async with (
            websockets.connect(_ws_url(base_url, "/ws/worker/gc1/term")) as worker,
            httpx.AsyncClient(base_url=base_url) as http,
        ):
            await worker.recv()

            r = await http.post("/worker/gc1/hijack/acquire", json={"owner": "test", "lease_s": 60})
            hijack_id = r.json()["hijack_id"]
            await _drain_until(worker, "control")

            # Send snapshot with specific prompt_id
            await worker.send(json.dumps(_snapshot_msg("screen", "actual_prompt")))
            await asyncio.sleep(0.1)

            # Try to send with different expected prompt_id
            r2 = await http.post(
                f"/worker/gc1/hijack/{hijack_id}/send",
                json={"keys": "test", "expect_prompt_id": "expected_prompt", "timeout_ms": 500},
            )
            # Guard check fails, returns 409
            assert r2.status_code == 409
            assert "prompt_guard" in r2.json().get("error", "").lower()

    async def test_send_guard_prompt_id_match_succeeds(self, live_hub: Any) -> None:
        """Send with matching expect_prompt_id succeeds."""
        _, base_url = live_hub
        async with (
            websockets.connect(_ws_url(base_url, "/ws/worker/gc2/term")) as worker,
            httpx.AsyncClient(base_url=base_url) as http,
        ):
            await worker.recv()

            r = await http.post("/worker/gc2/hijack/acquire", json={"owner": "test", "lease_s": 60})
            hijack_id = r.json()["hijack_id"]
            await _drain_until(worker, "control")

            # Send snapshot with specific prompt
            await worker.send(json.dumps(_snapshot_msg("screen", "correct_prompt")))
            await asyncio.sleep(0.1)

            # Send with matching prompt_id
            r2 = await http.post(
                f"/worker/gc2/hijack/{hijack_id}/send",
                json={"keys": "test", "expect_prompt_id": "correct_prompt", "timeout_ms": 1000},
            )
            assert r2.status_code == 200


# ---------------------------------------------------------------------------
# TestWorkerOffline — no worker connected
# ---------------------------------------------------------------------------


class TestWorkerOffline:
    async def test_acquire_fails_if_no_worker(self, live_hub: Any) -> None:
        """Acquire returns 409 when no worker is online."""
        _, base_url = live_hub
        async with httpx.AsyncClient(base_url=base_url) as http:
            # No worker connected for this worker_id
            r = await http.post("/worker/wo1/hijack/acquire", json={"owner": "test", "lease_s": 60})
            # When no worker is connected, acquire fails with 409
            assert r.status_code == 409

    async def test_send_fails_if_worker_disconnects(self, live_hub: Any) -> None:
        """Send fails with 409 after worker disconnects."""
        _, base_url = live_hub
        async with httpx.AsyncClient(base_url=base_url) as http:
            async with websockets.connect(_ws_url(base_url, "/ws/worker/wo2/term")) as worker:
                await worker.recv()
                r = await http.post("/worker/wo2/hijack/acquire", json={"owner": "test", "lease_s": 60})
                hijack_id = r.json()["hijack_id"]
                await _drain_until(worker, "control")

            # Worker disconnected
            await asyncio.sleep(0.2)

            # Try to send
            r2 = await http.post(
                f"/worker/wo2/hijack/{hijack_id}/send",
                json={"keys": "test", "timeout_ms": 500},
            )
            # May be 404 (session expired) or 409 (worker gone)
            assert r2.status_code in (404, 409)


# ---------------------------------------------------------------------------
# TestInvalidSession — bad hijack_id, expired sessions
# ---------------------------------------------------------------------------


class TestInvalidSession:
    async def test_send_with_invalid_hijack_id(self, live_hub: Any) -> None:
        """Send with nonexistent hijack_id returns 404."""
        _, base_url = live_hub
        async with httpx.AsyncClient(base_url=base_url) as http:
            r = await http.post(
                "/worker/is1/hijack/00000000-0000-0000-0000-000000000000/send",
                json={"keys": "test", "timeout_ms": 500},
            )
            assert r.status_code == 404

    async def test_snapshot_with_invalid_hijack_id(self, live_hub: Any) -> None:
        """GET /snapshot with bad hijack_id returns 404."""
        _, base_url = live_hub
        async with httpx.AsyncClient(base_url=base_url) as http:
            # Use a valid UUID format that doesn't exist
            r = await http.get("/worker/is2/hijack/00000000-0000-0000-0000-000000000000/snapshot")
            assert r.status_code == 404

    async def test_step_with_expired_session(self, live_hub: Any) -> None:
        """Step after lease expires returns 404."""
        _, base_url = live_hub
        async with (
            websockets.connect(_ws_url(base_url, "/ws/worker/is3/term")) as worker,
            httpx.AsyncClient(base_url=base_url) as http,
        ):
            await worker.recv()

            r = await http.post("/worker/is3/hijack/acquire", json={"owner": "test", "lease_s": 1})
            hijack_id = r.json()["hijack_id"]

            # Wait for lease to expire
            await asyncio.sleep(1.5)

            # Try to step with expired lease
            r2 = await http.post(f"/worker/is3/hijack/{hijack_id}/step")
            assert r2.status_code == 404


# ---------------------------------------------------------------------------
# TestMultiBrowserContention — 3+ concurrent browsers
# ---------------------------------------------------------------------------


class TestMultiBrowserContention:
    async def test_three_browsers_hijack_contention(self, live_hub: Any) -> None:
        """Three browsers race to hijack; one wins, others see owner=other."""
        _, base_url = live_hub
        async with websockets.connect(_ws_url(base_url, "/ws/worker/mbc1/term")) as worker:
            await worker.recv()

            async with (
                websockets.connect(_ws_url(base_url, "/ws/browser/mbc1/term")) as b1,
                websockets.connect(_ws_url(base_url, "/ws/browser/mbc1/term")) as b2,
                websockets.connect(_ws_url(base_url, "/ws/browser/mbc1/term")) as b3,
            ):
                for b in (b1, b2, b3):
                    await _drain_all(b)

                # All three send hijack_request simultaneously
                for b in (b1, b2, b3):
                    await b.send(json.dumps({"type": "hijack_request"}))

                await asyncio.sleep(0.1)

                # Collect states
                states = {
                    "b1": await _drain_until(b1, "hijack_state"),
                    "b2": await _drain_until(b2, "hijack_state"),
                    "b3": await _drain_until(b3, "hijack_state"),
                }

                # Exactly one should have owner=me, others owner=other
                me_count = sum(1 for s in states.values() if s and s.get("owner") == "me")
                other_count = sum(1 for s in states.values() if s and s.get("owner") == "other")
                assert me_count == 1, f"Expected 1 owner=me, got {me_count}"
                assert other_count == 2, f"Expected 2 owner=other, got {other_count}"


# ---------------------------------------------------------------------------
# TestBrowserDisconnect — disconnect during operations
# ---------------------------------------------------------------------------


class TestBrowserDisconnect:
    async def test_browser_disconnect_releases_hijack(self, live_hub: Any) -> None:
        """Browser disconnect during hijack sends resume to worker."""
        _, base_url = live_hub
        async with websockets.connect(_ws_url(base_url, "/ws/worker/bd1/term")) as worker:
            await worker.recv()

            async with websockets.connect(_ws_url(base_url, "/ws/browser/bd1/term")) as browser:
                await _drain_all(browser)
                await browser.send(json.dumps({"type": "hijack_request"}))
                await _drain_until(browser, "hijack_state")
                await _drain_until(worker, "control")  # pause

            # Browser exited context (disconnected)
            await asyncio.sleep(0.1)

            # Worker should get resume
            resume = await _drain_until(worker, "control", timeout=2.0)
            assert resume is not None
            assert resume["action"] == "resume"

    async def test_second_browser_takes_hijack_after_disconnect(self, live_hub: Any) -> None:
        """After first hijack owner disconnects, second browser can acquire."""
        _, base_url = live_hub
        async with websockets.connect(_ws_url(base_url, "/ws/worker/bd2/term")) as worker:
            await worker.recv()

            async with websockets.connect(_ws_url(base_url, "/ws/browser/bd2/term")) as b1:
                await _drain_all(b1)
                await b1.send(json.dumps({"type": "hijack_request"}))
                state1 = await _drain_until(b1, "hijack_state")
                assert state1["owner"] == "me"

            # b1 disconnected
            await asyncio.sleep(0.2)

            async with websockets.connect(_ws_url(base_url, "/ws/browser/bd2/term")) as b2:
                await _drain_all(b2)
                await b2.send(json.dumps({"type": "hijack_request"}))
                state2 = await _drain_until(b2, "hijack_state")
                # b2 should be able to hijack now
                assert state2["owner"] == "me"


# ---------------------------------------------------------------------------
# TestSnapshotLifecycle — snapshot persistence
# ---------------------------------------------------------------------------


class TestSnapshotLifecycle:
    async def test_last_snapshot_cached_on_new_browser(self, live_hub: Any) -> None:
        """New browser connecting gets the last cached snapshot."""
        _, base_url = live_hub
        async with websockets.connect(_ws_url(base_url, "/ws/worker/sl1/term")) as worker:
            await worker.recv()
            await worker.send(json.dumps(_snapshot_msg("cached content")))
            await asyncio.sleep(0.1)

            async with websockets.connect(_ws_url(base_url, "/ws/browser/sl1/term")) as browser:
                # Should receive cached snapshot
                snap = await _drain_until(browser, "snapshot", timeout=2.0)
                assert snap is not None
                assert snap["screen"] == "cached content"

    async def test_snapshot_cleared_after_worker_disconnect(self, live_hub: Any) -> None:
        """Snapshot is cleared when worker disconnects."""
        _, base_url = live_hub
        async with websockets.connect(_ws_url(base_url, "/ws/worker/sl2/term")) as worker:
            await worker.recv()
            await worker.send(json.dumps(_snapshot_msg("old snapshot")))
            await asyncio.sleep(0.1)

        # Worker disconnected, snapshot should clear
        await asyncio.sleep(0.2)

        async with websockets.connect(_ws_url(base_url, "/ws/browser/sl2/term")) as browser:
            # Should NOT receive a cached snapshot
            snap = await _drain_until(browser, "snapshot", timeout=1.0)
            # Either None or has no content (browser still gets hello/hijack_state)
            assert snap is None or snap.get("screen") != "old snapshot"
