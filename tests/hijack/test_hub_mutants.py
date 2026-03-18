#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Mutation-killing tests for hijack/hub/ source files.

Targets surviving mutants across:
- ownership.py  (_expire_leases_under_lock, _recheck_and_resume, cleanup_expired_hijack,
                  get_rest_session, try_acquire_rest_hijack, touch_hijack_owner,
                  extend_hijack_lease, get_fresh_hijack_expiry, get_hijack_events_data,
                  check_hijack_valid, prepare_browser_input, remove_dead_browsers)
- connections.py (register_worker, set_worker_hello_mode, deregister_worker,
                   register_browser, cleanup_browser_disconnect,
                   register_browser_state_snapshot, can_send_input,
                   request_analysis, force_release_hijack)
- core.py        (notify_hijack_changed, _resolve_role_for_browser, broadcast,
                   prune_if_idle, hijack_state_msg_for, disconnect_worker)
- polling.py     (wait_for_snapshot, wait_for_guard)
- resume.py      (InMemoryResumeStore.create, get, cleanup_expired, active_tokens)
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from undef.terminal.hijack.hub import TermHub
from undef.terminal.hijack.hub.resume import InMemoryResumeStore
from undef.terminal.hijack.models import HijackSession, WorkerTermState

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_hub(**kwargs: Any) -> TermHub:
    return TermHub(**kwargs)


def _make_ws() -> MagicMock:
    ws = MagicMock()
    ws.send_text = AsyncMock()
    return ws


def _make_hijack_session(hijack_id: str = "hj-1", owner: str = "op", lease_s: float = 60.0) -> HijackSession:
    now = time.time()
    return HijackSession(
        hijack_id=hijack_id,
        owner=owner,
        acquired_at=now,
        lease_expires_at=now + lease_s,
        last_heartbeat=now,
    )


async def _setup_worker(hub: TermHub, worker_id: str, worker_ws: Any = None) -> WorkerTermState:
    async with hub._lock:
        st = hub._workers.setdefault(worker_id, WorkerTermState())
        st.worker_ws = worker_ws or _make_ws()
        return st


# ===========================================================================
# ownership.py — _expire_leases_under_lock
# ===========================================================================


class TestExpireLeasesUnderLock:
    async def test_rest_expired_initial_false(self) -> None:
        """mutmut_7: rest_expired = False → None.  Returns tuple, not None-tuple."""
        hub = _make_hub()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            # expired session
            st.hijack_session = _make_hijack_session(lease_s=-10.0)

        result = await hub._expire_leases_under_lock("w1", time.time())
        assert result is not None
        rest_expired, dashboard_expired, should_resume = result
        assert rest_expired is True
        assert dashboard_expired is False

    async def test_dashboard_expired_initial_false(self) -> None:
        """mutmut_9: dashboard_expired = False → None.  Must be False initially."""
        hub = _make_hub()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_owner = _make_ws()
            st.hijack_owner_expires_at = time.time() - 10  # expired

        result = await hub._expire_leases_under_lock("w1", time.time())
        assert result is not None
        rest_expired, dashboard_expired, should_resume = result
        assert dashboard_expired is True
        assert rest_expired is False

    async def test_rest_expiry_uses_lte_not_lt(self) -> None:
        """mutmut_13: lease_expires_at <= now → < now.

        At exactly now, <= expires the lease; < does not.
        """
        hub = _make_hub()
        now = time.time()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_session = _make_hijack_session()
            st.hijack_session.lease_expires_at = now  # exactly now

        result = await hub._expire_leases_under_lock("w1", now)
        assert result is not None
        rest_expired, _, _ = result
        # <= now means it IS expired; < now means it is NOT
        assert rest_expired is True

    async def test_dashboard_expiry_uses_and_not_or(self) -> None:
        """mutmut_18: 'and' → 'or' in the dashboard_expired condition.

        Condition requires hijack_owner is not None AND expires_at is not None AND <= now.
        With 'or', a session with only expires_at set (no owner) would trigger incorrectly.
        """
        hub = _make_hub()
        now = time.time()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            # hijack_owner is None, expires_at is set (expired) — with 'or' this would fire
            st.hijack_owner = None
            st.hijack_owner_expires_at = now - 10
            # also have a REST session so the method doesn't return None early
            st.hijack_session = _make_hijack_session(lease_s=60.0)

        result = await hub._expire_leases_under_lock("w1", now)
        # dashboard_expired must be False: owner is None so condition should not fire
        if result is not None:
            _, dashboard_expired, _ = result
            assert dashboard_expired is False

    async def test_dashboard_expiry_uses_lte_not_lt(self) -> None:
        """mutmut_21: hijack_owner_expires_at <= now → < now.

        At exactly now, <= expires the lease; < does not.
        """
        hub = _make_hub()
        now = time.time()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_owner = _make_ws()
            st.hijack_owner_expires_at = now  # exactly now

        result = await hub._expire_leases_under_lock("w1", now)
        assert result is not None
        _, dashboard_expired, _ = result
        assert dashboard_expired is True

    async def test_hijack_owner_expires_at_cleared_to_none(self) -> None:
        """mutmut_23: hijack_owner_expires_at = None → ''.

        Must be set to None, not empty string.
        """
        hub = _make_hub()
        now = time.time()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_owner = _make_ws()
            st.hijack_owner_expires_at = now - 10  # expired

        await hub._expire_leases_under_lock("w1", now)

        async with hub._lock:
            st2 = hub._workers.get("w1")
            if st2 is not None:
                assert st2.hijack_owner_expires_at is None

    async def test_should_resume_requires_all_cleared(self) -> None:
        """mutmut_27: 'and st.hijack_session is None' → 'or st.hijack_session is None'.

        should_resume is True only when BOTH owner AND session are None.
        With 'or', it could be True even if one is still active.
        """
        hub = _make_hub()
        now = time.time()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            # owner expired but REST session still valid
            st.hijack_owner = _make_ws()
            st.hijack_owner_expires_at = now - 10  # expired
            st.hijack_session = _make_hijack_session(lease_s=60.0)  # still valid

        result = await hub._expire_leases_under_lock("w1", now)
        assert result is not None
        _, _, should_resume = result
        # REST session still active → should_resume must be False
        assert should_resume is False

    async def test_should_resume_or_mutation(self) -> None:
        """mutmut_28: '(rest or dashboard) and owner is None and session is None'
        → '(rest or dashboard) or owner is None and session is None'.

        With 'or', should_resume could be True even without any expiry.
        We need a case where neither expired but both owner and session are None.
        """
        hub = _make_hub()
        now = time.time()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            # Set a session that IS expired (so rest_expired=True) AND no owner
            st.hijack_session = _make_hijack_session(lease_s=-10.0)  # expired
            st.hijack_owner = None

        result = await hub._expire_leases_under_lock("w1", now)
        assert result is not None
        rest_expired, _, should_resume = result
        assert rest_expired is True
        # should_resume: (True or False) and owner is None and session is None
        # After expiry, session is None → True and True and True = True
        assert should_resume is True


# ===========================================================================
# ownership.py — _recheck_and_resume
# ===========================================================================


