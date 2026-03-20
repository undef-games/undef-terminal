#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Mutation-killing tests for manager — command history, queue, and cancel."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from undef.terminal.manager.config import ManagerConfig
from undef.terminal.manager.core import AgentManager
from undef.terminal.manager.models import AgentStatusBase
from undef.terminal.manager.routes.agent_ops import (
    _append_command_history,
    _build_action_response,
    _cancel_pending_manager_command,
    _command_history_rows,
    _queue_manager_command,
    _update_command_history,
)

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def config(tmp_path):
    return ManagerConfig(
        state_file=str(tmp_path / "state.json"),
        timeseries_dir=str(tmp_path / "metrics"),
        log_dir=str(tmp_path / "logs"),
    )


@pytest.fixture
def manager(config):
    mgr = AgentManager(config)
    pm = MagicMock()
    pm.cancel_spawn = AsyncMock(return_value=False)
    pm.start_spawn_swarm = AsyncMock()
    pm.spawn_agent = AsyncMock(return_value="agent_000")
    pm.spawn_swarm = AsyncMock(return_value=["agent_000"])
    pm.kill_agent = AsyncMock()
    pm.monitor_processes = AsyncMock()
    mgr.agent_process_manager = pm
    return mgr


@pytest.fixture
def agent() -> AgentStatusBase:
    return AgentStatusBase(agent_id="agent_001", state="running")


class TestCommandHistoryRowsExtra:
    def test_getattr_with_none_default_creates_list(self, agent):
        """mutmut_6: getattr with missing default would raise error; with None it returns None → []."""
        import types

        obj = types.SimpleNamespace()  # no manager_command_history attr
        rows = _command_history_rows(obj)  # type: ignore[arg-type]
        assert rows == []


# ===========================================================================
# routes/agent_ops.py — _append_command_history (additional)
# ===========================================================================


class TestAppendCommandHistoryExtra:
    def test_exactly_25_does_not_trim(self, agent):
        """mutmut_5: > 25 means trim happens at 26, not 25. At exactly 25 no trim."""
        agent.manager_command_history = [{"seq": i} for i in range(24)]
        _append_command_history(agent, {"seq": 25})
        assert len(agent.manager_command_history) == 25

    def test_26_triggers_trim(self, agent):
        """mutmut_5: >= 25 would trim at exactly 25. Original > 25 trims at 26."""
        agent.manager_command_history = [{"seq": i} for i in range(25)]
        _append_command_history(agent, {"seq": 999})
        assert len(agent.manager_command_history) == 25
        assert agent.manager_command_history[-1]["seq"] == 999


# ===========================================================================
# routes/agent_ops.py — _update_command_history (additional)
# ===========================================================================


class TestUpdateCommandHistoryExtra:
    def test_seq_zero_returns_early_not_executed(self, agent):
        """mutmut_1: seq < 0 would allow seq=0 to update; seq <= 0 must skip it."""
        agent.manager_command_history = [{"seq": 0, "status": "original"}]
        _update_command_history(agent, 0, status="should_not_change")
        assert agent.manager_command_history[0]["status"] == "original"

    def test_seq_one_must_update(self, agent):
        """mutmut_2: seq <= 1 would skip seq=1; must update seq=1."""
        agent.manager_command_history = [{"seq": 1, "status": "pending"}]
        _update_command_history(agent, 1, status="updated")
        assert agent.manager_command_history[0]["status"] == "updated"

    def test_fallback_zero_not_one_for_missing_seq(self, agent):
        """mutmut_10: 'or 0' fallback — row without seq key treated as seq=0, not seq=1."""
        agent.manager_command_history = [{"status": "original"}]  # no 'seq' key
        # Searching for seq=1 should NOT find the entry with no seq (treated as 0)
        _update_command_history(agent, 1, status="changed")
        assert agent.manager_command_history[0]["status"] == "original"

    def test_continue_not_break_on_no_match(self, agent):
        """mutmut_12: break would stop at first non-match, missing later entries."""
        agent.manager_command_history = [
            {"seq": 1, "status": "a"},
            {"seq": 3, "status": "b"},
            {"seq": 5, "status": "c"},
        ]
        # reversed = [5, 3, 1]; looking for seq=1 — break at 5≠1 would miss it
        _update_command_history(agent, 1, status="found")
        assert agent.manager_command_history[0]["status"] == "found"


