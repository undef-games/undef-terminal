#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Integration tests for TermHub logic (direct method calls, no HTTP).

Atomic/TOCTOU regression tests and prune tests are in test_hijack_hub_atomic.py.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from unittest.mock import AsyncMock

from undef.terminal.hijack.hub import TermHub
from undef.terminal.hijack.models import HijackSession, WorkerTermState

# ---------------------------------------------------------------------------
# State creation
# ---------------------------------------------------------------------------


async def test_get_creates_state() -> None:
    hub = TermHub()
    st = await hub._get("bot1")
    assert isinstance(st, WorkerTermState)
    assert "bot1" in hub._workers


async def test_get_returns_same_state() -> None:
    hub = TermHub()
    st1 = await hub._get("bot1")
    st2 = await hub._get("bot1")
    assert st1 is st2


async def test_is_hijacked_false_initially() -> None:
    hub = TermHub()
    st = await hub._get("bot1")
    assert not hub.is_hijacked(st)


# ---------------------------------------------------------------------------
# Cleanup — expired REST session
# ---------------------------------------------------------------------------


async def test_cleanup_expired_rest_session() -> None:
    hub = TermHub()
    await hub._get("bot1")
    hub._workers["bot1"].hijack_session = HijackSession(
        hijack_id="abc",
        owner="test",
        acquired_at=time.time() - 200,
        lease_expires_at=time.time() - 1,
        last_heartbeat=time.time() - 200,
    )
    expired = await hub.cleanup_expired_hijack("bot1")
    assert expired
    # Bot is fully idle after session expiry → pruned from _bots.
    assert "bot1" not in hub._workers


async def test_cleanup_not_expired_rest_session() -> None:
    hub = TermHub()
    await hub._get("bot1")
    hub._workers["bot1"].hijack_session = HijackSession(
        hijack_id="abc",
        owner="test",
        acquired_at=time.time(),
        lease_expires_at=time.time() + 3600,
        last_heartbeat=time.time(),
    )
    expired = await hub.cleanup_expired_hijack("bot1")
    assert not expired
    assert hub._workers["bot1"].hijack_session is not None


# ---------------------------------------------------------------------------
# Cleanup — expired dashboard owner
# ---------------------------------------------------------------------------


async def test_cleanup_expired_dashboard_owner() -> None:
    hub = TermHub()
    await hub._get("bot1")
    mock_ws = AsyncMock()
    hub._workers["bot1"].hijack_owner = mock_ws
    hub._workers["bot1"].hijack_owner_expires_at = time.time() - 1
    expired = await hub.cleanup_expired_hijack("bot1")
    assert expired
    # Bot is fully idle after owner expiry → pruned from _bots.
    assert "bot1" not in hub._workers


async def test_cleanup_missing_bot_returns_false() -> None:
    hub = TermHub()
    result = await hub.cleanup_expired_hijack("nonexistent")
    assert result is False


# ---------------------------------------------------------------------------
# Cleanup — resume message sent to worker
# ---------------------------------------------------------------------------


async def test_cleanup_sends_resume_to_worker() -> None:
    hub = TermHub()
    await hub._get("bot1")
    mock_ws = AsyncMock()
    hub._workers["bot1"].worker_ws = mock_ws
    hub._workers["bot1"].hijack_session = HijackSession(
        hijack_id="abc",
        owner="test",
        acquired_at=time.time() - 200,
        lease_expires_at=time.time() - 1,
        last_heartbeat=time.time() - 200,
    )
    await hub.cleanup_expired_hijack("bot1")
    mock_ws.send_text.assert_awaited_once()
    sent_msg = json.loads(mock_ws.send_text.await_args[0][0])
    assert sent_msg["action"] == "resume"


# ---------------------------------------------------------------------------
# Notify callbacks
# ---------------------------------------------------------------------------