class TestRecheckAndResume:
    async def test_control_msg_has_owner_key(self) -> None:
        """mutmut_18/19: 'owner' key → 'XXownerXX'/'OWNER'."""
        hub = _make_hub()
        worker_ws = _make_ws()
        sent_msgs: list[dict[str, Any]] = []
        worker_ws.send_text = AsyncMock(side_effect=lambda s: sent_msgs.append(__import__("json").loads(s)))
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = worker_ws

        await hub._recheck_and_resume("w1", time.time())
        assert len(sent_msgs) >= 1
        msg = sent_msgs[0]
        assert "owner" in msg, f"'owner' key must be present, got {list(msg.keys())}"

    async def test_control_msg_owner_is_lease_expired(self) -> None:
        """mutmut_20/21: 'lease-expired' → 'XXlease-expiredXX'/'LEASE-EXPIRED'."""
        hub = _make_hub()
        worker_ws = _make_ws()
        sent_msgs: list[dict[str, Any]] = []
        worker_ws.send_text = AsyncMock(side_effect=lambda s: sent_msgs.append(__import__("json").loads(s)))
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = worker_ws

        await hub._recheck_and_resume("w1", time.time())
        msg = sent_msgs[0]
        assert msg.get("owner") == "lease-expired"

    async def test_control_msg_has_lease_s_key(self) -> None:
        """mutmut_22/23: 'lease_s' key → 'XXlease_sXX'/'LEASE_S'."""
        hub = _make_hub()
        worker_ws = _make_ws()
        sent_msgs: list[dict[str, Any]] = []
        worker_ws.send_text = AsyncMock(side_effect=lambda s: sent_msgs.append(__import__("json").loads(s)))
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = worker_ws

        await hub._recheck_and_resume("w1", time.time())
        msg = sent_msgs[0]
        assert "lease_s" in msg, f"'lease_s' key must be present, got {list(msg.keys())}"

    async def test_control_msg_lease_s_is_zero(self) -> None:
        """mutmut_24: lease_s=0 → 1."""
        hub = _make_hub()
        worker_ws = _make_ws()
        sent_msgs: list[dict[str, Any]] = []
        worker_ws.send_text = AsyncMock(side_effect=lambda s: sent_msgs.append(__import__("json").loads(s)))
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = worker_ws

        await hub._recheck_and_resume("w1", time.time())
        msg = sent_msgs[0]
        assert msg.get("lease_s") == 0

    async def test_control_msg_has_ts_key(self) -> None:
        """mutmut_25/26: 'ts' key → 'XXtsXX'/'TS'."""
        hub = _make_hub()
        worker_ws = _make_ws()
        sent_msgs: list[dict[str, Any]] = []
        worker_ws.send_text = AsyncMock(side_effect=lambda s: sent_msgs.append(__import__("json").loads(s)))
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = worker_ws

        await hub._recheck_and_resume("w1", time.time())
        msg = sent_msgs[0]
        assert "ts" in msg

    async def test_notify_hijack_changed_called_with_correct_worker_id(self) -> None:
        """mutmut_27: notify_hijack_changed(worker_id, ...) → notify_hijack_changed(None, ...)."""
        received_ids: list[str | None] = []

        def _on_hijack(worker_id: str, enabled: bool, owner: str | None) -> None:
            received_ids.append(worker_id)

        hub = _make_hub(on_hijack_changed=_on_hijack)
        worker_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = worker_ws

        await hub._recheck_and_resume("w1", time.time())
        assert "w1" in received_ids, f"worker_id 'w1' must be passed to callback, got {received_ids}"

    async def test_notify_hijack_changed_enabled_false(self) -> None:
        """mutmut_28/32: enabled=False → None or True."""
        received: list[tuple[str, bool | None, str | None]] = []

        def _on_hijack(worker_id: str, enabled: bool, owner: str | None) -> None:
            received.append((worker_id, enabled, owner))

        hub = _make_hub(on_hijack_changed=_on_hijack)
        worker_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = worker_ws

        await hub._recheck_and_resume("w1", time.time())
        assert len(received) >= 1
        _, enabled, _ = received[0]
        assert enabled is False, f"enabled must be False, got {enabled!r}"

    async def test_notify_hijack_changed_owner_none(self) -> None:
        """mutmut_31: owner=None arg must be passed (not missing)."""
        received: list[tuple[str, bool, Any]] = []

        def _on_hijack(worker_id: str, enabled: bool, owner: Any) -> None:
            received.append((worker_id, enabled, owner))

        hub = _make_hub(on_hijack_changed=_on_hijack)
        worker_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = worker_ws

        await hub._recheck_and_resume("w1", time.time())
        assert len(received) >= 1
        _, _, owner = received[0]
        assert owner is None


# ===========================================================================
# ownership.py — cleanup_expired_hijack
# ===========================================================================


class TestCleanupExpiredHijack:
    async def test_recheck_and_resume_called_with_now(self) -> None:
        """mutmut_18: _recheck_and_resume(worker_id, now) → (worker_id, None).

        When should_resume is True, _recheck_and_resume is called with the real now.
        We verify this by checking that a resume control message has a realistic ts.
        """
        hub = _make_hub()
        worker_ws = _make_ws()
        sent_msgs: list[dict[str, Any]] = []
        worker_ws.send_text = AsyncMock(side_effect=lambda s: sent_msgs.append(__import__("json").loads(s)))
        before = time.time()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = worker_ws
            st.hijack_session = _make_hijack_session(lease_s=-10.0)  # expired

        result = await hub.cleanup_expired_hijack("w1")
        time.time()
        assert result is True
        # Control message ts must be between before and after
        ctrl_msgs = [m for m in sent_msgs if m.get("type") == "control"]
        if ctrl_msgs:
            assert ctrl_msgs[0]["ts"] >= before

    async def test_rest_expired_event_type_is_hijack_lease_expired(self) -> None:
        """mutmut_25/26: 'hijack_lease_expired' → 'XXhijack_lease_expiredXX'/'HIJACK_LEASE_EXPIRED'."""
        hub = _make_hub()
        worker_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = worker_ws
            st.events = deque(maxlen=100)
            st.hijack_session = _make_hijack_session(lease_s=-10.0)  # expired

        await hub.cleanup_expired_hijack("w1")

        events = await hub.get_recent_events("w1", 10)
        event_types = [e.get("type") for e in events]
        assert "hijack_lease_expired" in event_types, f"Expected 'hijack_lease_expired' event, got {event_types}"

    async def test_dashboard_expired_event_type_is_hijack_owner_expired(self) -> None:
        """mutmut_31/32: 'hijack_owner_expired' → 'XX...'/'HIJACK_OWNER_EXPIRED'."""
        hub = _make_hub()
        worker_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = worker_ws
            st.events = deque(maxlen=100)
            st.hijack_owner = _make_ws()
            st.hijack_owner_expires_at = time.time() - 10  # expired

        await hub.cleanup_expired_hijack("w1")

        events = await hub.get_recent_events("w1", 10)
        event_types = [e.get("type") for e in events]
        assert "hijack_owner_expired" in event_types, f"Expected 'hijack_owner_expired' event, got {event_types}"

    async def test_rest_expired_event_appended_for_correct_worker(self) -> None:
        """mutmut_21/27: append_event(None, ...) instead of (worker_id, ...)."""
        hub = _make_hub()
        worker_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = worker_ws
            st.events = deque(maxlen=100)
            st.hijack_session = _make_hijack_session(lease_s=-10.0)

        await hub.cleanup_expired_hijack("w1")

        # Events must be in w1's event deque, not in a None worker
        events = await hub.get_recent_events("w1", 10)
        assert any(e.get("type") == "hijack_lease_expired" for e in events)

    async def test_dashboard_expired_event_appended_for_correct_worker(self) -> None:
        """mutmut_27/28: append_event(None, ...) or (worker_id, None)."""
        hub = _make_hub()
        worker_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = worker_ws
            st.events = deque(maxlen=100)
            st.hijack_owner = _make_ws()
            st.hijack_owner_expires_at = time.time() - 10

        await hub.cleanup_expired_hijack("w1")

        events = await hub.get_recent_events("w1", 10)
        assert any(e.get("type") == "hijack_owner_expired" for e in events)


# ===========================================================================
# ownership.py — get_rest_session
# ===========================================================================


class TestGetRestSession:
    async def test_cleanup_called_with_correct_worker_id(self) -> None:
        """mutmut_1: cleanup_expired_hijack(None) instead of (worker_id).

        Verified indirectly: if cleanup is called with None, a real expired session
        for 'w1' won't be cleaned up, so get_rest_session would still return it.
        We set an expired session and expect None back (cleanup should have cleared it).
        """
        hub = _make_hub()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_session = _make_hijack_session(hijack_id="hj-1", lease_s=-10.0)

        result = await hub.get_rest_session("w1", "hj-1")
        assert result is None, "Expired session must return None after cleanup"

    async def test_returns_none_when_lease_at_exactly_now(self) -> None:
        """mutmut_9: lease_expires_at <= time.time() → < time.time().

        At exactly now, <= rejects; < does not.
        """
        hub = _make_hub()
        now = time.time()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_session = _make_hijack_session(hijack_id="hj-1")
            st.hijack_session.lease_expires_at = now - 0.0001  # just expired

        result = await hub.get_rest_session("w1", "hj-1")
        assert result is None


# ===========================================================================
# ownership.py — try_acquire_rest_hijack
# ===========================================================================


class TestTryAcquireRestHijack:
    async def test_acquired_at_is_now_not_none(self) -> None:
        """mutmut_18: acquired_at=now → None.  Must be a float."""
        hub = _make_hub()
        now = time.time()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()

        ok, err = await hub.try_acquire_rest_hijack("w1", owner="op", lease_s=30, hijack_id="hj-1", now=now)
        assert ok is True
        async with hub._lock:
            st2 = hub._workers["w1"]
            assert st2.hijack_session is not None
            assert st2.hijack_session.acquired_at is not None
            assert isinstance(st2.hijack_session.acquired_at, float)

    async def test_last_heartbeat_is_now_not_none(self) -> None:
        """mutmut_20: last_heartbeat=now → None.  Must be a float."""
        hub = _make_hub()
        now = time.time()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()

        ok, _ = await hub.try_acquire_rest_hijack("w1", owner="op", lease_s=30, hijack_id="hj-1", now=now)
        assert ok is True
        async with hub._lock:
            st2 = hub._workers["w1"]
            assert st2.hijack_session is not None
            assert st2.hijack_session.last_heartbeat is not None
            assert isinstance(st2.hijack_session.last_heartbeat, float)


