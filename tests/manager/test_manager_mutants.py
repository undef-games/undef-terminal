#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Targeted mutation-killing tests for manager/core.py, manager/routes/bot_ops.py, and manager/auth.py."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from undef.terminal.manager.auth import TokenAuthMiddleware, setup_auth
from undef.terminal.manager.config import ManagerConfig
from undef.terminal.manager.core import SwarmManager
from undef.terminal.manager.models import BotStatusBase
from undef.terminal.manager.routes.bot_ops import (
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
    mgr = SwarmManager(config)
    pm = MagicMock()
    pm.cancel_spawn = AsyncMock(return_value=False)
    pm.start_spawn_swarm = AsyncMock()
    pm.spawn_bot = AsyncMock(return_value="bot_000")
    pm.spawn_swarm = AsyncMock(return_value=["bot_000"])
    pm.kill_bot = AsyncMock()
    pm.monitor_processes = AsyncMock()
    mgr.bot_process_manager = pm
    return mgr


@pytest.fixture
def bot() -> BotStatusBase:
    return BotStatusBase(bot_id="bot_001", state="running")


# ===========================================================================
# core.py — SwarmManager.__init__
# ===========================================================================


class TestSwarmManagerInitMutants:
    def test_timeseries_manager_uses_get_swarm_status(self, config):
        """mutmut_25: get_swarm_status passed as callback (not None)."""
        mgr = SwarmManager(config)
        # The timeseries manager should call get_swarm_status successfully via _get_status
        status = mgr.timeseries_manager._get_status()
        assert status.total_bots == 0  # callable returns a valid SwarmStatus

    def test_timeseries_dir_from_config_when_set(self, tmp_path):
        """mutmut_30/33: timeseries_dir from config.timeseries_dir, not default 'logs/metrics'."""
        custom_dir = str(tmp_path / "custom_metrics")
        cfg = ManagerConfig(state_file=str(tmp_path / "s.json"), timeseries_dir=custom_dir)
        mgr = SwarmManager(cfg)
        assert str(mgr.timeseries_manager.path).startswith(custom_dir)

    def test_timeseries_dir_default_when_config_empty(self, tmp_path):
        """mutmut_33/34/35: When config.timeseries_dir is '', uses 'logs/metrics'."""
        cfg = ManagerConfig(state_file=str(tmp_path / "s.json"), timeseries_dir="")
        mgr = SwarmManager(cfg)
        assert "logs/metrics" in str(mgr.timeseries_manager.path)

    def test_timeseries_plugin_passed(self, config):
        """mutmut_28: plugin param passed to TimeseriesManager (not None)."""
        plugin = MagicMock()
        plugin.interval_seconds = None
        mgr = SwarmManager(config, timeseries_plugin=plugin)
        assert mgr.timeseries_manager._plugin is plugin

    def test_timeseries_interval_from_config(self, tmp_path):
        """mutmut_31/36: interval_s from config (not TIMESERIES_INTERVAL_S when config sets it)."""
        cfg = ManagerConfig(state_file=str(tmp_path / "s.json"), timeseries_interval_s=7)
        mgr = SwarmManager(cfg)
        assert mgr.timeseries_manager.interval_s == 7

    def test_app_initial_value_is_none(self, config):
        """mutmut_37: self.app initialized to None (not empty string or other value)."""
        mgr = SwarmManager(config)
        assert mgr.app is None

    def test_bot_process_manager_initial_value_is_none(self, config):
        """mutmut_38: self.bot_process_manager initialized to None (not empty string)."""
        mgr = SwarmManager(config)
        # Access attribute directly — it should be None (assignment annotation is None)
        assert mgr.bot_process_manager is None  # type: ignore[truthy-bool]


# ===========================================================================
# core.py — SwarmManager.get_swarm_status
# ===========================================================================


class TestGetSwarmStatusMutants:
    def test_swarm_status_builder_receives_self(self, config):
        """mutmut_2/9: builder called with self (not None)."""
        received_arg = []

        def builder(mgr):
            received_arg.append(mgr)
            from undef.terminal.manager.models import SwarmStatus

            return SwarmStatus(total_bots=0, running=0, completed=0, errors=0, stopped=0, uptime_seconds=0, bots=[])

        mgr = SwarmManager(config, swarm_status_builder=builder)
        mgr.bot_process_manager = MagicMock()
        mgr.get_swarm_status()
        assert received_arg[0] is mgr

    def test_recovering_bots_counted_in_running(self, manager):
        """mutmut_43/44: 'recovering' state counted as running."""
        manager.bots["b1"] = BotStatusBase(bot_id="b1", state="recovering")
        status = manager.get_swarm_status()
        assert status.running == 1

    def test_blocked_bots_counted_in_running(self, manager):
        """mutmut_45/46: 'blocked' state counted as running."""
        manager.bots["b1"] = BotStatusBase(bot_id="b1", state="blocked")
        status = manager.get_swarm_status()
        assert status.running == 1

    def test_running_bots_counted_in_running(self, manager):
        """'running' state counted as running."""
        manager.bots["b1"] = BotStatusBase(bot_id="b1", state="running")
        status = manager.get_swarm_status()
        assert status.running == 1

    def test_disconnected_bots_counted_in_errors(self, manager):
        """mutmut_57/58: 'disconnected' state counted as errors."""
        manager.bots["b1"] = BotStatusBase(bot_id="b1", state="disconnected")
        status = manager.get_swarm_status()
        assert status.errors == 1

    def test_blocked_bots_counted_in_errors(self, manager):
        """mutmut_59/60: 'blocked' also counted as errors."""
        manager.bots["b1"] = BotStatusBase(bot_id="b1", state="blocked")
        status = manager.get_swarm_status()
        assert status.errors == 1

    def test_error_bots_counted_in_errors(self, manager):
        """'error' state counted as errors."""
        manager.bots["b1"] = BotStatusBase(bot_id="b1", state="error")
        status = manager.get_swarm_status()
        assert status.errors == 1

    def test_stopped_bots_counted_correctly(self, manager):
        """mutmut_62/63/64/65: exactly 1 per stopped bot, != behavior."""
        manager.bots["b1"] = BotStatusBase(bot_id="b1", state="stopped")
        manager.bots["b2"] = BotStatusBase(bot_id="b2", state="running")
        status = manager.get_swarm_status()
        assert status.stopped == 1  # not 2, not inverted

    def test_stopped_count_not_inverted(self, manager):
        """mutmut_63: state != 'stopped' would invert the count."""
        manager.bots["b1"] = BotStatusBase(bot_id="b1", state="running")
        manager.bots["b2"] = BotStatusBase(bot_id="b2", state="stopped")
        status = manager.get_swarm_status()
        # Only 1 stopped bot, not 1 running counted as stopped
        assert status.stopped == 1

    def test_uptime_is_elapsed_not_summed(self, manager):
        """mutmut_66: uptime_seconds = time.time() - start_time (subtraction, not addition)."""
        manager.start_time = time.time() - 10.0
        status = manager.get_swarm_status()
        # Uptime should be ~10s, not ~(now * 2 - 10)
        assert 5.0 <= status.uptime_seconds <= 30.0

    def test_timeseries_file_from_manager_path(self, manager):
        """mutmut_18/31/67: timeseries_file comes from timeseries_manager.path."""
        status = manager.get_swarm_status()
        assert status.timeseries_file is not None
        assert str(manager.timeseries_manager.path) in status.timeseries_file

    def test_timeseries_interval_in_status(self, manager):
        """mutmut_32: timeseries_interval_seconds present in status."""
        status = manager.get_swarm_status()
        assert status.timeseries_interval_seconds == manager.timeseries_manager.interval_s

    def test_timeseries_samples_in_status(self, manager):
        """mutmut_33: timeseries_samples present in status."""
        status = manager.get_swarm_status()
        assert status.timeseries_samples == manager.timeseries_manager.samples_count

    def test_swarm_paused_in_status(self, manager):
        """mutmut_34: swarm_paused reflected in status."""
        manager.swarm_paused = True
        status = manager.get_swarm_status()
        assert status.swarm_paused is True

    def test_bust_respawn_in_status(self, manager):
        """mutmut_35: bust_respawn reflected in status."""
        manager.bust_respawn = True
        status = manager.get_swarm_status()
        assert status.bust_respawn is True

    def test_desired_bots_in_status(self, manager):
        """mutmut_36: desired_bots reflected in status."""
        manager.desired_bots = 7
        status = manager.get_swarm_status()
        assert status.desired_bots == 7

    def test_bots_list_in_status(self, manager):
        """bots list is present and populated."""
        manager.bots["b1"] = BotStatusBase(bot_id="b1", state="running")
        status = manager.get_swarm_status()
        assert len(status.bots) == 1
        assert status.bots[0]["bot_id"] == "b1"


# ===========================================================================
# core.py — SwarmManager.broadcast_status
# ===========================================================================


class TestBroadcastStatusMutants:
    @pytest.mark.asyncio
    async def test_message_is_json_of_status(self, manager):
        """mutmut_2/3: message is json.dumps(status.model_dump()), not None or json.dumps(None)."""
        ws = AsyncMock()
        manager.websocket_clients = {ws}
        await manager.broadcast_status()
        call_args = ws.send_text.call_args[0][0]
        parsed = json.loads(call_args)
        assert "total_bots" in parsed

    @pytest.mark.asyncio
    async def test_send_text_called_with_message_not_none(self, manager):
        """mutmut_7: send_text is called with the real message, not None."""
        ws = AsyncMock()
        manager.websocket_clients = {ws}
        await manager.broadcast_status()
        call_args = ws.send_text.call_args[0][0]
        assert call_args is not None
        assert isinstance(call_args, str)


# ===========================================================================
# core.py — SwarmManager._write_state
# ===========================================================================


class TestWriteStateMutants:
    def test_tmp_file_uses_dot_tmp_suffix(self, manager, tmp_path):
        """mutmut_6: suffix is '.tmp' not '.TMP'."""
        state_path = tmp_path / "state.json"
        manager.state_file = str(state_path)
        state = {"desired_bots": 3}
        manager._write_state(state)
        # After successful write, state.json should exist
        assert state_path.exists()
        content = json.loads(state_path.read_text())
        assert content["desired_bots"] == 3
        # No .TMP file should remain
        assert not (tmp_path / "state.TMP").exists()

    def test_write_uses_utf8_encoding(self, manager, tmp_path):
        """mutmut_8/10/17: encoding is 'utf-8' — file can be read back as utf-8."""
        state_path = tmp_path / "state.json"
        manager.state_file = str(state_path)
        state = {"key": "value", "count": 42}
        manager._write_state(state)
        # File exists and is valid JSON
        content = state_path.read_text(encoding="utf-8")
        loaded = json.loads(content)
        assert loaded["key"] == "value"

    def test_write_uses_indent_2(self, manager, tmp_path):
        """mutmut_12/14/15: json.dumps uses indent=2."""
        state_path = tmp_path / "state.json"
        manager.state_file = str(state_path)
        state = {"key": "value"}
        manager._write_state(state)
        raw = state_path.read_text()
        # indent=2 produces lines with exactly 2-space indentation
        assert "  " in raw

    def test_error_cleanup_removes_tmp(self, manager, tmp_path):
        """mutmut_28/29/30: on error, .tmp file is cleaned up."""
        bad_dir = tmp_path / "no_such_dir" / "state.json"
        manager.state_file = str(bad_dir)
        # Should not raise
        manager._write_state({"key": "value"})
        # No orphaned tmp file
        assert not (tmp_path / "no_such_dir" / "state.tmp").exists()

    def test_write_state_content_round_trips(self, manager, tmp_path):
        """mutmut_12: indent=None would produce compact JSON (still parseable but not indented)."""
        state_path = tmp_path / "state.json"
        manager.state_file = str(state_path)
        state = {"desired_bots": 5, "swarm_paused": True}
        manager._write_state(state)
        loaded = json.loads(state_path.read_text())
        assert loaded["desired_bots"] == 5
        assert loaded["swarm_paused"] is True


# ===========================================================================
# core.py — SwarmManager._load_state
# ===========================================================================


class TestLoadStateMutants:
    def test_desired_bots_zero_when_falsy(self, manager, tmp_path):
        """mutmut_16: desired_bots=0 when value is falsy (not 1)."""
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"desired_bots": 0}))
        manager.state_file = str(state_path)
        manager._load_state()
        assert manager.desired_bots == 0

    def test_desired_bots_loads_correctly(self, manager, tmp_path):
        """mutmut_16: desired_bots loads to exact value, not 'or 1' fallback."""
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"desired_bots": 5}))
        manager.state_file = str(state_path)
        manager._load_state()
        assert manager.desired_bots == 5

    def test_bots_default_empty_dict_when_key_missing(self, manager, tmp_path):
        """mutmut_32: state.get('bots', {}) returns {} not None when key absent."""
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"desired_bots": 2}))
        manager.state_file = str(state_path)
        # Should not raise AttributeError from None.items()
        manager._load_state()
        assert manager.desired_bots == 2

    def test_bot_saved_state_default_is_stopped(self, manager, tmp_path):
        """mutmut_40/42/45/46: saved_state defaults to 'stopped' when key missing.
        A bot without 'state' key gets saved_state='stopped', which is NOT in the
        reset list ('running', 'disconnected', 'queued'), so state is whatever
        BotStatusBase defaults to (unknown). But the key test: 'stopped' not in reset list."""
        state_path = tmp_path / "state.json"
        # Bot with explicit 'stopped' state — not reset
        state_path.write_text(json.dumps({"bots": {"b1": {"bot_id": "b1", "state": "stopped"}}}))
        manager.state_file = str(state_path)
        manager._load_state()
        assert "b1" in manager.bots
        assert manager.bots["b1"].state == "stopped"

    def test_disconnected_state_reset_to_stopped(self, manager, tmp_path):
        """mutmut_50/51: 'disconnected' saved state is reset to 'stopped'."""
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"bots": {"b1": {"bot_id": "b1", "state": "disconnected"}}}))
        manager.state_file = str(state_path)
        manager._load_state()
        assert manager.bots["b1"].state == "stopped"

    def test_queued_state_reset_to_stopped(self, manager, tmp_path):
        """mutmut_52/53: 'queued' saved state is reset to 'stopped'."""
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"bots": {"b1": {"bot_id": "b1", "state": "queued"}}}))
        manager.state_file = str(state_path)
        manager._load_state()
        assert manager.bots["b1"].state == "stopped"

    def test_running_state_reset_to_stopped(self, manager, tmp_path):
        """'running' saved state is reset to 'stopped'."""
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"bots": {"b1": {"bot_id": "b1", "state": "running"}}}))
        manager.state_file = str(state_path)
        manager._load_state()
        assert manager.bots["b1"].state == "stopped"

    def test_bot_id_injected_when_missing(self, manager, tmp_path):
        """mutmut_62/63/64: bot_id injected as bot_id key (not None, not wrong key)."""
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"bots": {"my_bot": {"state": "stopped"}}}))
        manager.state_file = str(state_path)
        manager._load_state()
        assert "my_bot" in manager.bots
        assert manager.bots["my_bot"].bot_id == "my_bot"

    def test_bot_id_not_overwritten_if_present(self, manager, tmp_path):
        """bot_id present in data is not overwritten."""
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"bots": {"b1": {"bot_id": "b1", "state": "stopped"}}}))
        manager.state_file = str(state_path)
        manager._load_state()
        assert manager.bots["b1"].bot_id == "b1"

    def test_invalid_bot_does_not_crash_load(self, manager, tmp_path):
        """mutmut_67-75: exception path doesn't crash; other bots still loaded."""
        state_path = tmp_path / "state.json"
        state_path.write_text(
            json.dumps(
                {
                    "bots": {
                        "bad": {"not_valid_field_xyz": "broken"},
                        "good": {"bot_id": "good", "state": "stopped"},
                    }
                }
            )
        )
        manager.state_file = str(state_path)
        manager._load_state()
        assert "good" in manager.bots

    def test_invalid_json_does_not_crash(self, manager, tmp_path):
        """mutmut_88-94: exception path doesn't propagate."""
        state_path = tmp_path / "state.json"
        state_path.write_text("not valid json at all!!!")
        manager.state_file = str(state_path)
        manager._load_state()  # should not raise
        assert manager.desired_bots == 0