async def test_notify_hijack_changed_sync() -> None:
    results: list[tuple] = []

    def cb(bot_id: str, enabled: bool, owner: str | None) -> None:
        results.append((bot_id, enabled, owner))

    hub = TermHub(on_hijack_changed=cb)
    hub.notify_hijack_changed("bot1", enabled=True, owner="me")
    assert results == [("bot1", True, "me")]


async def test_notify_hijack_changed_async() -> None:
    results: list[tuple] = []

    async def cb(bot_id: str, enabled: bool, owner: str | None) -> None:
        results.append((bot_id, enabled, owner))

    hub = TermHub(on_hijack_changed=cb)
    hub.notify_hijack_changed("bot1", enabled=True, owner="me")
    await asyncio.sleep(0)  # allow the scheduled task to run
    assert results == [("bot1", True, "me")]


async def test_notify_no_callback() -> None:
    hub = TermHub()
    # Should not raise
    hub.notify_hijack_changed("bot1", enabled=True, owner=None)


# ---------------------------------------------------------------------------
# _snapshot_matches
# ---------------------------------------------------------------------------


async def test_snapshot_matches_prompt_id() -> None:
    snapshot = {"prompt_detected": {"prompt_id": "main_menu"}, "screen": "hello"}
    assert TermHub.snapshot_matches(snapshot, expect_prompt_id="main_menu", expect_regex=None)


async def test_snapshot_matches_regex() -> None:
    snapshot = {"screen": "Welcome to the server"}
    pattern = re.compile("Welcome", re.IGNORECASE)
    assert TermHub.snapshot_matches(snapshot, expect_prompt_id=None, expect_regex=pattern)


async def test_snapshot_not_matches_wrong_prompt_id() -> None:
    snapshot = {"prompt_detected": {"prompt_id": "main_menu"}, "screen": "hello"}
    assert not TermHub.snapshot_matches(snapshot, expect_prompt_id="other", expect_regex=None)


async def test_snapshot_not_matches_none() -> None:
    assert not TermHub.snapshot_matches(None, expect_prompt_id="main_menu", expect_regex=None)


async def test_snapshot_matches_no_constraints() -> None:
    # Both constraints None → always True when snapshot is non-None
    snapshot = {"screen": "anything"}
    assert TermHub.snapshot_matches(snapshot, expect_prompt_id=None, expect_regex=None)


# ---------------------------------------------------------------------------
# _clamp_lease
# ---------------------------------------------------------------------------


async def test_clamp_lease_minimum() -> None:
    assert TermHub.clamp_lease(0) == 1


async def test_clamp_lease_normal() -> None:
    assert TermHub.clamp_lease(300) == 300


async def test_clamp_lease_maximum() -> None:
    assert TermHub.clamp_lease(9999) == 3600


# ---------------------------------------------------------------------------
# _is_dashboard_hijack_active
# ---------------------------------------------------------------------------


async def test_is_dashboard_hijack_active_expired() -> None:
    st = WorkerTermState()
    st.hijack_owner = AsyncMock()
    st.hijack_owner_expires_at = time.time() - 1
    assert not TermHub.is_dashboard_hijack_active(st)


async def test_is_dashboard_hijack_active_no_expiry() -> None:
    st = WorkerTermState()
    st.hijack_owner = AsyncMock()
    st.hijack_owner_expires_at = None  # no expiry → permanent
    assert TermHub.is_dashboard_hijack_active(st)


async def test_is_dashboard_hijack_active_future() -> None:
    st = WorkerTermState()
    st.hijack_owner = AsyncMock()
    st.hijack_owner_expires_at = time.time() + 3600
    assert TermHub.is_dashboard_hijack_active(st)


async def test_is_dashboard_hijack_active_no_owner() -> None:
    st = WorkerTermState()
    assert not TermHub.is_dashboard_hijack_active(st)


async def test_wait_for_guard_invalid_regex() -> None:
    hub = TermHub()
    ok, snapshot, reason = await hub.wait_for_guard(
        "bot1",
        expect_prompt_id=None,
        expect_regex="[invalid",
        timeout_ms=100,
        poll_interval_ms=50,
    )
    assert not ok
    assert reason is not None
    assert "invalid" in reason