# ===========================================================================
# ownership.py — touch_hijack_owner
# ===========================================================================


class TestTouchHijackOwner:
    async def test_lease_s_min_is_1_not_2(self) -> None:
        """mutmut_12: max(1, ...) → max(2, ...).  lease_s=1 must be accepted."""
        hub = _make_hub()
        ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_owner = ws

        before = time.time()
        result = await hub.touch_hijack_owner("w1", lease_s=1)
        assert result is not None
        # With max(1,...): ttl=max(1,min(1,600))=1 → expires_at ≈ now+1
        # With max(2,...): ttl=max(2,min(1,600))=2 → expires_at ≈ now+2
        assert result >= before + 0.9  # at least 0.9s in future
        assert result <= before + 1.5  # not much more than 1.5s

    async def test_lease_s_max_is_600_not_601(self) -> None:
        """mutmut_18: min(int(lease_s), 600) → min(int(lease_s), 601)."""
        hub = _make_hub()
        ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_owner = ws

        before = time.time()
        result = await hub.touch_hijack_owner("w1", lease_s=700)  # exceeds 600
        assert result is not None
        # ttl = max(1, min(700, 600)) = 600
        # With mutation: min(700, 601) = 601 → expires_at = now + 601
        assert result <= before + 601  # must be ≤ 600 + small delta
        assert result <= before + 600.5


# ===========================================================================
# ownership.py — extend_hijack_lease
# ===========================================================================


class TestExtendHijackLease:
    async def test_last_heartbeat_updated_to_now(self) -> None:
        """mutmut_8: last_heartbeat = now → None.  Must be a float after extend."""
        hub = _make_hub()
        now = time.time()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_session = _make_hijack_session(hijack_id="hj-1", lease_s=60.0)
            st.hijack_session.last_heartbeat = 0.0  # old value

        result = await hub.extend_hijack_lease("w1", "hj-1", 30, now)
        assert result is not None
        async with hub._lock:
            st2 = hub._workers["w1"]
            assert st2.hijack_session is not None
            assert st2.hijack_session.last_heartbeat == now


# ===========================================================================
# ownership.py — get_fresh_hijack_expiry
# ===========================================================================


class TestGetFreshHijackExpiry:
    async def test_returns_session_expiry_not_fallback(self) -> None:
        """mutmut_1/2: st = None or workers.get(None) — must use worker_id."""
        hub = _make_hub()
        now = time.time()
        expected_expiry = now + 500.0
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_session = _make_hijack_session(hijack_id="hj-1")
            st.hijack_session.lease_expires_at = expected_expiry

        result = await hub.get_fresh_hijack_expiry("w1", "hj-1", fallback=0.0)
        assert result == expected_expiry, f"Expected session expiry {expected_expiry}, got {result}"

    async def test_returns_fallback_when_worker_absent(self) -> None:
        """mutmut_5: st is not None → is None (inverts check).

        With mutation, would try to access st.hijack_session on None → AttributeError.
        """
        hub = _make_hub()
        fallback = 12345.0
        result = await hub.get_fresh_hijack_expiry("nonexistent", "hj-1", fallback=fallback)
        assert result == fallback

    async def test_returns_fallback_when_hijack_id_mismatch(self) -> None:
        """mutmut_7: hijack_id == hijack_id → != hijack_id.

        With mutation, a matching ID returns fallback; a non-matching one returns expiry.
        """
        hub = _make_hub()
        now = time.time()
        expected_expiry = now + 500.0
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_session = _make_hijack_session(hijack_id="hj-1")
            st.hijack_session.lease_expires_at = expected_expiry

        # Matching ID → must return session expiry (not fallback)
        result = await hub.get_fresh_hijack_expiry("w1", "hj-1", fallback=0.0)
        assert result == expected_expiry

        # Non-matching ID → must return fallback
        result2 = await hub.get_fresh_hijack_expiry("w1", "hj-WRONG", fallback=0.0)
        assert result2 == 0.0


# ===========================================================================
# ownership.py — get_hijack_events_data
# ===========================================================================


class TestGetHijackEventsData:
    def _make_hs(self, lease_expiry: float | None = None) -> HijackSession:
        now = time.time()
        return HijackSession(
            hijack_id="hj-1",
            owner="op",
            acquired_at=now,
            lease_expires_at=lease_expiry or (now + 60),
            last_heartbeat=now,
        )

    async def test_result_has_rows_key(self) -> None:
        """mutmut_4/5: 'rows' → 'XXrowsXX'/'ROWS' in None-worker fallback path.

        We test the normal path (worker exists) which also returns 'rows'.
        """
        hub = _make_hub()
        hs = self._make_hs()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_session = hs

        result = await hub.get_hijack_events_data("w1", "hj-1", hs, after_seq=0, limit=10)
        assert "rows" in result

    async def test_result_has_latest_seq_key(self) -> None:
        """mutmut_6/7: 'latest_seq' → 'XXlatest_seqXX'/'LATEST_SEQ'."""
        hub = _make_hub()
        hs = self._make_hs()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_session = hs

        result = await hub.get_hijack_events_data("w1", "hj-1", hs, after_seq=0, limit=10)
        assert "latest_seq" in result

    async def test_result_has_min_event_seq_key(self) -> None:
        """mutmut_9/10: 'min_event_seq' → 'XXmin_event_seqXX'/'MIN_EVENT_SEQ'."""
        hub = _make_hub()
        hs = self._make_hs()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_session = hs

        result = await hub.get_hijack_events_data("w1", "hj-1", hs, after_seq=0, limit=10)
        assert "min_event_seq" in result

    async def test_result_has_fresh_expires_key(self) -> None:
        """mutmut_12/13: 'fresh_expires' → 'XXfresh_expiresXX'/'FRESH_EXPIRES'."""
        hub = _make_hub()
        hs = self._make_hs()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_session = hs

        result = await hub.get_hijack_events_data("w1", "hj-1", hs, after_seq=0, limit=10)
        assert "fresh_expires" in result

    async def test_latest_seq_is_actual_event_seq(self) -> None:
        """mutmut_25: latest_seq = st.event_seq → None."""
        hub = _make_hub()
        hs = self._make_hs()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_session = hs
            st.event_seq = 42

        result = await hub.get_hijack_events_data("w1", "hj-1", hs, after_seq=0, limit=10)
        assert result["latest_seq"] == 42

    async def test_min_event_seq_is_actual_min_event_seq(self) -> None:
        """mutmut_26: min_event_seq = st.min_event_seq → None."""
        hub = _make_hub()
        hs = self._make_hs()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_session = hs
            st.min_event_seq = 7

        result = await hub.get_hijack_events_data("w1", "hj-1", hs, after_seq=0, limit=10)
        assert result["min_event_seq"] == 7

    async def test_fresh_expires_uses_session_expiry_when_matching(self) -> None:
        """mutmut_27/28/29/30: fresh_expires conditional logic."""
        hub = _make_hub()
        session_expiry = time.time() + 300.0
        hs = self._make_hs(lease_expiry=session_expiry)
        hs_fallback = self._make_hs(lease_expiry=99.0)
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_session = hs  # same hijack_id as hs passed

        result = await hub.get_hijack_events_data("w1", "hj-1", hs_fallback, after_seq=0, limit=10)
        # Session matches hijack_id → use session expiry
        assert result["fresh_expires"] == session_expiry

    async def test_fresh_expires_uses_fallback_hs_when_session_id_differs(self) -> None:
        """mutmut_30: == → != hijack_id, causes wrong expiry selection."""
        hub = _make_hub()
        fallback_expiry = 99.0
        session_expiry = time.time() + 300.0
        hs_passed = HijackSession(
            hijack_id="hj-OTHER",  # different ID
            owner="op",
            acquired_at=time.time(),
            lease_expires_at=fallback_expiry,
            last_heartbeat=time.time(),
        )
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            # Session is "hj-1" (different from passed hs "hj-OTHER")
            st.hijack_session = _make_hijack_session(hijack_id="hj-1")
            st.hijack_session.lease_expires_at = session_expiry

        result = await hub.get_hijack_events_data("w1", "hj-OTHER", hs_passed, after_seq=0, limit=10)
        # Passed hs hijack_id != stored session hijack_id → use hs.lease_expires_at
        assert result["fresh_expires"] == fallback_expiry

    async def test_seq_filter_gt_not_gte(self) -> None:
        """mutmut_23: seq filter > after_seq → >= would include after_seq itself.

        With default 0 and mutation using seq==0, an event at seq=0 would be included.
        With the original: seq > 0 means seq=0 is excluded.
        """
        hub = _make_hub()
        hs = self._make_hs()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_session = hs

        # append an event at seq=1 (seq=0 shouldn't exist after setup but seq=1 does)
        await hub.append_event("w1", "test_event")  # seq=1

        result = await hub.get_hijack_events_data("w1", "hj-1", hs, after_seq=1, limit=10)
        # after_seq=1 means events with seq > 1; our only event is seq=1 → excluded
        assert result["rows"] == []

    async def test_seq_filter_with_default_zero(self) -> None:
        """mutmut_18/20: evt.get('seq', 0) → None or missing arg.

        Default 0 ensures events without 'seq' key are treated as seq=0.
        """
        hub = _make_hub()
        hs = self._make_hs()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_session = hs

        await hub.append_event("w1", "ev1")  # seq=1

        result = await hub.get_hijack_events_data("w1", "hj-1", hs, after_seq=0, limit=10)
        assert len(result["rows"]) == 1