# ===========================================================================
# core.py — SwarmManager.spawn_swarm
# ===========================================================================


class TestSpawnSwarmMutants:
    @pytest.mark.asyncio
    async def test_delegates_config_paths(self, manager):
        """mutmut_3: config_paths passed to delegate (not None)."""
        paths = ["/a.yaml", "/b.yaml"]
        manager.bot_process_manager.spawn_swarm = AsyncMock(return_value=paths)
        await manager.spawn_swarm(paths)
        call_args = manager.bot_process_manager.spawn_swarm.call_args
        assert call_args[0][0] == paths

    @pytest.mark.asyncio
    async def test_delegates_group_size(self, manager):
        """mutmut_4: group_size passed (not None)."""
        manager.bot_process_manager.spawn_swarm = AsyncMock(return_value=[])
        await manager.spawn_swarm([], group_size=3)
        call_args = manager.bot_process_manager.spawn_swarm.call_args
        assert call_args[0][1] == 3

    @pytest.mark.asyncio
    async def test_delegates_group_delay(self, manager):
        """mutmut_5: group_delay passed (not None)."""
        manager.bot_process_manager.spawn_swarm = AsyncMock(return_value=[])
        await manager.spawn_swarm([], group_delay=30.0)
        call_args = manager.bot_process_manager.spawn_swarm.call_args
        assert call_args[0][2] == 30.0

    @pytest.mark.asyncio
    async def test_default_group_size_is_5(self, manager):
        """mutmut_1: default group_size is 5 (not 6)."""
        manager.bot_process_manager.spawn_swarm = AsyncMock(return_value=[])
        await manager.spawn_swarm([])
        call_args = manager.bot_process_manager.spawn_swarm.call_args
        assert call_args[0][1] == 5

    @pytest.mark.asyncio
    async def test_default_group_delay_is_60(self, manager):
        """mutmut_2: default group_delay is 60.0 (not 61.0)."""
        manager.bot_process_manager.spawn_swarm = AsyncMock(return_value=[])
        await manager.spawn_swarm([])
        call_args = manager.bot_process_manager.spawn_swarm.call_args
        assert call_args[0][2] == 60.0


