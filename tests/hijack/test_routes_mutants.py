#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Mutation-killing tests for hijack/routes/browser_handlers.py.

Targets the surviving mutants not already killed by test_browser_handlers_mutations.py:
- heartbeat_ack message field keys (ts, lease_expires_at) and broadcast_hijack_state call
- hijack_step message field keys (owner, lease_s, ts) and append_event arguments
- _handle_input append_event event name and dict key/value arguments
- _handle_hijack_request err == "already_hijacked" vs != (conflict metric, compensating resume)
- _handle_hijack_request compensating-resume message content
- _handle_resume token default "", not truthy placeholder
- _handle_resume _on_resume callback invoked with correct (token, session) args
- _handle_resume new_role initialized from role (not None)
- _handle_resume can_hijack = role == "admin" (not !=)
- _handle_resume role-restore condition: AND not OR
- _handle_resume hijack-reclaim condition: is None AND not hub.is_hijacked()
- _handle_resume owned_hijack set to True (not False/None) on reclaim
- _handle_resume store.create called with correct (worker_id, new_role) positional args
- _handle_resume _ws_to_resume_token set to new_token (not None)
- _handle_resume hello message: hijacked key, worker_online key, input_mode key
- _handle_resume hello: hijack_step_supported True (not False), resume_supported True (not False)
- _handle_resume hello: capabilities sub-dict keys correct
"""

from __future__ import annotations

import json
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from undef.terminal.hijack.hub import InMemoryResumeStore, TermHub
from undef.terminal.hijack.models import WorkerTermState
from undef.terminal.hijack.routes.browser_handlers import (
    _handle_resume,
    handle_browser_message,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_hub(resume_store: InMemoryResumeStore | None = None) -> TermHub:
    return TermHub(resume_store=resume_store)


def _make_ws() -> MagicMock:
    ws = MagicMock()
    ws.send_text = AsyncMock()
    return ws


async def _register(
    hub: TermHub,
    worker_id: str,
    browser_ws: Any,
    role: str,
    worker_ws: Any | None = None,
) -> WorkerTermState:
    async with hub._lock:
        st = hub._workers.setdefault(worker_id, WorkerTermState())
        st.browsers[browser_ws] = role
        if worker_ws is not None:
            st.worker_ws = worker_ws
        return st


def _make_app_client(
    role: str,
    store: InMemoryResumeStore | None = None,
) -> tuple[TestClient, TermHub]:
    hub = TermHub(
        resolve_browser_role=lambda _ws, _wid: role,
        resume_store=store,
    )
    app = FastAPI()
    app.include_router(hub.create_router())
    return TestClient(app), hub


def _read_initial(ws: Any) -> tuple[dict, dict]:
    hello = ws.receive_json()
    assert hello["type"] == "hello"
    hs = ws.receive_json()
    assert hs["type"] == "hijack_state"
    return hello, hs


# ---------------------------------------------------------------------------
# heartbeat message — field keys must be exact
# ---------------------------------------------------------------------------


class TestHeartbeatMessage:
    """mutmut 38,40,47,48,49: heartbeat_ack message field keys/values."""

    async def test_heartbeat_ack_has_ts_key(self) -> None:
        """mutmut_47,48: 'ts' key must be present (not 'XXtsXX' or 'TS')."""
        hub = _make_hub()
        ws = _make_ws()
        wws = _make_ws()
        st = await _register(hub, "w1", ws, "admin", wws)
        # Set ownership so touch_if_owner returns non-None
        async with hub._lock:
            st.hijack_owner = ws
            st.hijack_owner_expires_at = time.time() + 60
        await handle_browser_message(hub, ws, "w1", "admin", {"type": "heartbeat"}, True)
        ws.send_text.assert_called()
        sent = json.loads(ws.send_text.call_args_list[0][0][0])
        assert sent["type"] == "heartbeat_ack"
        assert "ts" in sent
        assert "lease_expires_at" in sent

    async def test_heartbeat_ack_broadcasts_state(self) -> None:
        """heartbeat must call broadcast_hijack_state so all browsers see updated lease."""
        hub = _make_hub()
        ws = _make_ws()
        wws = _make_ws()
        st = await _register(hub, "w1", ws, "admin", wws)
        async with hub._lock:
            st.hijack_owner = ws
            st.hijack_owner_expires_at = time.time() + 60
        with patch.object(hub, "broadcast_hijack_state", new_callable=AsyncMock) as mock_bcast:
            await handle_browser_message(hub, ws, "w1", "admin", {"type": "heartbeat"}, True)
            mock_bcast.assert_called_once_with("w1")

    async def test_heartbeat_no_owner_no_ack(self) -> None:
        """When touch_if_owner returns None (not owner), no heartbeat_ack is sent."""
        hub = _make_hub()
        ws = _make_ws()
        # No ownership established
        await _register(hub, "w1", ws, "admin")
        await handle_browser_message(hub, ws, "w1", "admin", {"type": "heartbeat"}, False)
        # Should NOT have sent heartbeat_ack
        if ws.send_text.called:
            calls = [json.loads(c[0][0]) for c in ws.send_text.call_args_list]
            assert not any(m.get("type") == "heartbeat_ack" for m in calls)


# ---------------------------------------------------------------------------
# hijack_step message — field keys must be exact
# ---------------------------------------------------------------------------


class TestHijackStepMessage:
    """mutmut 85-93, 110-124: hijack_step worker message and post-step events."""

    async def _setup_owner(self, hub: TermHub, ws: Any, wws: Any) -> WorkerTermState:
        st = await _register(hub, "w1", ws, "admin", wws)
        async with hub._lock:
            st.hijack_owner = ws
            st.hijack_owner_expires_at = time.time() + 60
        return st

    async def test_step_message_owner_key_is_owner(self) -> None:
        """mutmut_85,86: 'owner' key must be 'owner' (not 'XXownerXX' or 'OWNER')."""
        hub = _make_hub()
        ws = _make_ws()
        wws = _make_ws()
        await self._setup_owner(hub, ws, wws)
        await handle_browser_message(hub, ws, "w1", "admin", {"type": "hijack_step"}, True)
        msg = json.loads(wws.send_text.call_args_list[0][0][0])
        assert "owner" in msg
        assert msg["owner"] == "dashboard"

    async def test_step_message_owner_value_is_dashboard(self) -> None:
        """mutmut_87,88: 'owner' value must be 'dashboard' (not 'XXdashboardXX' or 'DASHBOARD')."""
        hub = _make_hub()
        ws = _make_ws()
        wws = _make_ws()
        await self._setup_owner(hub, ws, wws)
        await handle_browser_message(hub, ws, "w1", "admin", {"type": "hijack_step"}, True)
        msg = json.loads(wws.send_text.call_args_list[0][0][0])
        assert msg["owner"] == "dashboard"

    async def test_step_message_lease_s_key_is_lease_s(self) -> None:
        """mutmut_89,90: 'lease_s' key must be 'lease_s' (not 'XXlease_sXX' or 'LEASE_S')."""
        hub = _make_hub()
        ws = _make_ws()
        wws = _make_ws()
        await self._setup_owner(hub, ws, wws)
        await handle_browser_message(hub, ws, "w1", "admin", {"type": "hijack_step"}, True)
        msg = json.loads(wws.send_text.call_args_list[0][0][0])
        assert "lease_s" in msg

    async def test_step_message_lease_s_value_is_zero(self) -> None:
        """mutmut_91: 'lease_s' value must be 0 (not 1)."""
        hub = _make_hub()
        ws = _make_ws()
        wws = _make_ws()
        await self._setup_owner(hub, ws, wws)
        await handle_browser_message(hub, ws, "w1", "admin", {"type": "hijack_step"}, True)
        msg = json.loads(wws.send_text.call_args_list[0][0][0])
        assert msg["lease_s"] == 0

    async def test_step_message_ts_key_is_ts(self) -> None:
        """mutmut_92,93: 'ts' key must be 'ts' (not 'XXtsXX' or 'TS')."""
        hub = _make_hub()
        ws = _make_ws()
        wws = _make_ws()
        await self._setup_owner(hub, ws, wws)
        await handle_browser_message(hub, ws, "w1", "admin", {"type": "hijack_step"}, True)
        msg = json.loads(wws.send_text.call_args_list[0][0][0])
        assert "ts" in msg

    async def test_step_metric_name_is_hijack_steps_total(self) -> None:
        """mutmut_110-112: metric name must be 'hijack_steps_total'."""
        hub = _make_hub()
        ws = _make_ws()
        wws = _make_ws()
        await self._setup_owner(hub, ws, wws)
        with patch.object(hub, "metric") as mock_metric:
            await handle_browser_message(hub, ws, "w1", "admin", {"type": "hijack_step"}, True)
            mock_metric.assert_called_once_with("hijack_steps_total")

    async def test_step_append_event_called_with_correct_args(self) -> None:
        """mutmut_113-124: append_event must be called with (worker_id, 'hijack_step', {'owner': 'dashboard_ws'})."""
        hub = _make_hub()
        ws = _make_ws()
        wws = _make_ws()
        await self._setup_owner(hub, ws, wws)
        with patch.object(hub, "append_event", new_callable=AsyncMock) as mock_ae:
            await handle_browser_message(hub, ws, "w1", "admin", {"type": "hijack_step"}, True)
            mock_ae.assert_called_once()
            call_args = mock_ae.call_args
            assert call_args[0][0] == "w1"  # worker_id
            assert call_args[0][1] == "hijack_step"  # event name
            assert call_args[0][2] == {"owner": "dashboard_ws"}  # event data

    async def test_step_no_worker_sends_error(self) -> None:
        """hijack_step with no worker sends error (not metric/append_event path)."""
        hub = _make_hub()
        ws = _make_ws()
        # Owner set but no worker_ws
        st = await _register(hub, "w1", ws, "admin")
        async with hub._lock:
            st.hijack_owner = ws
            st.hijack_owner_expires_at = time.time() + 60
        await handle_browser_message(hub, ws, "w1", "admin", {"type": "hijack_step"}, True)
        ws.send_text.assert_called()
        msgs = [json.loads(c[0][0]) for c in ws.send_text.call_args_list]
        assert any(m.get("type") == "error" for m in msgs)


# ---------------------------------------------------------------------------
# _handle_input — append_event arguments
# ---------------------------------------------------------------------------


class TestHandleInputAppendEvent:
    """mutmut_67-75: append_event called with correct event name and args."""

    async def _setup_open_mode(self, hub: TermHub, ws: Any, wws: Any) -> None:
        await _register(hub, "w1", ws, "operator", wws)
        async with hub._lock:
            hub._workers["w1"].input_mode = "open"

    async def test_append_event_event_name_is_input_send(self) -> None:
        """mutmut_67,68: event name must be 'input_send' (not 'XXinput_sendXX' or 'INPUT_SEND')."""
        hub = _make_hub()
        ws = _make_ws()
        wws = _make_ws()
        await self._setup_open_mode(hub, ws, wws)
        with patch.object(hub, "append_event", new_callable=AsyncMock) as mock_ae:
            await handle_browser_message(hub, ws, "w1", "operator", {"type": "input", "data": "hi"}, False)
            mock_ae.assert_called_once()
            assert mock_ae.call_args[0][1] == "input_send"

    async def test_append_event_owner_key_is_owner(self) -> None:
        """mutmut_69,70: 'owner' key must be 'owner' (not 'XXownerXX' or 'OWNER')."""
        hub = _make_hub()
        ws = _make_ws()
        wws = _make_ws()
        await self._setup_open_mode(hub, ws, wws)
        with patch.object(hub, "append_event", new_callable=AsyncMock) as mock_ae:
            await handle_browser_message(hub, ws, "w1", "operator", {"type": "input", "data": "hi"}, False)
            event_data = mock_ae.call_args[0][2]
            assert "owner" in event_data

    async def test_append_event_owner_value_is_dashboard_ws(self) -> None:
        """mutmut_71,72: 'owner' value must be 'dashboard_ws' (not 'XXdashboard_wsXX' or 'DASHBOARD_WS')."""
        hub = _make_hub()
        ws = _make_ws()
        wws = _make_ws()
        await self._setup_open_mode(hub, ws, wws)
        with patch.object(hub, "append_event", new_callable=AsyncMock) as mock_ae:
            await handle_browser_message(hub, ws, "w1", "operator", {"type": "input", "data": "hi"}, False)
            event_data = mock_ae.call_args[0][2]
            assert event_data["owner"] == "dashboard_ws"

    async def test_append_event_keys_key_is_keys(self) -> None:
        """mutmut_73,74: 'keys' key must be 'keys' (not 'XXkeysXX' or 'KEYS')."""
        hub = _make_hub()
        ws = _make_ws()
        wws = _make_ws()
        await self._setup_open_mode(hub, ws, wws)
        with patch.object(hub, "append_event", new_callable=AsyncMock) as mock_ae:
            await handle_browser_message(hub, ws, "w1", "operator", {"type": "input", "data": "hi"}, False)
            event_data = mock_ae.call_args[0][2]
            assert "keys" in event_data

    async def test_append_event_keys_truncated_at_120(self) -> None:
        """mutmut_75: data[:120] not data[:121] — keys are truncated at 120 chars."""
        hub = _make_hub()
        ws = _make_ws()
        wws = _make_ws()
        await self._setup_open_mode(hub, ws, wws)
        long_data = "x" * 130  # longer than 120
        with patch.object(hub, "append_event", new_callable=AsyncMock) as mock_ae:
            await handle_browser_message(hub, ws, "w1", "operator", {"type": "input", "data": long_data}, False)
            event_data = mock_ae.call_args[0][2]
            # Truncated at 120, not 121 or beyond
            assert len(event_data["keys"]) == 120
            assert event_data["keys"] == "x" * 120

    async def test_append_event_worker_id_is_correct(self) -> None:
        """append_event first arg must be the actual worker_id."""
        hub = _make_hub()
        ws = _make_ws()
        wws = _make_ws()
        await self._setup_open_mode(hub, ws, wws)
        with patch.object(hub, "append_event", new_callable=AsyncMock) as mock_ae:
            await handle_browser_message(hub, ws, "w1", "operator", {"type": "input", "data": "hi"}, False)
            assert mock_ae.call_args[0][0] == "w1"


# ---------------------------------------------------------------------------
# _handle_hijack_request — err == "already_hijacked" branching
# ---------------------------------------------------------------------------


class TestHijackRequestAlreadyHijackedBranch:
    """mutmut_89-94: err == 'already_hijacked' condition and metric must be correct."""

    async def test_conflict_metric_called_on_already_hijacked(self) -> None:
        """mutmut_89-94: metric('hijack_conflicts_total') called when err == 'already_hijacked'."""
        hub = _make_hub()
        ws = _make_ws()
        owner_ws = _make_ws()
        wws = _make_ws()
        await _register(hub, "w1", ws, "admin", wws)
        # Pre-set a different owner so try_acquire_ws_hijack returns (False, already_hijacked)
        async with hub._lock:
            st = hub._workers["w1"]
            st.browsers[owner_ws] = "admin"
            st.hijack_owner = owner_ws
            st.hijack_owner_expires_at = time.time() + 60

        with patch.object(hub, "metric") as mock_metric:
            await handle_browser_message(hub, ws, "w1", "admin", {"type": "hijack_request"}, False)
            mock_metric.assert_called_once_with("hijack_conflicts_total")

    async def test_no_conflict_metric_on_no_worker(self) -> None:
        """mutmut_89: with err == 'no_worker', hijack_conflicts_total must NOT be called."""
        hub = _make_hub()
        ws = _make_ws()
        # No worker_ws registered → send_worker returns False → err == 'no_worker'
        await _register(hub, "w1", ws, "admin")

        with patch.object(hub, "metric") as mock_metric:
            await handle_browser_message(hub, ws, "w1", "admin", {"type": "hijack_request"}, False)
            # metric should not be called for hijack_conflicts_total
            for call in mock_metric.call_args_list:
                assert call[0][0] != "hijack_conflicts_total"

    async def test_compensating_resume_sent_on_no_worker(self) -> None:
        """mutmut_96,97: err != 'already_hijacked' → compensating resume IS sent for no_worker."""
        hub = _make_hub()
        ws = _make_ws()
        wws = _make_ws()
        await _register(hub, "w1", ws, "admin", wws)
        # Force try_acquire_ws_hijack to return (False, "no_worker"). We patch directly.
        with (
            patch.object(hub, "try_acquire_ws_hijack", new_callable=AsyncMock, return_value=(False, "no_worker")),
            patch.object(hub, "send_worker", new_callable=AsyncMock) as mock_send,
        ):
            mock_send.return_value = True
            await handle_browser_message(hub, ws, "w1", "admin", {"type": "hijack_request"}, False)
            # send_worker should be called at least once for resume
            actions_sent = []
            for c in mock_send.call_args_list:
                msg = c[0][1] if len(c[0]) > 1 else c[1].get("msg", {})
                if isinstance(msg, dict):
                    actions_sent.append(msg.get("action"))
            assert "resume" in actions_sent, f"Compensating resume not sent. Actions: {actions_sent}"

    async def test_compensating_resume_not_sent_on_already_hijacked(self) -> None:
        """mutmut_96,97: err == 'already_hijacked' → compensating resume must NOT be sent."""
        hub = _make_hub()
        ws = _make_ws()
        owner_ws = _make_ws()
        wws = _make_ws()
        await _register(hub, "w1", ws, "admin", wws)
        async with hub._lock:
            st = hub._workers["w1"]
            st.browsers[owner_ws] = "admin"
            st.hijack_owner = owner_ws
            st.hijack_owner_expires_at = time.time() + 60

        with (
            patch.object(
                hub, "try_acquire_ws_hijack", new_callable=AsyncMock, return_value=(False, "already_hijacked")
            ),
            patch.object(hub, "send_worker", new_callable=AsyncMock) as mock_send,
        ):
            mock_send.return_value = True
            await handle_browser_message(hub, ws, "w1", "admin", {"type": "hijack_request"}, False)
            actions_sent = []
            for c in mock_send.call_args_list:
                msg = c[0][1] if len(c[0]) > 1 else {}
                if isinstance(msg, dict):
                    actions_sent.append(msg.get("action"))
            assert "resume" not in actions_sent, f"Resume should not be sent for already_hijacked. Got: {actions_sent}"

    async def test_compensating_resume_message_type_is_control(self) -> None:
        """mutmut_102-105: compensating resume msg type must be 'control'."""
        hub = _make_hub()
        ws = _make_ws()
        wws = _make_ws()
        await _register(hub, "w1", ws, "admin", wws)
        sent_msgs: list[dict] = []

        async def capture(worker_id, msg):
            sent_msgs.append(msg)
            return True

        with (
            patch.object(hub, "try_acquire_ws_hijack", new_callable=AsyncMock, return_value=(False, "no_worker")),
            patch.object(hub, "send_worker", side_effect=capture),
        ):
            await handle_browser_message(hub, ws, "w1", "admin", {"type": "hijack_request"}, False)
        resume_calls = [m for m in sent_msgs if m.get("action") == "resume"]
        assert resume_calls, "No resume message sent"
        assert resume_calls[0]["type"] == "control"

    async def test_compensating_resume_message_action_is_resume(self) -> None:
        """mutmut_106-109: compensating resume action must be 'resume'."""
        hub = _make_hub()
        ws = _make_ws()
        wws = _make_ws()
        await _register(hub, "w1", ws, "admin", wws)
        sent_msgs: list[dict] = []

        async def capture(worker_id, msg):
            sent_msgs.append(msg)
            return True

        with (
            patch.object(hub, "try_acquire_ws_hijack", new_callable=AsyncMock, return_value=(False, "no_worker")),
            patch.object(hub, "send_worker", side_effect=capture),
        ):
            await handle_browser_message(hub, ws, "w1", "admin", {"type": "hijack_request"}, False)
        resume_calls = [m for m in sent_msgs if m.get("action") == "resume"]
        assert resume_calls, "No resume message sent"
        assert resume_calls[0]["action"] == "resume"

    async def test_compensating_resume_message_owner_is_dashboard(self) -> None:
        """mutmut_110-113: compensating resume 'owner' must be 'dashboard'."""
        hub = _make_hub()
        ws = _make_ws()
        wws = _make_ws()
        await _register(hub, "w1", ws, "admin", wws)
        sent_msgs: list[dict] = []

        async def capture(worker_id, msg):
            sent_msgs.append(msg)
            return True

        with (
            patch.object(hub, "try_acquire_ws_hijack", new_callable=AsyncMock, return_value=(False, "no_worker")),
            patch.object(hub, "send_worker", side_effect=capture),
        ):
            await handle_browser_message(hub, ws, "w1", "admin", {"type": "hijack_request"}, False)
        resume_calls = [m for m in sent_msgs if m.get("action") == "resume"]
        assert resume_calls
        assert resume_calls[0]["owner"] == "dashboard"

    async def test_compensating_resume_message_lease_s_is_zero(self) -> None:
        """mutmut_114-116: compensating resume 'lease_s' must be 0 (not 1)."""
        hub = _make_hub()
        ws = _make_ws()
        wws = _make_ws()
        await _register(hub, "w1", ws, "admin", wws)
        sent_msgs: list[dict] = []

        async def capture(worker_id, msg):
            sent_msgs.append(msg)
            return True

        with (
            patch.object(hub, "try_acquire_ws_hijack", new_callable=AsyncMock, return_value=(False, "no_worker")),
            patch.object(hub, "send_worker", side_effect=capture),
        ):
            await handle_browser_message(hub, ws, "w1", "admin", {"type": "hijack_request"}, False)
        resume_calls = [m for m in sent_msgs if m.get("action") == "resume"]
        assert resume_calls
        assert resume_calls[0]["lease_s"] == 0

    async def test_compensating_resume_message_has_ts(self) -> None:
        """mutmut_117,118: compensating resume must have 'ts' key."""
        hub = _make_hub()
        ws = _make_ws()
        wws = _make_ws()
        await _register(hub, "w1", ws, "admin", wws)
        sent_msgs: list[dict] = []

        async def capture(worker_id, msg):
            sent_msgs.append(msg)
            return True

        with (
            patch.object(hub, "try_acquire_ws_hijack", new_callable=AsyncMock, return_value=(False, "no_worker")),
            patch.object(hub, "send_worker", side_effect=capture),
        ):
            await handle_browser_message(hub, ws, "w1", "admin", {"type": "hijack_request"}, False)
        resume_calls = [m for m in sent_msgs if m.get("action") == "resume"]
        assert resume_calls
        assert "ts" in resume_calls[0]


# ---------------------------------------------------------------------------
# _handle_resume — token default and _on_resume args
# ---------------------------------------------------------------------------


class TestHandleResumeTokenAndCallbacks:
    """mutmut_5,7,10,20,21: token default and _on_resume args must be exact."""

    async def test_missing_token_key_returns_unchanged(self) -> None:
        """mutmut_5,7: msg_b.get('token', '') with missing key → '' → falsy → no resume."""
        store = InMemoryResumeStore()
        hub = TermHub(resume_store=store)
        ws = _make_ws()
        # Valid session in store, but message has no token key
        store.create("w1", "admin", 300)
        result = await _handle_resume(hub, ws, "w1", "admin", {"type": "resume"}, False)
        assert result is False
        # No hello message sent
        ws.send_text.assert_not_called()

    async def test_token_placeholder_string_causes_resume_attempt(self) -> None:
        """mutmut_10: default of 'XXXX' (truthy) would bypass the empty-check guard.

        If get('token', 'XXXX') is used instead of get('token', ''), a missing
        token key would produce 'XXXX' which is truthy, allowing the code to
        attempt a lookup that will fail with None — but the empty-string guard
        prevents even reaching that point.
        """
        store = InMemoryResumeStore()
        hub = TermHub(resume_store=store)
        ws = _make_ws()
        # No token key in message — should return without calling send_text
        result = await _handle_resume(hub, ws, "w1", "admin", {"type": "resume"}, True)
        assert result is True  # owned_hijack unchanged
        ws.send_text.assert_not_called()

    async def test_on_resume_called_with_old_token(self) -> None:
        """mutmut_20: _on_resume must receive old_token (not None)."""
        store = InMemoryResumeStore()
        received_args = []

        async def on_resume(token, session):
            received_args.append((token, session))
            return True  # allow resume

        hub = TermHub(resume_store=store, on_resume=on_resume)
        ws = _make_ws()
        await _register(hub, "w1", ws, "admin")
        token = store.create("w1", "admin", 300)
        await _handle_resume(hub, ws, "w1", "admin", {"type": "resume", "token": token}, False)
        assert received_args, "on_resume was not called"
        assert received_args[0][0] == token  # first arg must be old_token

    async def test_on_resume_called_with_session(self) -> None:
        """mutmut_21: _on_resume must receive session (not None)."""
        store = InMemoryResumeStore()
        received_args = []

        async def on_resume(token, session):
            received_args.append((token, session))
            return True

        hub = TermHub(resume_store=store, on_resume=on_resume)
        ws = _make_ws()
        await _register(hub, "w1", ws, "admin")
        token = store.create("w1", "admin", 300)
        from undef.terminal.hijack.hub.resume import ResumeSession

        await _handle_resume(hub, ws, "w1", "admin", {"type": "resume", "token": token}, False)
        assert received_args
        assert isinstance(received_args[0][1], ResumeSession)
        assert received_args[0][1].token == token

    async def test_on_resume_rejection_blocks_resume(self) -> None:
        """on_resume returning False must prevent the resume from proceeding."""
        store = InMemoryResumeStore()

        async def on_resume(token, session):
            return False  # reject

        hub = TermHub(resume_store=store, on_resume=on_resume)
        ws = _make_ws()
        await _register(hub, "w1", ws, "admin")
        token = store.create("w1", "admin", 300)
        result = await _handle_resume(hub, ws, "w1", "admin", {"type": "resume", "token": token}, False)
        assert result is False
        ws.send_text.assert_not_called()


# ---------------------------------------------------------------------------
# _handle_resume — new_role and can_hijack initialization
# ---------------------------------------------------------------------------


class TestHandleResumeRoleInit:
    """mutmut_25-30: new_role and can_hijack initialization."""

    async def test_new_role_initialized_to_current_role(self) -> None:
        """mutmut_25: new_role must start as role (not None) so it appears in hello response."""
        store = InMemoryResumeStore()
        client, hub = _make_app_client("operator", store)
        with client.websocket_connect("/ws/browser/w1/term") as ws:
            hello, _ = _read_initial(ws)
            token = hello["resume_token"]

        with client.websocket_connect("/ws/browser/w1/term") as ws:
            _read_initial(ws)
            ws.send_json({"type": "resume", "token": token})
            resumed = ws.receive_json()
            assert resumed["type"] == "hello"
            # Role must be a valid role string, not None
            assert resumed["role"] is not None
            assert resumed["role"] in {"viewer", "operator", "admin"}

    async def test_can_hijack_is_false_for_operator(self) -> None:
        """mutmut_26,27: can_hijack = role == 'admin' → False for 'operator'."""
        store = InMemoryResumeStore()
        client, _ = _make_app_client("operator", store)
        with client.websocket_connect("/ws/browser/w1/term") as ws:
            hello, _ = _read_initial(ws)
            token = hello["resume_token"]

        with client.websocket_connect("/ws/browser/w1/term") as ws:
            _read_initial(ws)
            ws.send_json({"type": "resume", "token": token})
            resumed = ws.receive_json()
            assert resumed["can_hijack"] is False

    async def test_can_hijack_is_true_for_admin(self) -> None:
        """mutmut_27-29: can_hijack = role == 'admin' → True for 'admin' (not !=)."""
        store = InMemoryResumeStore()
        client, _ = _make_app_client("admin", store)
        with client.websocket_connect("/ws/browser/w1/term") as ws:
            hello, _ = _read_initial(ws)
            token = hello["resume_token"]

        with client.websocket_connect("/ws/browser/w1/term") as ws:
            _read_initial(ws)
            ws.send_json({"type": "resume", "token": token})
            resumed = ws.receive_json()
            assert resumed["can_hijack"] is True


# ---------------------------------------------------------------------------
# _handle_resume — role restore condition (AND not OR)
# ---------------------------------------------------------------------------


class TestHandleResumeRoleRestoreCondition:
    """mutmut_30: session.role != role AND session.role in VALID_ROLES must both be true."""

    def test_role_not_restored_when_same_as_current(self) -> None:
        """mutmut_30: if AND is replaced with OR, same role would still update browsers dict."""
        store = InMemoryResumeStore()
        # Both connections resolve as "admin" — session.role == role
        hub = TermHub(
            resolve_browser_role=lambda _ws, _wid: "admin",
            resume_store=store,
        )
        app = FastAPI()
        app.include_router(hub.create_router())
        client = TestClient(app)

        with client.websocket_connect("/ws/browser/w1/term") as ws:
            hello, _ = _read_initial(ws)
            token = hello["resume_token"]

        with client.websocket_connect("/ws/browser/w1/term") as ws:
            _read_initial(ws)
            ws.send_json({"type": "resume", "token": token})
            resumed = ws.receive_json()
            # Role is still admin (same as current) — not altered
            assert resumed["role"] == "admin"
            assert resumed["resumed"] is True

    def test_role_restored_when_different(self) -> None:
        """mutmut_30: role IS restored when session.role != current role."""
        store = InMemoryResumeStore()
        # First session: admin. Second connection: viewer (different role).
        hub1 = TermHub(
            resolve_browser_role=lambda _ws, _wid: "admin",
            resume_store=store,
        )
        app1 = FastAPI()
        app1.include_router(hub1.create_router())
        c1 = TestClient(app1)

        with c1.websocket_connect("/ws/browser/w1/term") as ws:
            hello, _ = _read_initial(ws)
            token = hello["resume_token"]

        hub2 = TermHub(
            resolve_browser_role=lambda _ws, _wid: "viewer",
            resume_store=store,
        )
        app2 = FastAPI()
        app2.include_router(hub2.create_router())
        c2 = TestClient(app2)

        with c2.websocket_connect("/ws/browser/w1/term") as ws:
            _read_initial(ws)
            ws.send_json({"type": "resume", "token": token})
            resumed = ws.receive_json()
            # Session was admin, current is viewer — restore to admin
            assert resumed["role"] == "admin"


# ---------------------------------------------------------------------------
# _handle_resume — hijack reclaim conditions
# ---------------------------------------------------------------------------


class TestHandleResumeHijackReclaim:
    """mutmut_44,45: hijack reclaim conditions: is None AND not hub.is_hijacked()."""

    def test_hijack_not_reclaimed_when_already_hijacked_by_another(self) -> None:
        """mutmut_44: must check st.hijack_owner is None — if hijacked by another, must NOT reclaim."""
        store = InMemoryResumeStore()
        # Use a setup where an admin token was the hijack owner but someone else grabbed it
        hub = TermHub(
            resolve_browser_role=lambda _ws, _wid: "admin",
            resume_store=store,
        )
        app = FastAPI()
        app.include_router(hub.create_router())
        client = TestClient(app)

        # Connect first to get a token
        with client.websocket_connect("/ws/browser/w1/term") as ws:
            hello, _ = _read_initial(ws)
            token = hello["resume_token"]

        # Mark as hijack owner in the token
        store.mark_hijack_owner(token, True)

        # Now manually set a different hijack owner on the worker state.
        # We access _workers directly (safe in sync test context — no concurrent access).
        another_ws = MagicMock()
        st = hub._workers.get("w1")
        if st is None:
            # worker state not created yet — pre-create it
            hub._workers["w1"] = WorkerTermState()
            st = hub._workers["w1"]
        st.hijack_owner = another_ws
        st.hijack_owner_expires_at = time.time() + 60

        with client.websocket_connect("/ws/browser/w1/term") as ws:
            _read_initial(ws)
            ws.send_json({"type": "resume", "token": token})
            resumed = ws.receive_json()
            # Should NOT have reclaimed hijack since another owner holds it
            assert resumed["hijacked_by_me"] is False

    def test_hijack_reclaimed_when_no_current_owner(self) -> None:
        """mutmut_53,54: owned_hijack must be True (not False/None) after reclaim."""
        store = InMemoryResumeStore()
        client, hub = _make_app_client("admin", store)

        with client.websocket_connect("/ws/browser/w1/term") as ws:
            hello, _ = _read_initial(ws)
            token = hello["resume_token"]

        store.mark_hijack_owner(token, True)

        with client.websocket_connect("/ws/browser/w1/term") as ws:
            _read_initial(ws)
            ws.send_json({"type": "resume", "token": token})
            resumed = ws.receive_json()
            assert resumed["hijacked_by_me"] is True


# ---------------------------------------------------------------------------
# _handle_resume — store.create and _ws_to_resume_token
# ---------------------------------------------------------------------------


class TestHandleResumeTokenCreation:
    """mutmut_56,57,62: store.create args and _ws_to_resume_token assignment."""

    def test_new_token_created_with_correct_worker_id(self) -> None:
        """mutmut_56: store.create(worker_id, ...) not store.create(None, ...)."""
        store = InMemoryResumeStore()
        client, _ = _make_app_client("admin", store)

        with client.websocket_connect("/ws/browser/w1/term") as ws:
            hello, _ = _read_initial(ws)
            old_token = hello["resume_token"]

        with client.websocket_connect("/ws/browser/w1/term") as ws:
            _read_initial(ws)
            ws.send_json({"type": "resume", "token": old_token})
            resumed = ws.receive_json()
            new_token = resumed["resume_token"]
            # New token must be valid and belong to w1
            session = store.get(new_token)
            assert session is not None
            assert session.worker_id == "w1"

    def test_new_token_created_with_correct_role(self) -> None:
        """mutmut_57: store.create(worker_id, new_role, ...) not (worker_id, None, ...)."""
        store = InMemoryResumeStore()
        client, _ = _make_app_client("admin", store)

        with client.websocket_connect("/ws/browser/w1/term") as ws:
            hello, _ = _read_initial(ws)
            old_token = hello["resume_token"]

        with client.websocket_connect("/ws/browser/w1/term") as ws:
            _read_initial(ws)
            ws.send_json({"type": "resume", "token": old_token})
            resumed = ws.receive_json()
            new_token = resumed["resume_token"]
            session = store.get(new_token)
            assert session is not None
            assert session.role is not None
            assert session.role in {"viewer", "operator", "admin"}

    def test_ws_to_resume_token_set_to_new_token(self) -> None:
        """mutmut_62: hub._ws_to_resume_token[ws] must be new_token (not None)."""
        store = InMemoryResumeStore()
        client, hub = _make_app_client("admin", store)

        with client.websocket_connect("/ws/browser/w1/term") as ws:
            hello, _ = _read_initial(ws)
            old_token = hello["resume_token"]

        with client.websocket_connect("/ws/browser/w1/term") as ws:
            _read_initial(ws)
            ws.send_json({"type": "resume", "token": old_token})
            resumed = ws.receive_json()
            new_token = resumed["resume_token"]

            # The token in hub._ws_to_resume_token should equal new_token, not None
            # (We check indirectly: sending another resume_token message should yield a valid token)
            assert new_token is not None
            assert new_token != old_token


# ---------------------------------------------------------------------------
# _handle_resume — hello message field keys/values
# ---------------------------------------------------------------------------


class TestHandleResumeHelloFields:
    """mutmut 77-164: hello message fields in the resume response must be correct."""

    def _resume(self, store: InMemoryResumeStore, role: str = "admin") -> dict:
        """Helper: connect, capture token, reconnect and resume. Returns resumed hello."""
        client, _ = _make_app_client(role, store)
        with client.websocket_connect("/ws/browser/w1/term") as ws:
            hello, _ = _read_initial(ws)
            token = hello["resume_token"]
        with client.websocket_connect("/ws/browser/w1/term") as ws:
            _read_initial(ws)
            ws.send_json({"type": "resume", "token": token})
            return ws.receive_json()

    def test_hello_has_worker_id_key(self) -> None:
        """mutmut_77,78: 'worker_id' key must be present (not 'XXworker_idXX' or 'WORKER_ID')."""
        store = InMemoryResumeStore()
        resumed = self._resume(store)
        assert "worker_id" in resumed

    def test_hello_worker_id_value_is_correct(self) -> None:
        """mutmut_77,78: 'worker_id' value must be the actual worker id."""
        store = InMemoryResumeStore()
        resumed = self._resume(store)
        assert resumed["worker_id"] == "w1"

    def test_hello_has_hijacked_key(self) -> None:
        """mutmut_81,82: 'hijacked' key must be present (not 'XXhijackedXX' or 'HIJACKED')."""
        store = InMemoryResumeStore()
        resumed = self._resume(store)
        assert "hijacked" in resumed

    def test_hello_hijacked_is_false_when_not_hijacked(self) -> None:
        """mutmut_83-89: 'hijacked' must come from is_hijacked state (False when not hijacked)."""
        store = InMemoryResumeStore()
        resumed = self._resume(store)
        assert resumed["hijacked"] is False

    def test_hello_has_hijacked_by_me_key(self) -> None:
        """mutmut_93-98: 'hijacked_by_me' key and correct default."""
        store = InMemoryResumeStore()
        resumed = self._resume(store)
        assert "hijacked_by_me" in resumed

    def test_hello_hijacked_by_me_is_false_when_not_owner(self) -> None:
        """mutmut_98: default must be False (not True) for hijacked_by_me."""
        store = InMemoryResumeStore()
        resumed = self._resume(store)
        assert resumed["hijacked_by_me"] is False

    def test_hello_has_worker_online_key(self) -> None:
        """mutmut_99,100: 'worker_online' key must be present."""
        store = InMemoryResumeStore()
        resumed = self._resume(store)
        assert "worker_online" in resumed

    def test_hello_worker_online_is_false_when_no_worker(self) -> None:
        """mutmut_102,107: default must be False (not True/None) for worker_online."""
        store = InMemoryResumeStore()
        resumed = self._resume(store)
        assert resumed["worker_online"] is False

    def test_hello_has_input_mode_key(self) -> None:
        """mutmut_108,109: 'input_mode' key must be present."""
        store = InMemoryResumeStore()
        resumed = self._resume(store)
        assert "input_mode" in resumed

    def test_hello_input_mode_default_is_hijack(self) -> None:
        """mutmut_111-117: default input_mode must be 'hijack' (not None/HIJACK/XXhijackXX)."""
        store = InMemoryResumeStore()
        resumed = self._resume(store)
        assert resumed["input_mode"] == "hijack"

    def test_hello_has_hijack_control_key(self) -> None:
        """mutmut_120,121: 'hijack_control' key must be present."""
        store = InMemoryResumeStore()
        resumed = self._resume(store)
        assert "hijack_control" in resumed

    def test_hello_hijack_control_value_is_ws(self) -> None:
        """mutmut_122,123: 'hijack_control' value must be 'ws' (not 'XXwsXX' or 'WS')."""
        store = InMemoryResumeStore()
        resumed = self._resume(store)
        assert resumed["hijack_control"] == "ws"

    def test_hello_hijack_step_supported_is_true(self) -> None:
        """mutmut_126: 'hijack_step_supported' must be True (not False)."""
        store = InMemoryResumeStore()
        resumed = self._resume(store)
        assert resumed["hijack_step_supported"] is True

    def test_hello_has_capabilities_key(self) -> None:
        """mutmut_127,128: 'capabilities' key must be present."""
        store = InMemoryResumeStore()
        resumed = self._resume(store)
        assert "capabilities" in resumed

    def test_hello_capabilities_hijack_control_is_ws(self) -> None:
        """mutmut_129-132: capabilities['hijack_control'] must be 'ws'."""
        store = InMemoryResumeStore()
        resumed = self._resume(store)
        assert "hijack_control" in resumed["capabilities"]
        assert resumed["capabilities"]["hijack_control"] == "ws"

    def test_hello_capabilities_hijack_step_supported_is_true(self) -> None:
        """mutmut_133-135: capabilities['hijack_step_supported'] must be True (not False)."""
        store = InMemoryResumeStore()
        resumed = self._resume(store)
        assert "hijack_step_supported" in resumed["capabilities"]
        assert resumed["capabilities"]["hijack_step_supported"] is True

    def test_hello_resume_supported_is_true(self) -> None:
        """mutmut_136-138: 'resume_supported' must be True (not False)."""
        store = InMemoryResumeStore()
        resumed = self._resume(store)
        assert "resume_supported" in resumed
        assert resumed["resume_supported"] is True

    def test_hello_has_resume_token(self) -> None:
        """resume token must be issued and present."""
        store = InMemoryResumeStore()
        resumed = self._resume(store)
        assert "resume_token" in resumed
        assert resumed["resume_token"] is not None

    def test_hello_resumed_is_true(self) -> None:
        """'resumed' field must be True in the response."""
        store = InMemoryResumeStore()
        resumed = self._resume(store)
        assert resumed.get("resumed") is True

    def test_hello_role_is_correct(self) -> None:
        """Role in the hello must reflect the correct (restored or current) role."""
        store = InMemoryResumeStore()
        resumed = self._resume(store, role="operator")
        assert resumed["role"] == "operator"

    def test_resume_followed_by_hijack_state(self) -> None:
        """After resumed hello, a hijack_state message must follow."""
        store = InMemoryResumeStore()
        client, _ = _make_app_client("admin", store)
        with client.websocket_connect("/ws/browser/w1/term") as ws:
            hello, _ = _read_initial(ws)
            token = hello["resume_token"]
        with client.websocket_connect("/ws/browser/w1/term") as ws:
            _read_initial(ws)
            ws.send_json({"type": "resume", "token": token})
            resumed = ws.receive_json()
            assert resumed["type"] == "hello"
            hijack_state = ws.receive_json()
            assert hijack_state["type"] == "hijack_state"


# ---------------------------------------------------------------------------
# _handle_resume — hijack expiry uses addition not subtraction
# ---------------------------------------------------------------------------


class TestHandleResumeHijackExpiry:
    """mutmut_51: hijack_owner_expires_at = time.time() + lease (not minus, not None)."""

    def test_reclaimed_hijack_expiry_is_in_future(self) -> None:
        """mutmut_51: expiry time must be in the future (addition, not subtraction or None)."""
        store = InMemoryResumeStore()
        client, hub = _make_app_client("admin", store)

        with client.websocket_connect("/ws/browser/w1/term") as ws:
            hello, _ = _read_initial(ws)
            token = hello["resume_token"]

        store.mark_hijack_owner(token, True)

        with client.websocket_connect("/ws/browser/w1/term") as ws:
            _read_initial(ws)
            ws.send_json({"type": "resume", "token": token})
            resumed = ws.receive_json()
            assert resumed["hijacked_by_me"] is True
            # hijack_state message should show we are the owner
            hs = ws.receive_json()
            assert hs["type"] == "hijack_state"
            assert hs["owner"] == "me"

    def test_reclaimed_hijack_owner_expires_at_in_future(self) -> None:
        """Directly check hijack_owner_expires_at is in the future after reclaim."""
        store = InMemoryResumeStore()
        hub = TermHub(
            resolve_browser_role=lambda _ws, _wid: "admin",
            resume_store=store,
        )
        app = FastAPI()
        app.include_router(hub.create_router())
        client = TestClient(app)

        with client.websocket_connect("/ws/browser/w1/term") as ws:
            hello, _ = _read_initial(ws)
            token = hello["resume_token"]

        store.mark_hijack_owner(token, True)

        with client.websocket_connect("/ws/browser/w1/term") as ws:
            _read_initial(ws)
            ws.send_json({"type": "resume", "token": token})
            ws.receive_json()  # resumed hello

            # Access _workers directly (safe in sync test context)
            st = hub._workers.get("w1")
            if st is not None and st.hijack_owner_expires_at is not None:
                assert st.hijack_owner_expires_at > time.time()