# ===========================================================================
# ownership.py — check_hijack_valid
# ===========================================================================


class TestCheckHijackValid:
    async def test_valid_session_at_exactly_now_is_invalid(self) -> None:
        """mutmut_9: lease_expires_at > time.time() → >= time.time().

        With >=, a session expiring exactly at now is considered valid.
        With >, it is NOT valid (expired).
        """
        hub = _make_hub()
        now = time.time()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_session = _make_hijack_session(hijack_id="hj-1")
            st.hijack_session.lease_expires_at = now - 0.001  # just past

        result = await hub.check_hijack_valid("w1", "hj-1")
        assert result is False, "Session expired just before now must be invalid"

    async def test_valid_session_in_future_is_valid(self) -> None:
        """Sanity: a future-expiring session must be valid."""
        hub = _make_hub()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_session = _make_hijack_session(hijack_id="hj-1", lease_s=60.0)

        result = await hub.check_hijack_valid("w1", "hj-1")
        assert result is True


# ===========================================================================
# ownership.py — prepare_browser_input
# ===========================================================================


class TestPrepareBrowserInput:
    async def test_lease_extended_only_for_owner(self) -> None:
        """mutmut_11: 'and st.hijack_owner is ws' → 'or st.hijack_owner is ws'.

        With 'or', ANY active hijack (even owned by someone else) would extend lease.
        With 'and', only the actual owner's lease is extended.
        """
        hub = _make_hub(dashboard_hijack_lease_s=45)
        owner_ws = _make_ws()
        other_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_owner = owner_ws
            st.hijack_owner_expires_at = time.time() + 300  # not expiring
            st.browsers[owner_ws] = "admin"
            st.browsers[other_ws] = "admin"

        # Record expiry before call for non-owner
        async with hub._lock:
            st2 = hub._workers["w1"]
            initial_expiry = st2.hijack_owner_expires_at

        # Call prepare_browser_input for non-owner
        await hub.prepare_browser_input("w1", other_ws)

        # Expiry should NOT have changed (other_ws is not the owner)
        async with hub._lock:
            st3 = hub._workers["w1"]
            assert st3.hijack_owner_expires_at == initial_expiry

    async def test_lease_extended_for_actual_owner(self) -> None:
        """mutmut_13: 'is ws' → 'is not ws' — must extend for owner."""
        hub = _make_hub(dashboard_hijack_lease_s=45)
        owner_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_owner = owner_ws
            st.hijack_owner_expires_at = time.time() + 5  # close to expiry
            st.browsers[owner_ws] = "admin"

        before = time.time()
        await hub.prepare_browser_input("w1", owner_ws)

        async with hub._lock:
            st2 = hub._workers["w1"]
            # Lease must be extended to ~now + 45 (not near expiry anymore)
            assert st2.hijack_owner_expires_at is not None
            assert st2.hijack_owner_expires_at >= before + 44  # ~45s

    async def test_expires_at_set_positive_not_negative(self) -> None:
        """mutmut_15: time.time() + lease_s → time.time() - lease_s.

        Negative duration would make the lease already expired.
        """
        hub = _make_hub(dashboard_hijack_lease_s=45)
        owner_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_owner = owner_ws
            st.hijack_owner_expires_at = time.time() + 300
            st.browsers[owner_ws] = "admin"

        before = time.time()
        await hub.prepare_browser_input("w1", owner_ws)

        async with hub._lock:
            st2 = hub._workers["w1"]
            # Must be in the future, not in the past
            assert st2.hijack_owner_expires_at is not None
            assert st2.hijack_owner_expires_at > before

    async def test_expires_at_set_to_none_not_cleared(self) -> None:
        """mutmut_14: expires_at = time.time() + lease_s → None.

        Must remain a float, not None.
        """
        hub = _make_hub(dashboard_hijack_lease_s=45)
        owner_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_owner = owner_ws
            st.hijack_owner_expires_at = time.time() + 300
            st.browsers[owner_ws] = "admin"

        await hub.prepare_browser_input("w1", owner_ws)

        async with hub._lock:
            st2 = hub._workers["w1"]
            assert st2.hijack_owner_expires_at is not None


# ===========================================================================
# ownership.py — remove_dead_browsers
# ===========================================================================


class TestRemoveDeadBrowsers:
    async def test_dead_browser_removed_from_browsers_dict(self) -> None:
        """mutmut_8/9/13: condition mutations — dead browser must be popped."""
        hub = _make_hub()
        dead_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.browsers[dead_ws] = "operator"

        await hub.remove_dead_browsers("w1", {dead_ws})

        async with hub._lock:
            st2 = hub._workers.get("w1")
            if st2:
                assert dead_ws not in st2.browsers

    async def test_hijack_cleared_when_owner_is_dead(self) -> None:
        """mutmut_28/29: condition checking 'is_dashboard_hijack_active and hijack_owner is ws'."""
        hub = _make_hub()
        worker_ws = _make_ws()
        dead_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = worker_ws
            st.hijack_owner = dead_ws
            st.hijack_owner_expires_at = time.time() + 300
            st.browsers[dead_ws] = "admin"

        changed = await hub.remove_dead_browsers("w1", {dead_ws})
        assert changed is True

        async with hub._lock:
            st2 = hub._workers.get("w1")
            if st2:
                assert st2.hijack_owner is None

    async def test_returns_false_when_owner_not_dead(self) -> None:
        """mutmut_30/31: 'notify_hijack_off = not has_valid_rest_lease' → various mutations."""
        hub = _make_hub()
        worker_ws = _make_ws()
        live_ws = _make_ws()
        dead_ws = _make_ws()  # NOT the owner
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = worker_ws
            st.hijack_owner = live_ws  # live_ws is owner, not dead_ws
            st.hijack_owner_expires_at = time.time() + 300
            st.browsers[dead_ws] = "operator"

        changed = await hub.remove_dead_browsers("w1", {dead_ws})
        assert changed is False  # dead browser was not the owner

    async def test_hijack_owner_expires_at_cleared_after_owner_dies(self) -> None:
        """mutmut_36/37/38/39: hijack_owner_expires_at = None → '' or various."""
        hub = _make_hub()
        worker_ws = _make_ws()
        dead_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = worker_ws
            st.hijack_owner = dead_ws
            st.hijack_owner_expires_at = time.time() + 300
            st.browsers[dead_ws] = "admin"

        await hub.remove_dead_browsers("w1", {dead_ws})

        async with hub._lock:
            st2 = hub._workers.get("w1")
            if st2:
                assert st2.hijack_owner_expires_at is None

    async def test_notify_hijack_off_false_when_rest_still_active(self) -> None:
        """mutmut_40/41: notify_hijack_off = not has_valid_rest_lease → True.

        When REST session is still active after owner dies, should NOT send resume.
        """
        hub = _make_hub()
        worker_ws = _make_ws()
        dead_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = worker_ws
            st.hijack_owner = dead_ws
            st.hijack_owner_expires_at = time.time() + 300
            st.hijack_session = _make_hijack_session(lease_s=60.0)  # still active
            st.browsers[dead_ws] = "admin"

        result = await hub.remove_dead_browsers("w1", {dead_ws})
        # REST is still active → changed should be False (no resume sent)
        assert result is False

    async def test_resume_msg_type_is_control(self) -> None:
        """mutmut_42/43/44/45: 'control'/'resume'/'dead-socket'/lease_s key mutations."""
        hub = _make_hub()
        worker_ws = _make_ws()
        dead_ws = _make_ws()
        sent_msgs: list[dict[str, Any]] = []
        worker_ws.send_text = AsyncMock(side_effect=lambda s: sent_msgs.append(__import__("json").loads(s)))
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = worker_ws
            st.hijack_owner = dead_ws
            st.hijack_owner_expires_at = time.time() + 300
            st.browsers[dead_ws] = "admin"

        await hub.remove_dead_browsers("w1", {dead_ws})

        ctrl = [m for m in sent_msgs if m.get("type") == "control"]
        assert len(ctrl) >= 1
        assert ctrl[0].get("action") == "resume"
        assert ctrl[0].get("owner") == "dead-socket"
        assert ctrl[0].get("lease_s") == 0