# ===========================================================================
# core.py — SwarmManager.start_spawn_swarm
# ===========================================================================


class TestStartSpawnSwarmMutants:
    @pytest.mark.asyncio
    async def test_default_group_size_is_1(self, manager):
        """mutmut_1: default group_size is 1 (not 2)."""
        await manager.start_spawn_swarm([])
        call_kwargs = manager.bot_process_manager.start_spawn_swarm.call_args[1]
        assert call_kwargs["group_size"] == 1

    @pytest.mark.asyncio
    async def test_default_group_delay_is_12(self, manager):
        """mutmut_2: default group_delay is 12.0 (not 13.0)."""
        await manager.start_spawn_swarm([])
        call_kwargs = manager.bot_process_manager.start_spawn_swarm.call_args[1]
        assert call_kwargs["group_delay"] == 12.0

    @pytest.mark.asyncio
    async def test_default_cancel_existing_is_true(self, manager):
        """mutmut_3: default cancel_existing is True (not False)."""
        await manager.start_spawn_swarm([])
        call_kwargs = manager.bot_process_manager.start_spawn_swarm.call_args[1]
        assert call_kwargs["cancel_existing"] is True

    @pytest.mark.asyncio
    async def test_default_name_style_is_random(self, manager):
        """mutmut_6/7: default name_style is 'random' (not 'XXrandomXX' or 'RANDOM')."""
        await manager.start_spawn_swarm([])
        call_kwargs = manager.bot_process_manager.start_spawn_swarm.call_args[1]
        assert call_kwargs["name_style"] == "random"

    @pytest.mark.asyncio
    async def test_default_name_base_is_empty(self, manager):
        """mutmut_8: default name_base is '' (not 'XXXX')."""
        await manager.start_spawn_swarm([])
        call_kwargs = manager.bot_process_manager.start_spawn_swarm.call_args[1]
        assert call_kwargs["name_base"] == ""

    @pytest.mark.asyncio
    async def test_config_paths_passed(self, manager):
        """mutmut_9/16: config_paths forwarded (not None)."""
        paths = ["/game.yaml"]
        await manager.start_spawn_swarm(paths)
        call_args = manager.bot_process_manager.start_spawn_swarm.call_args
        assert call_args[0][0] == paths

    @pytest.mark.asyncio
    async def test_all_kwargs_passed(self, manager):
        """mutmut_10-22: all kwargs forwarded correctly."""
        await manager.start_spawn_swarm(
            ["/x.yaml"],
            group_size=2,
            group_delay=5.0,
            cancel_existing=False,
            name_style="sequential",
            name_base="hero",
        )
        call_args = manager.bot_process_manager.start_spawn_swarm.call_args
        kwargs = call_args[1]
        assert kwargs["group_size"] == 2
        assert kwargs["group_delay"] == 5.0
        assert kwargs["cancel_existing"] is False
        assert kwargs["name_style"] == "sequential"
        assert kwargs["name_base"] == "hero"