async def test_wait_for_guard_no_constraints_returns_immediately() -> None:
    hub = TermHub()
    await hub._get("bot1")
    hub._workers["bot1"].last_snapshot = {"screen": "hello"}
    ok, snapshot, reason = await hub.wait_for_guard(
        "bot1",
        expect_prompt_id=None,
        expect_regex=None,
        timeout_ms=100,
        poll_interval_ms=50,
    )
    assert ok
    assert reason is None


async def test_wait_for_guard_with_prompt_constraint() -> None:
    hub = TermHub()
    await hub._get("bot1")
    hub._workers["bot1"].last_snapshot = {
        "screen": "hello",
        "prompt_detected": {"prompt_id": "main_menu"},
    }
    ok, snapshot, reason = await hub.wait_for_guard(
        "bot1",
        expect_prompt_id="main_menu",
        expect_regex=None,
        timeout_ms=200,
        poll_interval_ms=20,
    )
    assert ok


async def test_wait_for_guard_timeout() -> None:
    hub = TermHub()
    # No snapshot → guard never satisfied
    ok, snapshot, reason = await hub.wait_for_guard(
        "bot1",
        expect_prompt_id="never",
        expect_regex=None,
        timeout_ms=50,
        poll_interval_ms=10,
    )
    assert not ok
    assert reason == "prompt_guard_not_satisfied"


async def test_broadcast_removes_dead_socket() -> None:
    hub = TermHub()
    await hub._get("bot1")

    dead_ws = AsyncMock()
    dead_ws.send_text = AsyncMock(side_effect=RuntimeError("disconnected"))
    hub._workers["bot1"].browsers[dead_ws] = "operator"

    await hub.broadcast("bot1", {"type": "test"})
    # Dead socket should be removed
    assert dead_ws not in hub._workers["bot1"].browsers


async def test_broadcast_hijack_state_rest_session_active() -> None:
    """_broadcast_hijack_state uses hijack_session.lease_expires_at when REST session active."""
    hub = TermHub()
    await hub._get("bot1")
    mock_ws = AsyncMock()
    hub._workers["bot1"].browsers[mock_ws] = "operator"
    hub._workers["bot1"].hijack_session = HijackSession(
        hijack_id="abc",
        owner="test",
        acquired_at=time.time(),
        lease_expires_at=time.time() + 3600,
        last_heartbeat=time.time(),
    )
    await hub.broadcast_hijack_state("bot1")
    mock_ws.send_text.assert_awaited_once()
    msg = json.loads(mock_ws.send_text.await_args[0][0])
    assert msg["hijacked"] is True


async def test_broadcast_hijack_state_removes_dead_socket() -> None:
    hub = TermHub()
    await hub._get("bot1")
    dead_ws = AsyncMock()
    dead_ws.send_text = AsyncMock(side_effect=RuntimeError("gone"))
    hub._workers["bot1"].browsers[dead_ws] = "operator"

    await hub.broadcast_hijack_state("bot1")
    assert dead_ws not in hub._workers["bot1"].browsers


async def test_touch_hijack_owner_returns_none_when_no_bot() -> None:
    hub = TermHub()
    result = await hub.touch_hijack_owner("nonexistent")
    assert result is None


async def test_create_router_returns_router() -> None:
    hub = TermHub()
    router = hub.create_router()
    assert router is not None


async def test_wait_for_snapshot_returns_fresh_snapshot() -> None:
    """_wait_for_snapshot returns early when a fresh snapshot (ts > req_ts) is available."""
    hub = TermHub()
    await hub._get("bot1")
    # A snapshot with ts=0 predates req_ts and must NOT be returned (stale).
    hub._workers["bot1"].last_snapshot = {"screen": "stale", "cols": 80, "rows": 25, "ts": 0}
    result = await hub.wait_for_snapshot("bot1", timeout_ms=50)
    assert result is None, "stale cached snapshot (ts=0) must not be returned on timeout"