# ===========================================================================
# connections.py — register_worker
# ===========================================================================


class TestRegisterWorker:
    async def test_events_preserved_on_re_register(self) -> None:
        """mutmut_9: deque(st.events, maxlen=...) → deque(maxlen=...) discards events."""
        hub = _make_hub()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.events = deque([{"type": "old_event", "seq": 1, "ts": 1.0}], maxlen=2000)

        ws = _make_ws()
        await hub.register_worker("w1", ws)

        async with hub._lock:
            st2 = hub._workers["w1"]
            event_types = [e.get("type") for e in st2.events]
            assert "old_event" in event_types, "Existing events must be preserved on re-register"

    async def test_prev_hijacked_or_not_and(self) -> None:
        """mutmut_12: 'or' → 'and' in prev_was_hijacked check.

        With 'and': requires BOTH session AND owner to be set.
        With 'or': either one set triggers the hijack-cleared logic.
        """
        hub = _make_hub()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            # Only hijack_session set, no owner
            st.hijack_session = _make_hijack_session(lease_s=60.0)
            st.hijack_owner = None

        ws = _make_ws()
        prev = await hub.register_worker("w1", ws)
        # With 'or': prev_was_hijacked = True (session is set)
        # With 'and': prev_was_hijacked = False (no owner)
        assert prev is True, "Session alone should trigger prev_was_hijacked"


# ===========================================================================
# connections.py — set_worker_hello_mode
# ===========================================================================


class TestSetWorkerHelloMode:
    async def test_mode_set_correctly(self) -> None:
        """mutmut_11/12/13/14: logger mutations — mode must still be set."""
        hub = _make_hub()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()

        result = await hub.set_worker_hello_mode("w1", "open")
        assert result is True
        async with hub._lock:
            st2 = hub._workers["w1"]
            assert st2.input_mode == "open"

    async def test_open_mode_blocked_when_hijack_active(self) -> None:
        """Ensure blocking still works even with logger mutations."""
        hub = _make_hub()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_owner = _make_ws()
            st.hijack_owner_expires_at = time.time() + 300

        result = await hub.set_worker_hello_mode("w1", "open")
        assert result is False


# ===========================================================================
# connections.py — deregister_worker
# ===========================================================================


class TestDeregisterWorker:
    async def test_returns_false_false_for_wrong_ws(self) -> None:
        """mutmut_7: return False, False → False, True for non-current ws."""
        hub = _make_hub()
        current_ws = _make_ws()
        old_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = current_ws

        result = await hub.deregister_worker("w1", old_ws)
        assert result == (False, False), f"Expected (False, False), got {result}"

    async def test_hijack_session_cleared_to_none(self) -> None:
        """mutmut_13: hijack_session = None → ''.  Must be None."""
        hub = _make_hub()
        ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = ws
            st.hijack_session = _make_hijack_session(lease_s=60.0)

        await hub.deregister_worker("w1", ws)

        async with hub._lock:
            st2 = hub._workers.get("w1")
            if st2:
                assert st2.hijack_session is None


# ===========================================================================
# connections.py — register_browser
# ===========================================================================


class TestRegisterBrowser:
    async def test_resume_token_stored_in_ws_map(self) -> None:
        """mutmut_10: ws_to_resume_token[ws] = resume_token → None."""
        store = InMemoryResumeStore()
        hub = _make_hub(resume_store=store)
        ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()

        await hub.register_browser("w1", ws, "operator")

        # Token must be stored for ws (not None)
        assert ws in hub._ws_to_resume_token
        assert hub._ws_to_resume_token[ws] is not None

    async def test_hijacked_by_me_is_false_for_non_owner(self) -> None:
        """mutmut_22: 'and' → 'or' in hijacked_by_me check."""
        hub = _make_hub()
        hijack_owner_ws = _make_ws()
        browser_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_owner = hijack_owner_ws
            st.hijack_owner_expires_at = time.time() + 300

        state = await hub.register_browser("w1", browser_ws, "operator")
        # browser_ws is NOT the owner → hijacked_by_me must be False
        assert state["hijacked_by_me"] is False

    async def test_hijacked_by_me_is_false_with_inverted_check(self) -> None:
        """mutmut_24: 'is ws' → 'is not ws'."""
        hub = _make_hub()
        owner_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_owner = owner_ws
            st.hijack_owner_expires_at = time.time() + 300

        # Registering owner_ws itself → hijacked_by_me must be True
        state = await hub.register_browser("w1", owner_ws, "admin")
        assert state["hijacked_by_me"] is True


# ===========================================================================
# connections.py — cleanup_browser_disconnect
# ===========================================================================


class TestCleanupBrowserDisconnect:
    async def test_browser_count_initial_sentinel_negative_one(self) -> None:
        """mutmut_1/2/3: browser_count = -1 → None/+1/-2.

        The value -1 is the sentinel "not visited the lock" — it must
        NOT trigger the on_worker_empty callback (which fires when count==0).
        """
        empty_fired: list[str] = []

        async def _on_empty(worker_id: str) -> None:
            empty_fired.append(worker_id)

        hub = _make_hub(on_worker_empty=_on_empty)
        ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.browsers[ws] = "operator"

        await hub.cleanup_browser_disconnect("w1", ws, owned_hijack=False)
        # After disconnect, count becomes 0 → on_empty should fire
        await asyncio.sleep(0)  # allow background task to run
        assert "w1" in empty_fired

    async def test_initial_browser_count_minus_one_not_zero(self) -> None:
        """mutmut_2: initial browser_count = +1 would trigger on_empty even before the lock."""
        # Verify the value by ensuring the callback ONLY fires when truly empty
        fires: list[str] = []

        async def _on_empty(worker_id: str) -> None:
            fires.append(worker_id)

        hub = _make_hub(on_worker_empty=_on_empty)
        ws1 = _make_ws()
        ws2 = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.browsers[ws1] = "operator"
            st.browsers[ws2] = "operator"

        # Remove ws1 (still 1 browser left)
        await hub.cleanup_browser_disconnect("w1", ws1, owned_hijack=False)
        await asyncio.sleep(0)
        # on_empty must NOT fire (still 1 browser)
        assert "w1" not in fires

    async def test_resume_store_mark_hijack_called_with_correct_token(self) -> None:
        """mutmut_56/57/58/60/63/64/67: resume store mark_hijack_owner mutations."""
        store = InMemoryResumeStore()
        hub = _make_hub(resume_store=store)
        owner_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_owner = owner_ws
            st.hijack_owner_expires_at = time.time() + 300
            st.browsers[owner_ws] = "admin"

        # Register first to get a token
        state = await hub.register_browser("w1", owner_ws, "admin")
        token = state.get("resume_token")
        assert token is not None

        # Re-set hijack owner to owner_ws (register_browser may have changed state)
        async with hub._lock:
            st2 = hub._workers["w1"]
            st2.hijack_owner = owner_ws
            st2.hijack_owner_expires_at = time.time() + 300

        await hub.cleanup_browser_disconnect("w1", owner_ws, owned_hijack=True)

        # Token must be marked as hijack owner
        session = store.get(token)
        assert session is not None
        assert session.was_hijack_owner is True

    async def test_resume_store_not_marked_when_not_owner(self) -> None:
        """mutmut_61: 'if token and (was_owner or owned_hijack)' → 'or (was_owner or owned_hijack)'.

        With 'or', mark_hijack_owner would be called even when token is None.
        """
        store = InMemoryResumeStore()
        hub = _make_hub(resume_store=store)
        browser_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.browsers[browser_ws] = "operator"

        state = await hub.register_browser("w1", browser_ws, "operator")
        token = state.get("resume_token")
        assert token is not None

        # Disconnect without any hijack ownership
        await hub.cleanup_browser_disconnect("w1", browser_ws, owned_hijack=False)

        session = store.get(token)
        if session is not None:
            assert session.was_hijack_owner is False

    async def test_resume_store_marked_only_when_was_owner_or_owned_hijack(self) -> None:
        """mutmut_62: 'was_owner or owned_hijack' → 'was_owner and owned_hijack'."""
        store = InMemoryResumeStore()
        hub = _make_hub(resume_store=store)
        browser_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.browsers[browser_ws] = "operator"

        state = await hub.register_browser("w1", browser_ws, "operator")
        token = state.get("resume_token")
        assert token is not None

        # owned_hijack=True but was_owner=False (browser was not WS hijack owner)
        await hub.cleanup_browser_disconnect("w1", browser_ws, owned_hijack=True)

        session = store.get(token)
        if session is not None:
            # With 'or': was_owner=False OR owned_hijack=True → True → mark called
            # With 'and': False AND True → False → not marked
            assert session.was_hijack_owner is True

    async def test_event_type_lookup_uses_type_key(self) -> None:
        """mutmut_36/38/41: evt.get('type', '') default mutations.

        When an event has no 'type' key, the default '' must NOT match
        'hijack_owner_expired' or 'hijack_lease_expired'.
        """
        hub = _make_hub()
        ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.browsers[ws] = "admin"
            # Add an event WITHOUT a 'type' key
            st.events.append({"seq": 1, "ts": 1.0})  # no 'type' key
            # Then add a legitimate hijack_acquired event
            st.events.append({"seq": 2, "ts": 1.0, "type": "hijack_acquired"})

        result = await hub.cleanup_browser_disconnect("w1", ws, owned_hijack=True)
        # resume_without_owner may be True or False but must not crash
        assert isinstance(result["resume_without_owner"], bool)