# ===========================================================================
# routes/agent_ops.py — _queue_manager_command (detailed)
# ===========================================================================


class TestQueueManagerCommandExtra:
    def test_seq_increments_from_zero(self, agent):
        """mutmut_12: default seq=0 (not 1). First command gets seq=1."""
        result = _queue_manager_command(agent, "set_goal", {"goal": "test"})
        assert result["seq"] == 1

    def test_replace_guard_requires_positive_seq_and_type(self, agent):
        """mutmut_14/15/16: replaced_seq > 0 AND type present to trigger replace."""
        agent.pending_command_seq = 0
        agent.pending_command_type = "set_goal"
        result = _queue_manager_command(agent, "set_goal", {"goal": "y"})
        # seq=0 → no replace update, replaces=None
        assert result["replaces"] is None
        rows = _command_history_rows(agent)
        # No "replaced" status entry
        assert all(r.get("status") != "replaced" for r in rows)

    def test_replace_marked_as_replaced_in_history(self, agent):
        """mutmut_34/35: status='replaced' (not None or 'REPLACED')."""
        _queue_manager_command(agent, "set_goal", {"goal": "x"})
        _queue_manager_command(agent, "set_goal", {"goal": "y"})
        rows = _command_history_rows(agent)
        first = next(r for r in rows if r["seq"] == 1)
        assert first["status"] == "replaced"

    def test_replaced_by_is_next_seq(self, agent):
        """mutmut_36/37: replaced_by = seq+1 (not seq-1 or seq+2)."""
        _queue_manager_command(agent, "set_goal", {"goal": "x"})
        _queue_manager_command(agent, "set_goal", {"goal": "y"})
        rows = _command_history_rows(agent)
        first = next(r for r in rows if r["seq"] == 1)
        assert first["replaced_by"] == 2

    def test_pending_payload_stored_as_dict(self, agent):
        """mutmut_42: payload stored as dict, not None."""
        _queue_manager_command(agent, "set_goal", {"goal": "explore"})
        assert agent.pending_command_payload == {"goal": "explore"}
        assert agent.pending_command_payload is not None

    def test_queued_result_has_type_key(self, agent):
        """mutmut_47/48: returned dict has 'type' key (not 'XXtypeXX' or 'TYPE')."""
        result = _queue_manager_command(agent, "set_goal", {"goal": "test"})
        assert "type" in result
        assert result["type"] == "set_goal"

    def test_replaces_none_for_first_command(self, agent):
        """mutmut_54/55: replaces=None when replaced_seq <= 0."""
        result = _queue_manager_command(agent, "set_goal", {"goal": "x"})
        assert result["replaces"] is None

    def test_replaces_set_for_second_command(self, agent):
        """mutmut_54/55: replaces=1 for second command (replaced_seq=1 > 0)."""
        _queue_manager_command(agent, "set_goal", {"goal": "x"})
        result = _queue_manager_command(agent, "set_goal", {"goal": "y"})
        assert result["replaces"] == 1

    def test_history_entry_has_seq_key(self, agent):
        """mutmut_60/61: history entry has 'seq' key (not 'XXseqXX' or 'SEQ')."""
        _queue_manager_command(agent, "set_goal", {"goal": "x"})
        rows = _command_history_rows(agent)
        assert "seq" in rows[0]
        assert rows[0]["seq"] == 1

    def test_history_entry_has_type_key(self, agent):
        """mutmut_64/65: history entry has 'type' key (not 'XXtypeXX' or 'TYPE')."""
        _queue_manager_command(agent, "set_goal", {"goal": "x"})
        rows = _command_history_rows(agent)
        assert "type" in rows[0]
        assert rows[0]["type"] == "set_goal"

    def test_history_entry_has_payload_key(self, agent):
        """mutmut_66/67: history entry has 'payload' key."""
        _queue_manager_command(agent, "set_goal", {"goal": "x"})
        rows = _command_history_rows(agent)
        assert "payload" in rows[0]
        assert rows[0]["payload"] == {"goal": "x"}

    def test_history_entry_status_is_queued(self, agent):
        """mutmut_69/70/71/72: history entry status is 'queued' (not 'QUEUED' etc)."""
        _queue_manager_command(agent, "set_goal", {"goal": "x"})
        rows = _command_history_rows(agent)
        assert rows[0]["status"] == "queued"

    def test_history_entry_has_queued_at_key(self, agent):
        """mutmut_73/74: history entry has 'queued_at' key."""
        _queue_manager_command(agent, "set_goal", {"goal": "x"})
        rows = _command_history_rows(agent)
        assert "queued_at" in rows[0]
        assert rows[0]["queued_at"] > 0

    def test_history_entry_has_updated_at_key(self, agent):
        """mutmut_75/76: history entry has 'updated_at' key."""
        _queue_manager_command(agent, "set_goal", {"goal": "x"})
        rows = _command_history_rows(agent)
        assert "updated_at" in rows[0]
        assert rows[0]["updated_at"] > 0

    def test_history_entry_has_replaces_key(self, agent):
        """mutmut_77/78: history entry has 'replaces' key."""
        _queue_manager_command(agent, "set_goal", {"goal": "x"})
        rows = _command_history_rows(agent)
        assert "replaces" in rows[0]
        assert rows[0]["replaces"] is None

    def test_history_entry_has_replaced_by_key(self, agent):
        """mutmut_81/82: history entry has 'replaced_by' key (not 'XXreplaced_byXX')."""
        _queue_manager_command(agent, "set_goal", {"goal": "x"})
        rows = _command_history_rows(agent)
        assert "replaced_by" in rows[0]
        assert rows[0]["replaced_by"] is None

    def test_history_entry_has_cancelled_reason_key(self, agent):
        """mutmut_83/84: history entry has 'cancelled_reason' key with None value."""
        _queue_manager_command(agent, "set_goal", {"goal": "x"})
        rows = _command_history_rows(agent)
        assert "cancelled_reason" in rows[0]
        assert rows[0]["cancelled_reason"] is None

    def test_history_entry_replaces_set_when_replacing(self, agent):
        """mutmut_77/78: replaces field set in history when replacing existing command."""
        _queue_manager_command(agent, "set_goal", {"goal": "x"})
        _queue_manager_command(agent, "set_goal", {"goal": "y"})
        rows = _command_history_rows(agent)
        second = next(r for r in rows if r["seq"] == 2)
        assert second["replaces"] == 1