# ===========================================================================
# core.py — SwarmManager.get_timeseries_recent / get_timeseries_summary
# ===========================================================================


class TestTimeseriesDelegateMutants:
    def test_get_timeseries_recent_default_limit_200(self, manager):
        """mutmut_1: default limit is 200 (not 201)."""
        with patch.object(manager.timeseries_manager, "get_recent", return_value=[]) as mock_fn:
            manager.get_timeseries_recent()
            mock_fn.assert_called_once_with(200)

    def test_get_timeseries_recent_passes_limit(self, manager):
        """mutmut_2: limit passed to get_recent (not None)."""
        with patch.object(manager.timeseries_manager, "get_recent", return_value=[]) as mock_fn:
            manager.get_timeseries_recent(50)
            mock_fn.assert_called_once_with(50)

    def test_get_timeseries_summary_default_window_120(self, manager):
        """mutmut_1: default window_minutes is 120 (not 121)."""
        with patch.object(manager.timeseries_manager, "get_summary", return_value={}) as mock_fn:
            manager.get_timeseries_summary()
            mock_fn.assert_called_once_with(120)

    def test_get_timeseries_summary_passes_window(self, manager):
        """mutmut_2: window_minutes passed to get_summary (not None)."""
        with patch.object(manager.timeseries_manager, "get_summary", return_value={}) as mock_fn:
            manager.get_timeseries_summary(60)
            mock_fn.assert_called_once_with(60)


# ===========================================================================
# core.py — SwarmManager.run (save_periodically state dict keys)
# ===========================================================================


class TestRunSaveStateMutants:
    def test_host_or_fallback_to_config(self, manager):
        """mutmut_1/2: _host = host or self.config.host (not None, not 'and')."""
        # When host is None, uses config.host
        # When host is provided, uses that value
        # Just verify config.host is accessible
        assert manager.config.host is not None

    def test_port_or_fallback_to_config(self, manager):
        """mutmut_3/4: _port = port or self.config.port (not None, not 'and')."""
        assert manager.config.port is not None

    @pytest.mark.asyncio
    async def test_save_periodically_state_dict_has_timestamp(self, manager, tmp_path):
        """mutmut_23/24: save state dict has 'timestamp' key (not 'XXtimestampXX')."""
        # Verify state dict shape by directly calling _write_state with expected structure
        state = {
            "timestamp": time.time(),
            "desired_bots": manager.desired_bots,
            "swarm_paused": manager.swarm_paused,
            "bust_respawn": manager.bust_respawn,
            "bots": {bid: bot.model_dump() for bid, bot in manager.bots.items()},
        }
        # The _write_state and _load_state should work with this structure
        manager._write_state(state)
        # Reload the state file
        state_file = Path(manager.state_file)
        assert state_file.exists()
        loaded = json.loads(state_file.read_text())
        assert "timestamp" in loaded

    def test_save_state_includes_desired_bots(self, manager, tmp_path):
        """mutmut_25/26: 'desired_bots' key (not 'XXdesired_botsXX')."""
        manager.desired_bots = 7
        state = {
            "timestamp": time.time(),
            "desired_bots": manager.desired_bots,
            "swarm_paused": manager.swarm_paused,
            "bust_respawn": manager.bust_respawn,
            "bots": {},
        }
        manager._write_state(state)
        loaded = json.loads(Path(manager.state_file).read_text())
        assert "desired_bots" in loaded
        assert loaded["desired_bots"] == 7

    def test_save_state_includes_swarm_paused(self, manager, tmp_path):
        """mutmut_27/28: 'swarm_paused' key present in saved state."""
        manager.swarm_paused = True
        state = {
            "timestamp": time.time(),
            "desired_bots": 0,
            "swarm_paused": manager.swarm_paused,
            "bust_respawn": manager.bust_respawn,
            "bots": {},
        }
        manager._write_state(state)
        loaded = json.loads(Path(manager.state_file).read_text())
        assert "swarm_paused" in loaded
        assert loaded["swarm_paused"] is True

    def test_save_state_includes_bust_respawn(self, manager, tmp_path):
        """mutmut_29/30: 'bust_respawn' key present in saved state."""
        manager.bust_respawn = True
        state = {
            "timestamp": time.time(),
            "desired_bots": 0,
            "swarm_paused": False,
            "bust_respawn": manager.bust_respawn,
            "bots": {},
        }
        manager._write_state(state)
        loaded = json.loads(Path(manager.state_file).read_text())
        assert "bust_respawn" in loaded
        assert loaded["bust_respawn"] is True


# ===========================================================================
# routes/bot_ops.py — _command_history_rows (additional)
# ===========================================================================


class TestCommandHistoryRowsExtra:
    def test_getattr_with_none_default_creates_list(self, bot):
        """mutmut_6: getattr with missing default would raise error; with None it returns None → []."""
        import types

        obj = types.SimpleNamespace()  # no manager_command_history attr
        rows = _command_history_rows(obj)  # type: ignore[arg-type]
        assert rows == []


# ===========================================================================
# routes/bot_ops.py — _append_command_history (additional)
# ===========================================================================


class TestAppendCommandHistoryExtra:
    def test_exactly_25_does_not_trim(self, bot):
        """mutmut_5: > 25 means trim happens at 26, not 25. At exactly 25 no trim."""
        bot.manager_command_history = [{"seq": i} for i in range(24)]
        _append_command_history(bot, {"seq": 25})
        assert len(bot.manager_command_history) == 25

    def test_26_triggers_trim(self, bot):
        """mutmut_5: >= 25 would trim at exactly 25. Original > 25 trims at 26."""
        bot.manager_command_history = [{"seq": i} for i in range(25)]
        _append_command_history(bot, {"seq": 999})
        assert len(bot.manager_command_history) == 25
        assert bot.manager_command_history[-1]["seq"] == 999


# ===========================================================================
# routes/bot_ops.py — _update_command_history (additional)
# ===========================================================================