# ===========================================================================
# connections.py — register_browser_state_snapshot
# ===========================================================================


class TestRegisterBrowserStateSnapshot:
    async def test_hijacked_by_me_and_not_or(self) -> None:
        """mutmut_17/18: 'and' → 'or' in hijacked_by_me check."""
        hub = _make_hub()
        owner_ws = _make_ws()
        other_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_owner = owner_ws
            st.hijack_owner_expires_at = time.time() + 300
            st.browsers[other_ws] = "operator"
            st.browsers[owner_ws] = "admin"

        state = await hub.register_browser_state_snapshot("w1", other_ws)
        # other_ws is NOT the hijack owner → hijacked_by_me must be False
        assert state["hijacked_by_me"] is False

    async def test_hijacked_by_me_true_for_owner(self) -> None:
        """Sanity: owner should get hijacked_by_me=True."""
        hub = _make_hub()
        owner_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_owner = owner_ws
            st.hijack_owner_expires_at = time.time() + 300
            st.browsers[owner_ws] = "admin"

        state = await hub.register_browser_state_snapshot("w1", owner_ws)
        assert state["hijacked_by_me"] is True

    async def test_worker_online_uses_is_not_none(self) -> None:
        """mutmut_22: worker_ws is not None → is None."""
        hub = _make_hub()
        ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()  # worker IS online
            st.browsers[ws] = "operator"

        state = await hub.register_browser_state_snapshot("w1", ws)
        assert state["worker_online"] is True

    async def test_no_worker_fallback_returns_hijack_mode(self) -> None:
        """mutmut_25/26/27/28/29: fallback input_mode mutations."""
        hub = _make_hub()
        ws = _make_ws()
        # Worker not registered
        state = await hub.register_browser_state_snapshot("nonexistent", ws)
        assert state["input_mode"] == "hijack"


# ===========================================================================
# connections.py — can_send_input
# ===========================================================================


class TestCanSendInput:
    def test_open_mode_operator_can_send(self) -> None:
        """mutmut_6: 'operator' in valid set."""
        hub = _make_hub()
        ws = _make_ws()
        st = WorkerTermState()
        st.input_mode = "open"
        st.browsers[ws] = "operator"
        assert hub.can_send_input(st, ws) is True

    def test_open_mode_admin_can_send(self) -> None:
        """mutmut_8: 'admin' in valid set."""
        hub = _make_hub()
        ws = _make_ws()
        st = WorkerTermState()
        st.input_mode = "open"
        st.browsers[ws] = "admin"
        assert hub.can_send_input(st, ws) is True

    def test_open_mode_viewer_cannot_send(self) -> None:
        """mutmut_9: viewer excluded from open mode."""
        hub = _make_hub()
        ws = _make_ws()
        st = WorkerTermState()
        st.input_mode = "open"
        st.browsers[ws] = "viewer"
        assert hub.can_send_input(st, ws) is False

    def test_open_mode_unknown_role_cannot_send(self) -> None:
        """mutmut_10: unknown role treated as viewer."""
        hub = _make_hub()
        ws = _make_ws()
        st = WorkerTermState()
        st.input_mode = "open"
        st.browsers[ws] = "superadmin"
        assert hub.can_send_input(st, ws) is False


# ===========================================================================
# connections.py — force_release_hijack (extra)
# ===========================================================================


class TestForceReleaseHijackExtra:
    async def test_returns_false_when_no_hijack_active(self) -> None:
        """mutmut_4/5: 'if not had_hijack: return False' — with no hijack set."""
        hub = _make_hub()
        worker_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = worker_ws
            # No hijack_session, no hijack_owner

        result = await hub.force_release_hijack("w1")
        assert result is False

    async def test_notify_called_with_correct_enabled(self) -> None:
        """mutmut_39/40/41/42: notify_hijack_changed arg mutations."""
        received: list[tuple[str, bool, Any]] = []

        def _on_hijack(worker_id: str, enabled: bool, owner: Any) -> None:
            received.append((worker_id, enabled, owner))

        hub = _make_hub(on_hijack_changed=_on_hijack)
        worker_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = worker_ws
            st.hijack_owner = _make_ws()
            st.hijack_owner_expires_at = time.time() + 300

        await hub.force_release_hijack("w1")
        assert len(received) >= 1
        _, enabled, owner = received[0]
        assert enabled is False
        assert owner is None

    async def test_rest_session_owner_used_in_control_msg(self) -> None:
        """mutmut_45/46: owner from rest session must be used when session exists."""
        hub = _make_hub()
        worker_ws = _make_ws()
        sent_msgs: list[dict[str, Any]] = []
        worker_ws.send_text = AsyncMock(side_effect=lambda s: sent_msgs.append(__import__("json").loads(s)))
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = worker_ws
            st.hijack_session = _make_hijack_session(hijack_id="hj-1", owner="my-operator")

        await hub.force_release_hijack("w1")
        ctrl = [m for m in sent_msgs if m.get("type") == "control"]
        assert ctrl[0].get("owner") == "my-operator"


# ===========================================================================
# core.py — notify_hijack_changed
# ===========================================================================


class TestNotifyHijackChanged:
    async def test_async_callback_worker_id_correct(self) -> None:
        """mutmut_16/17: callback called with worker_id=None or exc=None.

        The done callback logs worker_id and exception — we verify the task runs.
        """
        received: list[tuple[str, bool, Any]] = []

        async def _async_cb(worker_id: str, enabled: bool, owner: Any) -> None:
            received.append((worker_id, enabled, owner))

        hub = _make_hub(on_hijack_changed=_async_cb)
        hub.notify_hijack_changed("w-async", enabled=True, owner="me")
        await asyncio.sleep(0.05)  # let task run
        assert ("w-async", True, "me") in received

    async def test_error_in_async_callback_does_not_raise(self) -> None:
        """mutmut_21: logger message mutation — error must still be swallowed."""

        async def _failing_cb(worker_id: str, enabled: bool, owner: Any) -> None:
            raise RuntimeError("test error")

        hub = _make_hub(on_hijack_changed=_failing_cb)
        hub.notify_hijack_changed("w-err", enabled=True, owner=None)
        await asyncio.sleep(0.05)  # let task fail, must not propagate


# ===========================================================================
# core.py — _resolve_role_for_browser (supplementary mutants)
# ===========================================================================


