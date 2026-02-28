#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Integration tests for TermHub logic (direct method calls, no HTTP)."""

from __future__ import annotations

import asyncio
import json
import re
import time
from unittest.mock import AsyncMock

from undef.terminal.hijack.hub import TermHub
from undef.terminal.hijack.models import BotTermState, HijackSession

# ---------------------------------------------------------------------------
# State creation
# ---------------------------------------------------------------------------


async def test_get_creates_state() -> None:
    hub = TermHub()
    st = await hub._get("bot1")
    assert isinstance(st, BotTermState)
    assert "bot1" in hub._bots


async def test_get_returns_same_state() -> None:
    hub = TermHub()
    st1 = await hub._get("bot1")
    st2 = await hub._get("bot1")
    assert st1 is st2


async def test_is_hijacked_false_initially() -> None:
    hub = TermHub()
    st = await hub._get("bot1")
    assert not hub._is_hijacked(st)


# ---------------------------------------------------------------------------
# Cleanup — expired REST session
# ---------------------------------------------------------------------------


async def test_cleanup_expired_rest_session() -> None:
    hub = TermHub()
    await hub._get("bot1")
    hub._bots["bot1"].hijack_session = HijackSession(
        hijack_id="abc",
        owner="test",
        acquired_at=time.time() - 200,
        lease_expires_at=time.time() - 1,
        last_heartbeat=time.time() - 200,
    )
    expired = await hub._cleanup_expired_hijack("bot1")
    assert expired
    assert hub._bots["bot1"].hijack_session is None


async def test_cleanup_not_expired_rest_session() -> None:
    hub = TermHub()
    await hub._get("bot1")
    hub._bots["bot1"].hijack_session = HijackSession(
        hijack_id="abc",
        owner="test",
        acquired_at=time.time(),
        lease_expires_at=time.time() + 3600,
        last_heartbeat=time.time(),
    )
    expired = await hub._cleanup_expired_hijack("bot1")
    assert not expired
    assert hub._bots["bot1"].hijack_session is not None


# ---------------------------------------------------------------------------
# Cleanup — expired dashboard owner
# ---------------------------------------------------------------------------


async def test_cleanup_expired_dashboard_owner() -> None:
    hub = TermHub()
    await hub._get("bot1")
    mock_ws = AsyncMock()
    hub._bots["bot1"].hijack_owner = mock_ws
    hub._bots["bot1"].hijack_owner_expires_at = time.time() - 1
    expired = await hub._cleanup_expired_hijack("bot1")
    assert expired
    assert hub._bots["bot1"].hijack_owner is None
    assert hub._bots["bot1"].hijack_owner_expires_at is None


async def test_cleanup_missing_bot_returns_false() -> None:
    hub = TermHub()
    result = await hub._cleanup_expired_hijack("nonexistent")
    assert result is False


# ---------------------------------------------------------------------------
# Cleanup — resume message sent to worker
# ---------------------------------------------------------------------------


async def test_cleanup_sends_resume_to_worker() -> None:
    hub = TermHub()
    await hub._get("bot1")
    mock_ws = AsyncMock()
    hub._bots["bot1"].worker_ws = mock_ws
    hub._bots["bot1"].hijack_session = HijackSession(
        hijack_id="abc",
        owner="test",
        acquired_at=time.time() - 200,
        lease_expires_at=time.time() - 1,
        last_heartbeat=time.time() - 200,
    )
    await hub._cleanup_expired_hijack("bot1")
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
    hub._notify_hijack_changed("bot1", enabled=True, owner="me")
    assert results == [("bot1", True, "me")]


async def test_notify_hijack_changed_async() -> None:
    results: list[tuple] = []

    async def cb(bot_id: str, enabled: bool, owner: str | None) -> None:
        results.append((bot_id, enabled, owner))

    hub = TermHub(on_hijack_changed=cb)
    hub._notify_hijack_changed("bot1", enabled=True, owner="me")
    await asyncio.sleep(0)  # allow the scheduled task to run
    assert results == [("bot1", True, "me")]


async def test_notify_no_callback() -> None:
    hub = TermHub()
    # Should not raise
    hub._notify_hijack_changed("bot1", enabled=True, owner=None)


# ---------------------------------------------------------------------------
# _snapshot_matches
# ---------------------------------------------------------------------------


async def test_snapshot_matches_prompt_id() -> None:
    snapshot = {"prompt_detected": {"prompt_id": "main_menu"}, "screen": "hello"}
    assert TermHub._snapshot_matches(snapshot, expect_prompt_id="main_menu", expect_regex=None)


async def test_snapshot_matches_regex() -> None:
    snapshot = {"screen": "Welcome to the server"}
    pattern = re.compile("Welcome", re.IGNORECASE)
    assert TermHub._snapshot_matches(snapshot, expect_prompt_id=None, expect_regex=pattern)


async def test_snapshot_not_matches_wrong_prompt_id() -> None:
    snapshot = {"prompt_detected": {"prompt_id": "main_menu"}, "screen": "hello"}
    assert not TermHub._snapshot_matches(snapshot, expect_prompt_id="other", expect_regex=None)


async def test_snapshot_not_matches_none() -> None:
    assert not TermHub._snapshot_matches(None, expect_prompt_id="main_menu", expect_regex=None)


async def test_snapshot_matches_no_constraints() -> None:
    # Both constraints None → always True when snapshot is non-None
    snapshot = {"screen": "anything"}
    assert TermHub._snapshot_matches(snapshot, expect_prompt_id=None, expect_regex=None)


# ---------------------------------------------------------------------------
# _clamp_lease
# ---------------------------------------------------------------------------


async def test_clamp_lease_minimum() -> None:
    assert TermHub._clamp_lease(0) == 1


async def test_clamp_lease_normal() -> None:
    assert TermHub._clamp_lease(300) == 300


async def test_clamp_lease_maximum() -> None:
    assert TermHub._clamp_lease(9999) == 3600


# ---------------------------------------------------------------------------
# _is_dashboard_hijack_active
# ---------------------------------------------------------------------------


async def test_is_dashboard_hijack_active_expired() -> None:
    st = BotTermState()
    st.hijack_owner = AsyncMock()
    st.hijack_owner_expires_at = time.time() - 1
    assert not TermHub._is_dashboard_hijack_active(st)


async def test_is_dashboard_hijack_active_no_expiry() -> None:
    st = BotTermState()
    st.hijack_owner = AsyncMock()
    st.hijack_owner_expires_at = None  # no expiry → permanent
    assert TermHub._is_dashboard_hijack_active(st)


async def test_is_dashboard_hijack_active_future() -> None:
    st = BotTermState()
    st.hijack_owner = AsyncMock()
    st.hijack_owner_expires_at = time.time() + 3600
    assert TermHub._is_dashboard_hijack_active(st)


async def test_is_dashboard_hijack_active_no_owner() -> None:
    st = BotTermState()
    assert not TermHub._is_dashboard_hijack_active(st)