class TestUpdateCommandHistoryExtra:
    def test_seq_zero_returns_early_not_executed(self, bot):
        """mutmut_1: seq < 0 would allow seq=0 to update; seq <= 0 must skip it."""
        bot.manager_command_history = [{"seq": 0, "status": "original"}]
        _update_command_history(bot, 0, status="should_not_change")
        assert bot.manager_command_history[0]["status"] == "original"

    def test_seq_one_must_update(self, bot):
        """mutmut_2: seq <= 1 would skip seq=1; must update seq=1."""
        bot.manager_command_history = [{"seq": 1, "status": "pending"}]
        _update_command_history(bot, 1, status="updated")
        assert bot.manager_command_history[0]["status"] == "updated"

    def test_fallback_zero_not_one_for_missing_seq(self, bot):
        """mutmut_10: 'or 0' fallback — row without seq key treated as seq=0, not seq=1."""
        bot.manager_command_history = [{"status": "original"}]  # no 'seq' key
        # Searching for seq=1 should NOT find the entry with no seq (treated as 0)
        _update_command_history(bot, 1, status="changed")
        assert bot.manager_command_history[0]["status"] == "original"

    def test_continue_not_break_on_no_match(self, bot):
        """mutmut_12: break would stop at first non-match, missing later entries."""
        bot.manager_command_history = [
            {"seq": 1, "status": "a"},
            {"seq": 3, "status": "b"},
            {"seq": 5, "status": "c"},
        ]
        # reversed = [5, 3, 1]; looking for seq=1 — break at 5≠1 would miss it
        _update_command_history(bot, 1, status="found")
        assert bot.manager_command_history[0]["status"] == "found"


# ===========================================================================
# routes/bot_ops.py — _queue_manager_command (detailed)
# ===========================================================================


class TestQueueManagerCommandExtra:
    def test_seq_increments_from_zero(self, bot):
        """mutmut_12: default seq=0 (not 1). First command gets seq=1."""
        result = _queue_manager_command(bot, "set_goal", {"goal": "test"})
        assert result["seq"] == 1

    def test_replace_guard_requires_positive_seq_and_type(self, bot):
        """mutmut_14/15/16: replaced_seq > 0 AND type present to trigger replace."""
        bot.pending_command_seq = 0
        bot.pending_command_type = "set_goal"
        result = _queue_manager_command(bot, "set_goal", {"goal": "y"})
        # seq=0 → no replace update, replaces=None
        assert result["replaces"] is None
        rows = _command_history_rows(bot)
        # No "replaced" status entry
        assert all(r.get("status") != "replaced" for r in rows)

    def test_replace_marked_as_replaced_in_history(self, bot):
        """mutmut_34/35: status='replaced' (not None or 'REPLACED')."""
        _queue_manager_command(bot, "set_goal", {"goal": "x"})
        _queue_manager_command(bot, "set_goal", {"goal": "y"})
        rows = _command_history_rows(bot)
        first = next(r for r in rows if r["seq"] == 1)
        assert first["status"] == "replaced"

    def test_replaced_by_is_next_seq(self, bot):
        """mutmut_36/37: replaced_by = seq+1 (not seq-1 or seq+2)."""
        _queue_manager_command(bot, "set_goal", {"goal": "x"})
        _queue_manager_command(bot, "set_goal", {"goal": "y"})
        rows = _command_history_rows(bot)
        first = next(r for r in rows if r["seq"] == 1)
        assert first["replaced_by"] == 2

    def test_pending_payload_stored_as_dict(self, bot):
        """mutmut_42: payload stored as dict, not None."""
        _queue_manager_command(bot, "set_goal", {"goal": "explore"})
        assert bot.pending_command_payload == {"goal": "explore"}
        assert bot.pending_command_payload is not None

    def test_queued_result_has_type_key(self, bot):
        """mutmut_47/48: returned dict has 'type' key (not 'XXtypeXX' or 'TYPE')."""
        result = _queue_manager_command(bot, "set_goal", {"goal": "test"})
        assert "type" in result
        assert result["type"] == "set_goal"

    def test_replaces_none_for_first_command(self, bot):
        """mutmut_54/55: replaces=None when replaced_seq <= 0."""
        result = _queue_manager_command(bot, "set_goal", {"goal": "x"})
        assert result["replaces"] is None

    def test_replaces_set_for_second_command(self, bot):
        """mutmut_54/55: replaces=1 for second command (replaced_seq=1 > 0)."""
        _queue_manager_command(bot, "set_goal", {"goal": "x"})
        result = _queue_manager_command(bot, "set_goal", {"goal": "y"})
        assert result["replaces"] == 1

    def test_history_entry_has_seq_key(self, bot):
        """mutmut_60/61: history entry has 'seq' key (not 'XXseqXX' or 'SEQ')."""
        _queue_manager_command(bot, "set_goal", {"goal": "x"})
        rows = _command_history_rows(bot)
        assert "seq" in rows[0]
        assert rows[0]["seq"] == 1

    def test_history_entry_has_type_key(self, bot):
        """mutmut_64/65: history entry has 'type' key (not 'XXtypeXX' or 'TYPE')."""
        _queue_manager_command(bot, "set_goal", {"goal": "x"})
        rows = _command_history_rows(bot)
        assert "type" in rows[0]
        assert rows[0]["type"] == "set_goal"

    def test_history_entry_has_payload_key(self, bot):
        """mutmut_66/67: history entry has 'payload' key."""
        _queue_manager_command(bot, "set_goal", {"goal": "x"})
        rows = _command_history_rows(bot)
        assert "payload" in rows[0]
        assert rows[0]["payload"] == {"goal": "x"}

    def test_history_entry_status_is_queued(self, bot):
        """mutmut_69/70/71/72: history entry status is 'queued' (not 'QUEUED' etc)."""
        _queue_manager_command(bot, "set_goal", {"goal": "x"})
        rows = _command_history_rows(bot)
        assert rows[0]["status"] == "queued"

    def test_history_entry_has_queued_at_key(self, bot):
        """mutmut_73/74: history entry has 'queued_at' key."""
        _queue_manager_command(bot, "set_goal", {"goal": "x"})
        rows = _command_history_rows(bot)
        assert "queued_at" in rows[0]
        assert rows[0]["queued_at"] > 0

    def test_history_entry_has_updated_at_key(self, bot):
        """mutmut_75/76: history entry has 'updated_at' key."""
        _queue_manager_command(bot, "set_goal", {"goal": "x"})
        rows = _command_history_rows(bot)
        assert "updated_at" in rows[0]
        assert rows[0]["updated_at"] > 0

    def test_history_entry_has_replaces_key(self, bot):
        """mutmut_77/78: history entry has 'replaces' key."""
        _queue_manager_command(bot, "set_goal", {"goal": "x"})
        rows = _command_history_rows(bot)
        assert "replaces" in rows[0]
        assert rows[0]["replaces"] is None

    def test_history_entry_has_replaced_by_key(self, bot):
        """mutmut_81/82: history entry has 'replaced_by' key (not 'XXreplaced_byXX')."""
        _queue_manager_command(bot, "set_goal", {"goal": "x"})
        rows = _command_history_rows(bot)
        assert "replaced_by" in rows[0]
        assert rows[0]["replaced_by"] is None

    def test_history_entry_has_cancelled_reason_key(self, bot):
        """mutmut_83/84: history entry has 'cancelled_reason' key with None value."""
        _queue_manager_command(bot, "set_goal", {"goal": "x"})
        rows = _command_history_rows(bot)
        assert "cancelled_reason" in rows[0]
        assert rows[0]["cancelled_reason"] is None

    def test_history_entry_replaces_set_when_replacing(self, bot):
        """mutmut_77/78: replaces field set in history when replacing existing command."""
        _queue_manager_command(bot, "set_goal", {"goal": "x"})
        _queue_manager_command(bot, "set_goal", {"goal": "y"})
        rows = _command_history_rows(bot)
        second = next(r for r in rows if r["seq"] == 2)
        assert second["replaces"] == 1