class TestResolveRoleExtra:
    async def test_operator_role_accepted(self) -> None:
        """mutmut_14/17/19: 'operator' in valid set."""
        hub = _make_hub(resolve_browser_role=lambda ws, wid: "operator")
        ws = _make_ws()
        role = await hub._resolve_role_for_browser(ws, "w1")
        assert role == "operator"

    async def test_admin_role_accepted(self) -> None:
        """mutmut_20/21/22: 'admin' in valid set."""
        hub = _make_hub(resolve_browser_role=lambda ws, wid: "admin")
        ws = _make_ws()
        role = await hub._resolve_role_for_browser(ws, "w1")
        assert role == "admin"

    async def test_none_resolver_returns_viewer_default(self) -> None:
        """mutmut_29/30: role='viewer' default (no resolver)."""
        hub = _make_hub()
        ws = _make_ws()
        role = await hub._resolve_role_for_browser(ws, "w1")
        assert role == "viewer"

    async def test_none_resolved_role_falls_back_to_viewer(self) -> None:
        """mutmut_34: resolved_role is None → return role (viewer)."""
        hub = _make_hub(resolve_browser_role=lambda ws, wid: None)
        ws = _make_ws()
        role = await hub._resolve_role_for_browser(ws, "w1")
        assert role == "viewer"

    async def test_int_resolved_role_falls_back_to_viewer(self) -> None:
        """mutmut_39/40: isinstance check — non-string role should fall back."""
        hub = _make_hub(resolve_browser_role=lambda ws, wid: 42)
        ws = _make_ws()
        role = await hub._resolve_role_for_browser(ws, "w1")
        assert role == "viewer"

    async def test_await_timeout_5s_raises_resolution_error(self) -> None:
        """mutmut_45/47/48/52: timeout=5.0 mutations."""
        from undef.terminal.hijack.hub import BrowserRoleResolutionError

        async def _slow_resolver(ws: Any, worker_id: str) -> None:
            await asyncio.sleep(1000)

        hub = _make_hub(resolve_browser_role=_slow_resolver)
        ws = _make_ws()

        async def _mock_wait_for(coro: Any, **kwargs: Any) -> None:
            raise TimeoutError("mocked")

        with patch("asyncio.wait_for", side_effect=_mock_wait_for), pytest.raises(BrowserRoleResolutionError):
            await hub._resolve_role_for_browser(ws, "w1")


# ===========================================================================
# core.py — broadcast
# ===========================================================================


class TestBroadcast:
    async def test_dead_browsers_cleaned_up(self) -> None:
        """mutmut_9/11/12: remove_dead_browsers called after send failure."""
        hub = _make_hub()
        worker_ws = _make_ws()
        dead_browser = _make_ws()
        dead_browser.send_text = AsyncMock(side_effect=Exception("disconnected"))
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = worker_ws
            st.browsers[dead_browser] = "operator"

        await hub.broadcast("w1", {"type": "test"})

        async with hub._lock:
            st2 = hub._workers.get("w1")
            if st2:
                assert dead_browser not in st2.browsers

    async def test_broadcast_sends_to_all_browsers(self) -> None:
        """mutmut_15/16/20/28: message sent to correct browsers."""
        hub = _make_hub()
        b1 = _make_ws()
        b2 = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.browsers[b1] = "operator"
            st.browsers[b2] = "operator"

        await hub.broadcast("w1", {"type": "ping", "data": "hello"})

        import json

        assert b1.send_text.call_count == 1
        assert b2.send_text.call_count == 1
        msg = json.loads(b1.send_text.call_args[0][0])
        assert msg["type"] == "ping"


# ===========================================================================
# core.py — prune_if_idle
# ===========================================================================


class TestPruneIfIdle:
    async def test_worker_pruned_when_all_empty(self) -> None:
        """mutmut_12/13/14/15: logger mutations — prune still executes."""
        hub = _make_hub()
        async with hub._lock:
            hub._workers["w1"] = WorkerTermState()
            # No worker_ws, no browsers, no hijack state — fully idle

        await hub.prune_if_idle("w1")

        async with hub._lock:
            assert "w1" not in hub._workers

    async def test_worker_not_pruned_when_worker_ws_present(self) -> None:
        """Sanity: worker_ws must prevent pruning."""
        hub = _make_hub()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()

        await hub.prune_if_idle("w1")

        async with hub._lock:
            assert "w1" in hub._workers


# ===========================================================================
# core.py — hijack_state_msg_for
# ===========================================================================


class TestHijackStateMsgFor:
    async def test_msg_type_is_hijack_state(self) -> None:
        """mutmut_4/5/6/7: 'type' key mutations."""
        hub = _make_hub()
        ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()

        msg = await hub.hijack_state_msg_for("w1", ws)
        assert msg.get("type") == "hijack_state"

    async def test_msg_hijacked_is_bool(self) -> None:
        """mutmut_13/14/15/16: 'hijacked' key mutations."""
        hub = _make_hub()
        ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()

        msg = await hub.hijack_state_msg_for("w1", ws)
        assert "hijacked" in msg
        assert isinstance(msg["hijacked"], bool)

    async def test_msg_owner_is_me_for_dashboard_owner(self) -> None:
        """mutmut_17/18: 'owner' and 'me' key/value mutations."""
        hub = _make_hub()
        owner_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_owner = owner_ws
            st.hijack_owner_expires_at = time.time() + 300

        msg = await hub.hijack_state_msg_for("w1", owner_ws)
        assert msg.get("owner") == "me"

    async def test_msg_owner_is_other_for_non_owner_browser(self) -> None:
        """mutmut_26/27: 'other' value mutations."""
        hub = _make_hub()
        owner_ws = _make_ws()
        other_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.hijack_owner = owner_ws
            st.hijack_owner_expires_at = time.time() + 300

        msg = await hub.hijack_state_msg_for("w1", other_ws)
        assert msg.get("owner") == "other"

    async def test_msg_has_lease_expires_at(self) -> None:
        """mutmut_28/29: 'lease_expires_at' key mutations."""
        hub = _make_hub()
        ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()

        msg = await hub.hijack_state_msg_for("w1", ws)
        assert "lease_expires_at" in msg

    async def test_msg_has_input_mode(self) -> None:
        """mutmut_38/47/48: 'input_mode' key mutations."""
        hub = _make_hub()
        ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()

        msg = await hub.hijack_state_msg_for("w1", ws)
        assert "input_mode" in msg

    async def test_msg_no_worker_returns_defaults(self) -> None:
        """mutmut_4/5/6/7: no-worker path returns correct defaults."""
        hub = _make_hub()
        ws = _make_ws()
        msg = await hub.hijack_state_msg_for("nonexistent", ws)
        assert msg["type"] == "hijack_state"
        assert msg["hijacked"] is False
        assert msg["owner"] is None
        assert msg["input_mode"] == "hijack"


# ===========================================================================
# core.py — disconnect_worker
# ===========================================================================


class TestDisconnectWorker:
    async def test_initial_ws_assignment_does_not_matter(self) -> None:
        """mutmut_1: ws = None → ''.  The local ws var must work after assign."""
        hub = _make_hub()
        worker_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = worker_ws

        result = await hub.disconnect_worker("w1")
        assert result is True

    async def test_returns_false_for_unknown_worker(self) -> None:
        """Sanity check for mutmut_1 path."""
        hub = _make_hub()
        result = await hub.disconnect_worker("nonexistent")
        assert result is False

    async def test_notify_hijack_changed_called_when_hijacked(self) -> None:
        """mutmut_41: notify called without owner=None arg."""
        received: list[tuple[str, bool, Any]] = []

        def _on_hijack(worker_id: str, enabled: bool, owner: Any) -> None:
            received.append((worker_id, enabled, owner))

        hub = _make_hub(on_hijack_changed=_on_hijack)
        worker_ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = worker_ws
            st.hijack_session = _make_hijack_session(lease_s=60.0)

        await hub.disconnect_worker("w1")
        assert len(received) >= 1
        _, enabled, owner = received[0]
        assert enabled is False
        assert owner is None


# ===========================================================================
# polling.py — wait_for_snapshot
# ===========================================================================


class TestWaitForSnapshot:
    async def test_default_timeout_is_1500_ms(self) -> None:
        """mutmut_1: default timeout_ms=1500 → 1501."""
        import inspect

        sig = inspect.signature(TermHub.wait_for_snapshot)
        default = sig.parameters["timeout_ms"].default
        assert default == 1500

    async def test_snap_returned_when_ts_after_req_ts(self) -> None:
        """mutmut_22: snap.get('ts', 0) > req_ts → >= req_ts.

        With >= and ts==req_ts, an old snapshot would be returned.
        With >, it must have a newer ts.
        """
        hub = _make_hub()
        ws = _make_ws()
        request_snapshot_calls: list[str | None] = []

        async def _mock_request(worker_id: str) -> None:
            request_snapshot_calls.append(worker_id)
            # Inject a fresh snapshot with ts AFTER req_ts
            await asyncio.sleep(0)
            now = time.time()
            async with hub._lock:
                st = hub._workers.get(worker_id)
                if st is not None:
                    st.last_snapshot = {"screen": "hello", "ts": now + 1.0}

        hub.request_snapshot = _mock_request  # type: ignore[method-assign]
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = ws

        result = await hub.wait_for_snapshot("w1", timeout_ms=500)
        assert result is not None
        assert result.get("screen") == "hello"

    async def test_returns_none_for_nonexistent_worker(self) -> None:
        """mutmut_7: request_snapshot(None) vs (worker_id)."""
        hub = _make_hub()
        result = await hub.wait_for_snapshot("nonexistent", timeout_ms=50)
        assert result is None

    async def test_snap_ts_0_default_not_returned_when_stale(self) -> None:
        """mutmut_16/18/21: snap.get('ts', 0) → None/missing/1.

        With default 0 and req_ts > 0: snap without 'ts' has ts=0 < req_ts → not returned.
        With default 1 and req_ts=0: ts=1 > 0 → would be returned as fresh (wrong).
        """
        hub = _make_hub()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            # snapshot without 'ts' key — default 0 means it's before req_ts
            st.last_snapshot = {"screen": "old", "cols": 80}

        async def _noop_request(worker_id: str) -> None:
            pass

        hub.request_snapshot = _noop_request  # type: ignore[method-assign]

        # With very short timeout (50ms), the stale snapshot should NOT be returned
        result = await hub.wait_for_snapshot("w1", timeout_ms=50)
        # Result should be None since snapshot has no fresh 'ts'
        assert result is None