# ===========================================================================
# routes/agent_ops.py — _cancel_pending_manager_command (detailed)
# ===========================================================================


class TestCancelPendingCommandExtra:
    def test_default_reason_is_operator_cancelled(self, agent):
        """mutmut_1/2: default reason is 'operator_cancelled' (exact string)."""
        agent.pending_command_seq = 1
        agent.pending_command_type = "set_goal"
        agent.pending_command_payload = {}
        result = _cancel_pending_manager_command(agent)
        assert result is not None
        assert result["cancelled_reason"] == "operator_cancelled"

    def test_returns_none_when_seq_zero(self, agent):
        """mutmut_30: pending_seq <= 0 check — seq=0 returns None."""
        agent.pending_command_seq = 0
        agent.pending_command_type = "set_goal"
        assert _cancel_pending_manager_command(agent) is None

    def test_returns_none_when_type_empty(self, agent):
        """mutmut_29: 'and' vs 'or' — seq>0 but type="" still returns None."""
        agent.pending_command_seq = 1
        agent.pending_command_type = ""
        assert _cancel_pending_manager_command(agent) is None

    def test_both_conditions_required(self, agent):
        """mutmut_29: seq<=0 OR empty type → None. Both must be satisfied for cancel."""
        # seq=0 with type set → None
        agent.pending_command_seq = 0
        agent.pending_command_type = "set_goal"
        assert _cancel_pending_manager_command(agent) is None
        # seq>0 with empty type → None
        agent.pending_command_seq = 5
        agent.pending_command_type = ""
        assert _cancel_pending_manager_command(agent) is None

    def test_cancelled_result_has_seq_key(self, agent):
        """mutmut_34/35: result has 'seq' key (not 'XXseqXX' or 'SEQ')."""
        agent.pending_command_seq = 3
        agent.pending_command_type = "set_goal"
        agent.pending_command_payload = {}
        result = _cancel_pending_manager_command(agent)
        assert result is not None
        assert "seq" in result
        assert result["seq"] == 3

    def test_cancelled_result_has_type_key(self, agent):
        """mutmut_36/37: result has 'type' key (not 'XXtypeXX' or 'TYPE')."""
        agent.pending_command_seq = 1
        agent.pending_command_type = "set_directive"
        agent.pending_command_payload = {}
        result = _cancel_pending_manager_command(agent)
        assert result is not None
        assert "type" in result
        assert result["type"] == "set_directive"

    def test_cancelled_result_has_payload_key(self, agent):
        """mutmut_38/39: result has 'payload' key (not 'XXpayloadXX' or 'PAYLOAD')."""
        agent.pending_command_seq = 1
        agent.pending_command_type = "set_goal"
        agent.pending_command_payload = {"goal": "x"}
        result = _cancel_pending_manager_command(agent)
        assert result is not None
        assert "payload" in result

    def test_cancelled_result_has_cancelled_reason_key(self, agent):
        """mutmut_50/51: result has 'cancelled_reason' key."""
        agent.pending_command_seq = 1
        agent.pending_command_type = "set_goal"
        agent.pending_command_payload = {}
        result = _cancel_pending_manager_command(agent, "test_reason")
        assert result is not None
        assert "cancelled_reason" in result
        assert result["cancelled_reason"] == "test_reason"

    def test_payload_from_agent_attr(self, agent):
        """mutmut_41/42/44/47/48/49: payload comes from agent.pending_command_payload."""
        agent.pending_command_seq = 1
        agent.pending_command_type = "set_goal"
        agent.pending_command_payload = {"key": "val"}
        result = _cancel_pending_manager_command(agent)
        assert result is not None
        assert result["payload"] == {"key": "val"}

    def test_history_updated_with_cancelled_status(self, agent):
        """mutmut_54/62/63: _update_command_history called with status='cancelled'."""
        _queue_manager_command(agent, "set_goal", {"goal": "x"})
        _cancel_pending_manager_command(agent)
        rows = _command_history_rows(agent)
        assert rows[0]["status"] == "cancelled"

    def test_history_updated_with_cancelled_reason(self, agent):
        """mutmut_55: cancelled_reason passed to history update."""
        _queue_manager_command(agent, "set_goal", {"goal": "x"})
        _cancel_pending_manager_command(agent, "my_reason")
        rows = _command_history_rows(agent)
        assert rows[0]["cancelled_reason"] == "my_reason"

    def test_seq_reset_to_zero_after_cancel(self, agent):
        """mutmut_66: pending_command_seq = 0 after cancel."""
        agent.pending_command_seq = 5
        agent.pending_command_type = "set_goal"
        agent.pending_command_payload = {}
        _cancel_pending_manager_command(agent)
        assert agent.pending_command_seq == 0

    def test_type_reset_to_none_after_cancel(self, agent):
        """mutmut_66: pending_command_type = None (not empty string)."""
        agent.pending_command_seq = 1
        agent.pending_command_type = "set_goal"
        agent.pending_command_payload = {}
        _cancel_pending_manager_command(agent)
        assert agent.pending_command_type is None

    def test_payload_reset_to_empty_dict_after_cancel(self, agent):
        """mutmut_67: pending_command_payload = {} (not None)."""
        agent.pending_command_seq = 1
        agent.pending_command_type = "set_goal"
        agent.pending_command_payload = {"goal": "x"}
        _cancel_pending_manager_command(agent)
        assert agent.pending_command_payload == {}
        assert agent.pending_command_payload is not None