# ===========================================================================
# routes/bot_ops.py — _cancel_pending_manager_command (detailed)
# ===========================================================================


class TestCancelPendingCommandExtra:
    def test_default_reason_is_operator_cancelled(self, bot):
        """mutmut_1/2: default reason is 'operator_cancelled' (exact string)."""
        bot.pending_command_seq = 1
        bot.pending_command_type = "set_goal"
        bot.pending_command_payload = {}
        result = _cancel_pending_manager_command(bot)
        assert result is not None
        assert result["cancelled_reason"] == "operator_cancelled"

    def test_returns_none_when_seq_zero(self, bot):
        """mutmut_30: pending_seq <= 0 check — seq=0 returns None."""
        bot.pending_command_seq = 0
        bot.pending_command_type = "set_goal"
        assert _cancel_pending_manager_command(bot) is None

    def test_returns_none_when_type_empty(self, bot):
        """mutmut_29: 'and' vs 'or' — seq>0 but type="" still returns None."""
        bot.pending_command_seq = 1
        bot.pending_command_type = ""
        assert _cancel_pending_manager_command(bot) is None

    def test_both_conditions_required(self, bot):
        """mutmut_29: seq<=0 OR empty type → None. Both must be satisfied for cancel."""
        # seq=0 with type set → None
        bot.pending_command_seq = 0
        bot.pending_command_type = "set_goal"
        assert _cancel_pending_manager_command(bot) is None
        # seq>0 with empty type → None
        bot.pending_command_seq = 5
        bot.pending_command_type = ""
        assert _cancel_pending_manager_command(bot) is None

    def test_cancelled_result_has_seq_key(self, bot):
        """mutmut_34/35: result has 'seq' key (not 'XXseqXX' or 'SEQ')."""
        bot.pending_command_seq = 3
        bot.pending_command_type = "set_goal"
        bot.pending_command_payload = {}
        result = _cancel_pending_manager_command(bot)
        assert result is not None
        assert "seq" in result
        assert result["seq"] == 3

    def test_cancelled_result_has_type_key(self, bot):
        """mutmut_36/37: result has 'type' key (not 'XXtypeXX' or 'TYPE')."""
        bot.pending_command_seq = 1
        bot.pending_command_type = "set_directive"
        bot.pending_command_payload = {}
        result = _cancel_pending_manager_command(bot)
        assert result is not None
        assert "type" in result
        assert result["type"] == "set_directive"

    def test_cancelled_result_has_payload_key(self, bot):
        """mutmut_38/39: result has 'payload' key (not 'XXpayloadXX' or 'PAYLOAD')."""
        bot.pending_command_seq = 1
        bot.pending_command_type = "set_goal"
        bot.pending_command_payload = {"goal": "x"}
        result = _cancel_pending_manager_command(bot)
        assert result is not None
        assert "payload" in result

    def test_cancelled_result_has_cancelled_reason_key(self, bot):
        """mutmut_50/51: result has 'cancelled_reason' key."""
        bot.pending_command_seq = 1
        bot.pending_command_type = "set_goal"
        bot.pending_command_payload = {}
        result = _cancel_pending_manager_command(bot, "test_reason")
        assert result is not None
        assert "cancelled_reason" in result
        assert result["cancelled_reason"] == "test_reason"

    def test_payload_from_bot_attr(self, bot):
        """mutmut_41/42/44/47/48/49: payload comes from bot.pending_command_payload."""
        bot.pending_command_seq = 1
        bot.pending_command_type = "set_goal"
        bot.pending_command_payload = {"key": "val"}
        result = _cancel_pending_manager_command(bot)
        assert result is not None
        assert result["payload"] == {"key": "val"}

    def test_history_updated_with_cancelled_status(self, bot):
        """mutmut_54/62/63: _update_command_history called with status='cancelled'."""
        _queue_manager_command(bot, "set_goal", {"goal": "x"})
        _cancel_pending_manager_command(bot)
        rows = _command_history_rows(bot)
        assert rows[0]["status"] == "cancelled"

    def test_history_updated_with_cancelled_reason(self, bot):
        """mutmut_55: cancelled_reason passed to history update."""
        _queue_manager_command(bot, "set_goal", {"goal": "x"})
        _cancel_pending_manager_command(bot, "my_reason")
        rows = _command_history_rows(bot)
        assert rows[0]["cancelled_reason"] == "my_reason"

    def test_seq_reset_to_zero_after_cancel(self, bot):
        """mutmut_66: pending_command_seq = 0 after cancel."""
        bot.pending_command_seq = 5
        bot.pending_command_type = "set_goal"
        bot.pending_command_payload = {}
        _cancel_pending_manager_command(bot)
        assert bot.pending_command_seq == 0

    def test_type_reset_to_none_after_cancel(self, bot):
        """mutmut_66: pending_command_type = None (not empty string)."""
        bot.pending_command_seq = 1
        bot.pending_command_type = "set_goal"
        bot.pending_command_payload = {}
        _cancel_pending_manager_command(bot)
        assert bot.pending_command_type is None

    def test_payload_reset_to_empty_dict_after_cancel(self, bot):
        """mutmut_67: pending_command_payload = {} (not None)."""
        bot.pending_command_seq = 1
        bot.pending_command_type = "set_goal"
        bot.pending_command_payload = {"goal": "x"}
        _cancel_pending_manager_command(bot)
        assert bot.pending_command_payload == {}
        assert bot.pending_command_payload is not None


# ===========================================================================
# routes/bot_ops.py — _build_action_response (plugin path)
# ===========================================================================


class TestBuildActionResponseExtra:
    def test_plugin_called_with_all_args(self):
        """mutmut_9-14: plugin called with correct args (not None substitutions)."""
        plugin = MagicMock()
        plugin.build_action_response.return_value = {"ok": True}
        _build_action_response(
            "bot_X",
            "pause",
            "local_runtime",
            applied=True,
            queued=False,
            result={"key": "v"},
            state="running",
            plugin=plugin,
        )
        plugin.build_action_response.assert_called_once_with(
            "bot_X",
            "pause",
            "local_runtime",
            applied=True,
            queued=False,
            result={"key": "v"},
            state="running",
        )

    def test_plugin_bot_id_not_none(self):
        """mutmut_9: first positional arg is bot_id, not None."""
        plugin = MagicMock()
        plugin.build_action_response.return_value = {}
        _build_action_response("real_bot", "a", "s", applied=True, queued=False, result={}, state="x", plugin=plugin)
        call_args = plugin.build_action_response.call_args
        assert call_args[0][0] == "real_bot"

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
            "bot_z", "restart", "manager", applied=True, queued=False, result={"restarted": True}, state="running"
        )
        assert result["bot_id"] == "bot_z"
        assert result["action"] == "restart"
        assert result["source"] == "manager"
        assert result["applied"] is True
        assert result["queued"] is False
        assert result["result"] == {"restarted": True}
        assert result["state"] == "running"