async def test_wait_for_snapshot_returns_none_on_timeout_no_worker() -> None:
    """_wait_for_snapshot returns None when the worker never sends a snapshot."""
    hub = TermHub()
    await hub._get("bot1")
    result = await hub.wait_for_snapshot("bot1", timeout_ms=50)
    assert result is None


async def test_hijack_state_msg_owner_is_me() -> None:
    """_hijack_state_msg_for returns owner='me' when the calling ws is the hijack owner (line 311)."""
    hub = TermHub()
    await hub._get("bot1")
    mock_ws = AsyncMock()
    hub._workers["bot1"].hijack_owner = mock_ws
    hub._workers["bot1"].hijack_owner_expires_at = time.time() + 3600
    msg = await hub.hijack_state_msg_for("bot1", mock_ws)
    assert msg["owner"] == "me"


async def test_cleanup_expired_both_expired_sends_resume() -> None:
    """When both dashboard and REST expire, resume is sent once and owner_expired event is appended."""
    hub = TermHub()
    await hub._get("bot1")
    mock_ws = AsyncMock()
    hub._workers["bot1"].worker_ws = mock_ws
    hub._workers["bot1"].hijack_owner = AsyncMock()
    hub._workers["bot1"].hijack_owner_expires_at = time.time() - 1
    hub._workers["bot1"].hijack_session = HijackSession(
        hijack_id="abc",
        owner="test",
        acquired_at=time.time() - 200,
        lease_expires_at=time.time() - 1,
        last_heartbeat=time.time() - 200,
    )
    expired = await hub.cleanup_expired_hijack("bot1")
    assert expired
    mock_ws.send_text.assert_awaited()


# ---------------------------------------------------------------------------
# Fix 2 regression — _broadcast_hijack_state snapshots state under lock
# ---------------------------------------------------------------------------


async def test_broadcast_hijack_state_owner_gets_me_others_get_other() -> None:
    """Regression fix 2: hijack owner WebSocket receives owner='me'; other browsers get 'other'."""
    hub = TermHub()
    ws_owner = AsyncMock()
    ws_other = AsyncMock()

    async with hub._lock:
        st = hub._workers.setdefault("bot1", WorkerTermState())
        st.browsers = {ws_owner: "admin", ws_other: "operator"}
        st.hijack_owner = ws_owner
        st.hijack_owner_expires_at = time.time() + 60

    await hub.broadcast_hijack_state("bot1")

    owner_msg = json.loads(ws_owner.send_text.await_args[0][0])
    assert owner_msg["owner"] == "me"
    assert owner_msg["type"] == "hijack_state"
    assert owner_msg["hijacked"] is True

    other_msg = json.loads(ws_other.send_text.await_args[0][0])
    assert other_msg["owner"] == "other"
    assert other_msg["hijacked"] is True


async def test_broadcast_hijack_state_no_hijack_owner_is_none() -> None:
    """Regression fix 2: when not hijacked, owner is None for all browsers."""
    hub = TermHub()
    ws1 = AsyncMock()
    ws2 = AsyncMock()

    async with hub._lock:
        st = hub._workers.setdefault("bot1", WorkerTermState())
        st.browsers = {ws1: "operator", ws2: "operator"}

    await hub.broadcast_hijack_state("bot1")

    msg1 = json.loads(ws1.send_text.await_args[0][0])
    msg2 = json.loads(ws2.send_text.await_args[0][0])
    assert msg1["owner"] is None
    assert msg2["owner"] is None
    assert msg1["hijacked"] is False


# ---------------------------------------------------------------------------
# Fix 4 regression — _notify_hijack_changed done_callback logs exceptions
# ---------------------------------------------------------------------------