# ===========================================================================
# routes/agent_ops.py — _build_action_response (plugin path)
# ===========================================================================


class TestBuildActionResponseExtra:
    def test_plugin_called_with_all_args(self):
        """mutmut_9-14: plugin called with correct args (not None substitutions)."""
        plugin = MagicMock()
        plugin.build_action_response.return_value = {"ok": True}
        _build_action_response(
            "agent_X",
            "pause",
            "local_runtime",
            applied=True,
            queued=False,
            result={"key": "v"},
            state="running",
            plugin=plugin,
        )
        plugin.build_action_response.assert_called_once_with(
            "agent_X",
            "pause",
            "local_runtime",
            applied=True,
            queued=False,
            result={"key": "v"},
            state="running",
        )

    def test_plugin_agent_id_not_none(self):
        """mutmut_9: first positional arg is agent_id, not None."""
        plugin = MagicMock()
        plugin.build_action_response.return_value = {}
        _build_action_response("real_agent", "a", "s", applied=True, queued=False, result={}, state="x", plugin=plugin)
        call_args = plugin.build_action_response.call_args
        assert call_args[0][0] == "real_agent"

    def test_plugin_action_not_none(self):
        """mutmut_10: second positional arg is action, not None."""
        plugin = MagicMock()
        plugin.build_action_response.return_value = {}
        _build_action_response("b", "my_action", "s", applied=True, queued=False, result={}, state="x", plugin=plugin)
        call_args = plugin.build_action_response.call_args
        assert call_args[0][1] == "my_action"

    def test_plugin_source_not_none(self):
        """mutmut_11: third positional arg is source, not None."""
        plugin = MagicMock()
        plugin.build_action_response.return_value = {}
        _build_action_response("b", "a", "my_source", applied=True, queued=False, result={}, state="x", plugin=plugin)
        call_args = plugin.build_action_response.call_args
        assert call_args[0][2] == "my_source"

    def test_plugin_applied_kwarg_not_none(self):
        """mutmut_12: applied kwarg passed (not None)."""
        plugin = MagicMock()
        plugin.build_action_response.return_value = {}
        _build_action_response("b", "a", "s", applied=True, queued=False, result={}, state="x", plugin=plugin)
        call_kwargs = plugin.build_action_response.call_args[1]
        assert call_kwargs["applied"] is True

    def test_plugin_queued_kwarg_not_none(self):
        """mutmut_13: queued kwarg passed (not None)."""
        plugin = MagicMock()
        plugin.build_action_response.return_value = {}
        _build_action_response("b", "a", "s", applied=False, queued=True, result={}, state="x", plugin=plugin)
        call_kwargs = plugin.build_action_response.call_args[1]
        assert call_kwargs["queued"] is True

    def test_no_plugin_returns_dict_with_all_keys(self):
        """mutmut_27-36: all keys present in no-plugin result."""
        result = _build_action_response(
            "agent_z", "restart", "manager", applied=True, queued=False, result={"restarted": True}, state="running"
        )
        assert result["agent_id"] == "agent_z"
        assert result["action"] == "restart"
        assert result["source"] == "manager"
        assert result["applied"] is True
        assert result["queued"] is False
        assert result["result"] == {"restarted": True}
        assert result["state"] == "running"


# ===========================================================================
# auth.py — TokenAuthMiddleware.__call__ (targeted mutants)
# ===========================================================================