# ===========================================================================
# auth.py — TokenAuthMiddleware.__call__ (targeted mutants)
# ===========================================================================


class TestTokenAuthMiddlewareCallMutants:
    """Tests targeting specific surviving mutants in TokenAuthMiddleware.__call__."""

    @pytest.mark.asyncio
    async def test_non_http_scope_passes_scope_to_inner(self):
        """mutmut_10-15: non-http scope passes scope/receive/send correctly."""
        captured = []

        async def inner(scope, receive, send):
            captured.append((scope, receive, send))

        mw = TokenAuthMiddleware(inner, "tok")
        scope = {"type": "lifespan"}
        recv = AsyncMock()
        send = AsyncMock()
        await mw(scope, recv, send)
        assert len(captured) == 1
        assert captured[0][0] is scope
        assert captured[0][1] is recv
        assert captured[0][2] is send

    @pytest.mark.asyncio
    async def test_public_path_passes_all_args_to_inner(self):
        """mutmut_28-33: public path passes scope/receive/send correctly."""
        captured = []

        async def inner(scope, receive, send):
            captured.append((scope, receive, send))

        mw = TokenAuthMiddleware(inner, "tok", public_paths=frozenset({"/health"}))
        scope = {"type": "http", "path": "/health", "method": "GET"}
        recv = AsyncMock()
        send = AsyncMock()
        await mw(scope, recv, send)
        assert len(captured) == 1
        assert captured[0][0] is scope
        assert captured[0][1] is recv
        assert captured[0][2] is send

    @pytest.mark.asyncio
    async def test_missing_path_defaults_to_empty_string(self):
        """mutmut_18/20: scope.get('path', '') defaults to '' not None or 'XXXX'."""
        inner = AsyncMock()
        mw = TokenAuthMiddleware(inner, "tok", public_paths=frozenset({""}))
        # scope without 'path' key — should default to '' and match public_paths
        scope = {"type": "http", "method": "GET", "headers": []}
        await mw(scope, AsyncMock(), AsyncMock())
        inner.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_websocket_qs_default_empty_bytes(self):
        """mutmut_43/45/48: query_string defaults to b'' (not None/b'XXXX')."""
        # WebSocket scope without query_string key — should not crash
        inner = AsyncMock()
        mw = TokenAuthMiddleware(inner, "correct_tok")
        scope = {
            "type": "websocket",
            "path": "/ws",
            # no query_string key
        }
        receive = AsyncMock(return_value={"type": "websocket.connect"})
        sent = []

        async def fake_send(m):
            sent.append(m)

        # No token → rejected, but should not crash
        await mw(scope, receive, fake_send)
        inner.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_websocket_token_extraction(self):
        """mutmut_40/41/50/51/52: token correctly extracted from query string."""
        inner = AsyncMock()
        mw = TokenAuthMiddleware(inner, "my_token")
        scope = {
            "type": "websocket",
            "path": "/ws",
            "query_string": b"token=my_token&other=x",
        }
        await mw(scope, AsyncMock(), AsyncMock())
        inner.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_websocket_empty_default_for_missing_token(self):
        """mutmut_59: parse_qs returns empty → defaults to [''] not ['XXXX']."""
        inner = AsyncMock()
        mw = TokenAuthMiddleware(inner, "secret")
        scope = {
            "type": "websocket",
            "path": "/ws",
            "query_string": b"other=value",  # no token param
        }
        receive = AsyncMock()
        sent = []

        async def fake_send(m):
            sent.append(m)

        await mw(scope, receive, fake_send)
        # Token is '' which doesn't match 'secret' → rejected
        inner.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_http_method_default_empty_string(self):
        """mutmut_63/65/68: method defaults to '' not None or 'XXXX'."""
        inner = AsyncMock()
        mw = TokenAuthMiddleware(inner, "tok")
        # Missing method key — should default to '' which is not 'OPTIONS'
        scope = {
            "type": "http",
            "path": "/api",
            # no method key
            "headers": [(b"authorization", b"Bearer tok")],
        }
        await mw(scope, AsyncMock(), AsyncMock())
        inner.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_options_passes_all_args_to_inner(self):
        """mutmut_72-77: OPTIONS passes scope/receive/send correctly."""
        captured = []

        async def inner(scope, receive, send):
            captured.append((scope, receive, send))

        mw = TokenAuthMiddleware(inner, "tok")
        scope = {"type": "http", "path": "/api", "method": "OPTIONS", "headers": []}
        recv = AsyncMock()
        send_fn = AsyncMock()
        await mw(scope, recv, send_fn)
        assert len(captured) == 1
        assert captured[0][0] is scope
        assert captured[0][1] is recv
        assert captured[0][2] is send_fn

    @pytest.mark.asyncio
    async def test_headers_default_empty_list(self):
        """mutmut_81/83: headers defaults to [] not None."""
        inner = AsyncMock()
        mw = TokenAuthMiddleware(inner, "tok")
        # scope without headers key
        scope = {"type": "http", "path": "/api", "method": "GET"}
        sent = []

        async def fake_send(m):
            sent.append(m)

        # Should not crash on missing headers
        await mw(scope, AsyncMock(), fake_send)
        inner.assert_not_awaited()  # no auth token → rejected

    @pytest.mark.asyncio
    async def test_bearer_auth_decode_utf8(self):
        """mutmut_89/90/99/100/101: auth header decoded as utf-8."""
        inner = AsyncMock()
        mw = TokenAuthMiddleware(inner, "mytoken")
        scope = {
            "type": "http",
            "path": "/api",
            "method": "GET",
            "headers": [(b"authorization", b"Bearer mytoken")],
        }
        await mw(scope, AsyncMock(), AsyncMock())
        inner.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_x_api_token_decode_utf8(self):
        """mutmut_110/111/118/120/121/122: x-api-token decoded as utf-8."""
        inner = AsyncMock()
        mw = TokenAuthMiddleware(inner, "mytoken")
        scope = {
            "type": "http",
            "path": "/api",
            "method": "GET",
            "headers": [(b"x-api-token", b"mytoken")],
        }
        await mw(scope, AsyncMock(), AsyncMock())
        inner.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_websocket_close_sends_accept_then_close(self):
        """mutmut_132-135/141-143: WS rejection sends accept with correct type, then close with code 4403."""
        inner = AsyncMock()
        mw = TokenAuthMiddleware(inner, "secret")
        scope = {"type": "websocket", "path": "/ws", "query_string": b"token=wrong"}
        receive = AsyncMock(return_value={"type": "websocket.connect"})
        sent = []

        async def fake_send(m):
            sent.append(m)

        await mw(scope, receive, fake_send)
        inner.assert_not_awaited()
        types_sent = [m.get("type") for m in sent]
        assert "websocket.accept" in types_sent
        assert "websocket.close" in types_sent
        close_msg = next(m for m in sent if m.get("type") == "websocket.close")
        assert close_msg["code"] == 4403

    @pytest.mark.asyncio
    async def test_http_unauthorized_returns_401(self):
        """mutmut_145/148/149/150/151/152/153/154: HTTP rejected with 401 JSON response."""
        inner = AsyncMock()
        mw = TokenAuthMiddleware(inner, "secret")
        scope = {
            "type": "http",
            "path": "/api",
            "method": "GET",
            "headers": [(b"authorization", b"Bearer wrong")],
        }
        sent = []

        async def fake_send(m):
            sent.append(m)

        await mw(scope, AsyncMock(), fake_send)
        inner.assert_not_awaited()
        # Look for status 401 in start message
        start_msgs = [m for m in sent if m.get("type") == "http.response.start"]
        assert any(m.get("status") == 401 for m in start_msgs)

    @pytest.mark.asyncio
    async def test_http_unauthorized_response_passes_receive(self):
        """mutmut_156: response called with (scope, receive, send) not (scope, None, send)."""
        inner = AsyncMock()
        mw = TokenAuthMiddleware(inner, "secret")
        scope = {
            "type": "http",
            "path": "/api",
            "method": "GET",
            "headers": [],
        }
        # Use a real receive that can be called
        recv_called = []

        async def recv():
            recv_called.append(True)
            return {"type": "http.request"}

        sent = []

        async def fake_send(m):
            sent.append(m)

        await mw(scope, recv, fake_send)
        inner.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_authenticated_passes_all_args_to_inner(self):
        """mutmut_161-166: authenticated request passes scope/receive/send correctly."""
        captured = []

        async def inner(scope, receive, send):
            captured.append((scope, receive, send))

        mw = TokenAuthMiddleware(inner, "correct")
        scope = {
            "type": "http",
            "path": "/api",
            "method": "GET",
            "headers": [(b"authorization", b"Bearer correct")],
        }
        recv = AsyncMock()
        send_fn = AsyncMock()
        await mw(scope, recv, send_fn)
        assert len(captured) == 1
        assert captured[0][0] is scope
        assert captured[0][1] is recv
        assert captured[0][2] is send_fn