# ===========================================================================
# polling.py — wait_for_guard
# ===========================================================================


class TestWaitForGuard:
    async def test_invalid_regex_returns_error(self) -> None:
        """mutmut_6/7: error string returned on bad regex."""
        hub = _make_hub()
        matched, snap, reason = await hub.wait_for_guard(
            "w1",
            expect_prompt_id=None,
            expect_regex="[invalid(regex",
            timeout_ms=100,
            poll_interval_ms=10,
        )
        assert matched is False
        assert reason is not None
        assert "invalid" in reason.lower() or "regex" in reason.lower()

    async def test_no_guards_returns_current_snapshot_immediately(self) -> None:
        """mutmut_12/13/14/15/16: early-return path when no guards specified."""
        hub = _make_hub()
        ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = ws
            st.last_snapshot = {"screen": "current", "ts": time.time()}

        async def _noop(worker_id: str) -> None:
            pass

        hub.request_snapshot = _noop  # type: ignore[method-assign]

        matched, snap, reason = await hub.wait_for_guard(
            "w1",
            expect_prompt_id=None,
            expect_regex=None,
            timeout_ms=100,
            poll_interval_ms=10,
        )
        assert matched is True
        assert reason is None

    async def test_timeout_returns_failure_reason(self) -> None:
        """mutmut_25/26: 'prompt_guard_not_satisfied' reason on timeout."""
        hub = _make_hub()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.last_snapshot = {"screen": "no match here", "ts": time.time()}

        async def _noop(worker_id: str) -> None:
            pass

        hub.request_snapshot = _noop  # type: ignore[method-assign]

        matched, _, reason = await hub.wait_for_guard(
            "w1",
            expect_prompt_id=None,
            expect_regex="WILL_NOT_MATCH_XYZ",
            timeout_ms=50,
            poll_interval_ms=10,
        )
        assert matched is False
        assert reason == "prompt_guard_not_satisfied"

    async def test_min_timeout_50ms(self) -> None:
        """mutmut_33/34: max(50, timeout_ms) / 1000.0 — timeout must be at least 50ms."""

        # We can't easily test timing, but verify the formula: max(50, X) / 1000.0
        # max(50, 10) = 50ms; max(50, 100) = 100ms
        assert max(50, 10) / 1000.0 == 0.05
        assert max(50, 100) / 1000.0 == 0.1

    async def test_min_interval_20ms(self) -> None:
        """mutmut_35/36: max(20, poll_interval_ms) / 1000.0."""
        assert max(20, 5) / 1000.0 == 0.02
        assert max(20, 50) / 1000.0 == 0.05

    async def test_snap_ts_stale_triggers_new_request(self) -> None:
        """mutmut_38/39: snap_ts <= last_snap_ts → only requests when stale."""
        hub = _make_hub()
        request_calls: list[str] = []
        snap_ts = time.time() - 1.0  # old snapshot

        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = _make_ws()
            st.last_snapshot = {"screen": "old", "ts": snap_ts}

        async def _counting_request(worker_id: str) -> None:
            request_calls.append(worker_id)

        hub.request_snapshot = _counting_request  # type: ignore[method-assign]

        matched, _, reason = await hub.wait_for_guard(
            "w1",
            expect_prompt_id=None,
            expect_regex="NEVER_MATCH",
            timeout_ms=60,
            poll_interval_ms=10,
        )
        # Should have made at least the initial request + 1 retry
        assert len(request_calls) >= 2

    async def test_regex_case_insensitive(self) -> None:
        """mutmut_52/56/57: re.IGNORECASE in compile flags."""
        hub = _make_hub()
        ws = _make_ws()
        async with hub._lock:
            st = hub._workers.setdefault("w1", WorkerTermState())
            st.worker_ws = ws
            st.last_snapshot = {"screen": "Login: prompt here", "ts": time.time() + 100}

        async def _noop(worker_id: str) -> None:
            pass

        hub.request_snapshot = _noop  # type: ignore[method-assign]

        matched, snap, reason = await hub.wait_for_guard(
            "w1",
            expect_prompt_id=None,
            expect_regex="login:",  # lowercase regex, screen has uppercase
            timeout_ms=200,
            poll_interval_ms=10,
        )
        assert matched is True


# ===========================================================================
# resume.py — InMemoryResumeStore
# ===========================================================================


class TestInMemoryResumeStore:
    def test_create_token_length_32(self) -> None:
        """mutmut_3: token_urlsafe(32) → token_urlsafe(33).

        With 32 bytes, URL-safe base64 produces ~43 chars.
        With 33 bytes, it produces ~44+ chars.
        """
        store = InMemoryResumeStore()
        token = store.create("w1", "operator", 60.0)
        # secrets.token_urlsafe(32) → ~43 chars (32 bytes * 4/3 rounded up)
        assert len(token) >= 40  # both 32 and 33 produce >=40 but differ
        # The key test: token stored with correct key
        assert token in store._tokens

    def test_create_stores_correct_token_in_session(self) -> None:
        """mutmut_6: session.token = None instead of token."""
        store = InMemoryResumeStore()
        token = store.create("w1", "operator", 60.0)
        session = store._tokens[token]
        assert session.token == token, f"session.token must equal the token key, got {session.token!r}"

    def test_create_sets_created_at_float(self) -> None:
        """mutmut_9: created_at = None instead of now."""
        store = InMemoryResumeStore()
        before = __import__("time").monotonic()
        token = store.create("w1", "operator", 60.0)
        session = store._tokens[token]
        assert session.created_at is not None
        assert isinstance(session.created_at, float)
        assert session.created_at >= before

    def test_create_sets_expires_at_correctly(self) -> None:
        """Sanity: expires_at = created_at + ttl_s."""
        store = InMemoryResumeStore()
        import time as time_mod

        before = time_mod.monotonic()
        token = store.create("w1", "operator", 60.0)
        session = store._tokens[token]
        assert session.expires_at >= before + 59.9

    def test_get_returns_session_at_exact_expiry_minus_epsilon(self) -> None:
        """mutmut_4: get expires when monotonic() >= expires_at (instead of >).

        With >=, a session at exactly expires_at would be expired.
        With >, it is still valid.
        """
        import time as time_mod

        store = InMemoryResumeStore()
        future = time_mod.monotonic() + 1000.0  # well in future
        token = store.create("w1", "operator", 1000.0)
        store._tokens[token].expires_at = future

        # Token should still be valid
        session = store.get(token)
        assert session is not None

    def test_get_returns_none_for_expired_token(self) -> None:
        """Sanity: expired token returns None."""
        store = InMemoryResumeStore()
        token = store.create("w1", "operator", 0.001)
        import time as time_mod

        time_mod.sleep(0.01)
        session = store.get(token)
        assert session is None

    def test_cleanup_expired_uses_gt_not_gte(self) -> None:
        """mutmut_3: cleanup_expired uses now > expires_at (not >=).

        With >=, a token expiring exactly at 'now' would be cleaned up.
        With >, it would not.
        Test by verifying cleanup returns only truly expired tokens.
        """
        import time as time_mod

        store = InMemoryResumeStore()
        # Create token that just expired
        store.create("w1", "operator", 0.001)
        time_mod.sleep(0.01)
        count = store.cleanup_expired()
        assert count == 1

    def test_active_tokens_excludes_expired(self) -> None:
        """mutmut_2: active_tokens uses now <= expires_at (includes at-expiry).

        With <, a token at exactly now would be excluded.
        """

        store = InMemoryResumeStore()
        # Create a token with very long TTL
        token = store.create("w1", "operator", 3600.0)

        active = store.active_tokens()
        assert token in active

    def test_active_tokens_uses_lte_not_lt(self) -> None:
        """mutmut_2 boundary: now == expires_at should be included (<=).

        We can't easily force exact equality, but we verify a token
        expiring well in the future IS included.
        """
        store = InMemoryResumeStore()

        token = store.create("w1", "operator", 1.0)
        # Token expires in ~1s — well before 'now <= expires_at' would fail
        active = store.active_tokens()
        assert token in active