async def test_notify_hijack_changed_async_exception_is_logged(caplog) -> None:
    """Regression fix 4: exceptions from async on_hijack_changed are logged, not silently dropped."""
    import logging

    async def failing_cb(bot_id: str, enabled: bool, owner: str | None) -> None:
        raise ValueError("callback error")

    hub = TermHub(on_hijack_changed=failing_cb)

    with caplog.at_level(logging.WARNING, logger="undef.terminal.hijack.hub"):
        hub.notify_hijack_changed("bot1", enabled=True, owner="me")
        await asyncio.sleep(0.05)  # let the fire-and-forget task run

    assert any("on_hijack_changed" in r.message for r in caplog.records), (
        "expected warning log for failed on_hijack_changed callback"
    )


async def test_notify_hijack_changed_successful_async_does_not_log(caplog) -> None:
    """Regression fix 4: a successful async callback produces no warning logs."""
    import logging

    async def ok_cb(bot_id: str, enabled: bool, owner: str | None) -> None:
        pass  # no exception

    hub = TermHub(on_hijack_changed=ok_cb)

    with caplog.at_level(logging.WARNING, logger="undef.terminal.hijack.hub"):
        hub.notify_hijack_changed("bot1", enabled=True, owner="me")
        await asyncio.sleep(0.05)

    assert not any("on_hijack_changed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Polling coverage — weak mutation survivors
# ---------------------------------------------------------------------------


async def test_snapshot_matches_both_constraints() -> None:
    """snapshot_matches with both prompt_id AND regex — both must be satisfied."""
    snapshot = {"prompt_detected": {"prompt_id": "menu"}, "screen": "Main Menu\nOptions:"}
    pattern = re.compile("Options", re.IGNORECASE)

    # Both match — returns True
    assert TermHub.snapshot_matches(snapshot, expect_prompt_id="menu", expect_regex=pattern)

    # Prompt matches, regex doesn't — returns False
    assert not TermHub.snapshot_matches(snapshot, expect_prompt_id="menu", expect_regex=re.compile("NotFound"))

    # Regex matches, prompt doesn't — returns False
    assert not TermHub.snapshot_matches(snapshot, expect_prompt_id="wrong", expect_regex=pattern)


async def test_snapshot_matches_regex_multiline() -> None:
    """snapshot_matches regex uses MULTILINE flag."""
    snapshot = {"screen": "line1\nline2 TARGET\nline3"}
    pattern = re.compile("^line2", re.MULTILINE)
    assert TermHub.snapshot_matches(snapshot, expect_prompt_id=None, expect_regex=pattern)


async def test_wait_for_guard_regex_compile_error_message() -> None:
    """wait_for_guard returns detailed error on invalid regex."""
    hub = TermHub()
    await hub._get("bot1")

    ok, snap, reason = await hub.wait_for_guard(
        "bot1",
        expect_prompt_id=None,
        expect_regex=r"(unclosed",
        timeout_ms=100,
        poll_interval_ms=10,
    )

    assert not ok
    assert snap is None
    assert "invalid expect_regex" in reason


async def test_wait_for_guard_timeout_ms_minimum() -> None:
    """wait_for_guard clamps timeout_ms to minimum 50ms."""
    hub = TermHub()
    await hub._get("bot1")
    hub._workers["bot1"].last_snapshot = {"screen": "test"}

    # timeout_ms=1 should be clamped to 50ms
    start = time.time()
    ok, snap, reason = await hub.wait_for_guard(
        "bot1",
        expect_prompt_id="nonexistent",
        expect_regex=None,
        timeout_ms=1,  # Will be clamped to 50
        poll_interval_ms=10,
    )
    elapsed = time.time() - start

    assert not ok
    assert reason == "prompt_guard_not_satisfied"
    assert elapsed >= 0.04  # At least ~50ms (clamped minimum)


async def test_wait_for_guard_poll_interval_minimum() -> None:
    """wait_for_guard clamps poll_interval_ms to minimum 20ms."""
    hub = TermHub()
    await hub._get("bot1")
    hub._workers["bot1"].last_snapshot = {"screen": "test", "ts": time.time()}

    # poll_interval_ms=1 should be clamped to 20ms
    start = time.time()
    ok, snap, reason = await hub.wait_for_guard(
        "bot1",
        expect_prompt_id="nonexistent",
        expect_regex=None,
        timeout_ms=100,
        poll_interval_ms=1,  # Will be clamped to 20
    )
    elapsed = time.time() - start

    # Should have at least 1 poll cycle (20ms)
    assert elapsed >= 0.015


async def test_wait_for_guard_matches_during_poll() -> None:
    """wait_for_guard matches snapshot during polling loop."""
    hub = TermHub()
    await hub._get("bot1")

    # Set initial snapshot without prompt_id
    hub._workers["bot1"].last_snapshot = {"screen": "initial"}

    # Simulate snapshot being updated in background
    async def update_snapshot() -> None:
        await asyncio.sleep(0.03)
        hub._workers["bot1"].last_snapshot = {
            "screen": "updated",
            "prompt_detected": {"prompt_id": "target"},
            "ts": time.time(),
        }

    task = asyncio.create_task(update_snapshot())
    ok, snap, reason = await hub.wait_for_guard(
        "bot1",
        expect_prompt_id="target",
        expect_regex=None,
        timeout_ms=500,
        poll_interval_ms=10,
    )
    await task

    assert ok
    assert snap is not None
    assert snap["screen"] == "updated"
    assert reason is None


async def test_wait_for_guard_no_new_snapshot_rerequests() -> None:
    """wait_for_guard re-requests snapshot when ts hasn't advanced."""
    hub = TermHub()
    await hub._get("bot1")

    request_count = 0
    original_request = hub.request_snapshot

    async def track_requests(worker_id: str) -> None:
        nonlocal request_count
        request_count += 1
        await original_request(worker_id)

    hub.request_snapshot = track_requests  # type: ignore[method-assign]

    # Set snapshot with old timestamp
    old_ts = time.time() - 1
    hub._workers["bot1"].last_snapshot = {
        "screen": "old",
        "ts": old_ts,
    }

    ok, snap, reason = await hub.wait_for_guard(
        "bot1",
        expect_prompt_id="nonexistent",
        expect_regex=None,
        timeout_ms=100,
        poll_interval_ms=20,
    )

    # Should have requested multiple times (initial + re-requests)
    assert request_count >= 2


async def test_wait_for_snapshot_with_fresh_snapshot() -> None:
    """wait_for_snapshot returns immediately when fresh snapshot available."""
    """wait_for_snapshot returns immediately when fresh snapshot available."""
    hub = TermHub()
    await hub._get("bot1")

    # Set fresh snapshot with timestamp in future (will be checked against req_ts)
    import time

    fresh_ts = time.time() + 1  # Definitely in the future
    hub._workers["bot1"].last_snapshot = {
        "screen": "fresh content",
        "ts": fresh_ts,
    }

    # Should return immediately without waiting for timeout
    start = time.time()
    result = await hub.wait_for_snapshot("bot1", timeout_ms=500)
    elapsed = time.time() - start

    assert result is not None
    assert result["screen"] == "fresh content"
    assert elapsed < 0.1  # Should be fast, not wait 500ms


async def test_wait_for_snapshot_ignores_older_ts() -> None:
    """wait_for_snapshot ignores snapshots with ts <= req_ts."""
    hub = TermHub()
    await hub._get("bot1")

    req_ts = time.time()

    # Manually set to just before request time
    hub._workers["bot1"].last_snapshot = {
        "screen": "old",
        "ts": req_ts - 0.1,
    }

    result = await hub.wait_for_snapshot("bot1", timeout_ms=50)

    # Should timeout because snapshot predates the request
    assert result is None


async def test_wait_for_snapshot_worker_disappears() -> None:
    """wait_for_snapshot returns None if worker is deleted during polling."""
    hub = TermHub()
    await hub._get("bot1")

    # Simulate worker being removed
    async def remove_worker() -> None:
        await asyncio.sleep(0.02)
        if "bot1" in hub._workers:
            del hub._workers["bot1"]

    task = asyncio.create_task(remove_worker())
    result = await hub.wait_for_snapshot("bot1", timeout_ms=200)
    await task

    assert result is None