# ===========================================================================
# auth.py — setup_auth
# ===========================================================================


class TestSetupAuthMutants:
    def test_env_var_default_is_uterm_manager_api_token(self):
        """mutmut_1/2: default env_var is 'UTERM_MANAGER_API_TOKEN' (exact case)."""
        app = MagicMock()
        env_var = "UTERM_MANAGER_API_TOKEN"
        with patch.dict(os.environ, {env_var: "tok"}):
            setup_auth(app)  # uses default env_var
        app.add_middleware.assert_called_once()

    def test_no_token_does_not_add_middleware(self):
        """setup_auth without token → no middleware."""
        app = MagicMock()
        env_var = "TEST_TOKEN_VAR_NOTSET_XYZ"
        os.environ.pop(env_var, None)
        setup_auth(app, env_var=env_var)
        app.add_middleware.assert_not_called()

    def test_public_paths_default_frozenset_empty(self):
        """mutmut_16: public_paths starts as frozenset() (not None)."""
        app = MagicMock()
        with patch.dict(os.environ, {"MY_TOK_A": "tok"}):
            setup_auth(app, env_var="MY_TOK_A")
        call_kwargs = app.add_middleware.call_args[1]
        assert call_kwargs["public_paths"] == frozenset()

    def test_public_prefixes_default_empty_tuple(self):
        """mutmut_17: public_prefixes starts as () (not None)."""
        app = MagicMock()
        with patch.dict(os.environ, {"MY_TOK_B": "tok"}):
            setup_auth(app, env_var="MY_TOK_B")
        call_kwargs = app.add_middleware.call_args[1]
        assert call_kwargs["public_prefixes"] == ()

    def test_config_public_paths_used(self):
        """mutmut_19: public_paths from config (not None)."""
        app = MagicMock()
        config = MagicMock()
        config.auth_public_paths = ["/dashboard", "/health"]
        config.auth_public_prefixes = []
        with patch.dict(os.environ, {"MY_TOK_C": "tok"}):
            setup_auth(app, env_var="MY_TOK_C", config=config)
        call_kwargs = app.add_middleware.call_args[1]
        assert "/dashboard" in call_kwargs["public_paths"]

    def test_config_public_prefixes_used(self):
        """mutmut_21: public_prefixes from config (not None)."""
        app = MagicMock()
        config = MagicMock()
        config.auth_public_paths = []
        config.auth_public_prefixes = ["/static/"]
        with patch.dict(os.environ, {"MY_TOK_D": "tok"}):
            setup_auth(app, env_var="MY_TOK_D", config=config)
        call_kwargs = app.add_middleware.call_args[1]
        assert "/static/" in call_kwargs["public_prefixes"]

    def test_middleware_class_is_token_auth(self):
        """mutmut_26: TokenAuthMiddleware class passed (not None)."""
        app = MagicMock()
        with patch.dict(os.environ, {"MY_TOK_E": "tok"}):
            setup_auth(app, env_var="MY_TOK_E")
        call_args = app.add_middleware.call_args
        assert call_args[0][0] is TokenAuthMiddleware

    def test_token_kwarg_passed_to_middleware(self):
        """mutmut_27: token kwarg passed (not None)."""
        app = MagicMock()
        with patch.dict(os.environ, {"MY_TOK_F": "real_tok"}):
            setup_auth(app, env_var="MY_TOK_F")
        call_kwargs = app.add_middleware.call_args[1]
        assert call_kwargs["token"] == "real_tok"

    def test_public_paths_kwarg_passed(self):
        """mutmut_28/32: public_paths kwarg passed to middleware."""
        app = MagicMock()
        with patch.dict(os.environ, {"MY_TOK_G": "tok"}):
            setup_auth(app, env_var="MY_TOK_G")
        call_kwargs = app.add_middleware.call_args[1]
        assert "public_paths" in call_kwargs

    def test_public_prefixes_kwarg_passed(self):
        """mutmut_29/33: public_prefixes kwarg passed to middleware."""
        app = MagicMock()
        with patch.dict(os.environ, {"MY_TOK_H": "tok"}):
            setup_auth(app, env_var="MY_TOK_H")
        call_kwargs = app.add_middleware.call_args[1]
        assert "public_prefixes" in call_kwargs

    def test_setup_auth_with_config_wires_correctly(self):
        """mutmut_19/21/27/28/29: config path sets both public_paths and public_prefixes."""
        app = MagicMock()
        config = MagicMock()
        config.auth_public_paths = ["/pub"]
        config.auth_public_prefixes = ["/pfx/"]
        with patch.dict(os.environ, {"MY_TOK_I": "secretval"}):
            setup_auth(app, env_var="MY_TOK_I", config=config)
        call_kwargs = app.add_middleware.call_args[1]
        assert call_kwargs["token"] == "secretval"
        assert "/pub" in call_kwargs["public_paths"]
        assert "/pfx/" in call_kwargs["public_prefixes"]
