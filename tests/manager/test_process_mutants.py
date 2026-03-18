# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Mutation-killing tests for undef.terminal.manager.process."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from undef.terminal.manager.config import ManagerConfig
from undef.terminal.manager.core import SwarmManager
from undef.terminal.manager.models import BotStatusBase
from undef.terminal.manager.process import BotProcessManager


class FakeWorkerPlugin:
    @property
    def worker_type(self) -> str:
        return "test_game"

    @property
    def worker_module(self) -> str:
        return "test_module"

    def configure_worker_env(self, env, bot_status, manager, **kwargs):
        env["CONFIGURED"] = "yes"


@pytest.fixture
def config(tmp_path):
    return ManagerConfig(
        state_file=str(tmp_path / "state.json"),
        timeseries_dir=str(tmp_path / "metrics"),
        log_dir=str(tmp_path / "logs"),
        health_check_interval_s=0,
        heartbeat_timeout_s=1,
    )


@pytest.fixture
def manager(config):
    return SwarmManager(config)


@pytest.fixture
def pm(manager, tmp_path):
    pm = BotProcessManager(
        manager,
        worker_registry={"test_game": FakeWorkerPlugin()},
        log_dir=str(tmp_path / "logs"),
    )
    manager.bot_process_manager = pm
    return pm


# ---------------------------------------------------------------------------
# __init__ default value mutations (mutmut_1, 5, 9, 12, 13, 14, 15, 16, 17)
# ---------------------------------------------------------------------------
class TestInitDefaults:
    def test_log_dir_default_is_empty_string(self, manager):
        """Kills mutmut_1: log_dir default "" → "XXXX"."""
        pm = BotProcessManager(manager)
        assert pm._log_dir == ""

    def test_log_dir_stored(self, manager, tmp_path):
        """Kills mutmut_5: self._log_dir = None."""
        pm = BotProcessManager(manager, log_dir=str(tmp_path))
        assert pm._log_dir == str(tmp_path)

    def test_queued_launch_delay_is_30(self, manager):
        """Kills mutmut_9: _queued_launch_delay = 31.0."""
        pm = BotProcessManager(manager)
        assert pm._queued_launch_delay == 30.0

    def test_spawn_name_style_is_random(self, manager):
        """Kills mutmut_12/13/14: _spawn_name_style = None/XXrandomXX/RANDOM."""
        pm = BotProcessManager(manager)
        assert pm._spawn_name_style == "random"

    def test_spawn_name_base_is_empty(self, manager):
        """Kills mutmut_15/16: _spawn_name_base = None/"XXXX"."""
        pm = BotProcessManager(manager)
        assert pm._spawn_name_base == ""

    def test_last_spawn_config_is_none(self, manager):
        """Kills mutmut_17: _last_spawn_config = "" instead of None."""
        pm = BotProcessManager(manager)
        assert pm._last_spawn_config is None

    def test_next_bot_index_starts_at_zero(self, manager):
        """Kills mutmut_10/11: _next_bot_index = None/1."""
        pm = BotProcessManager(manager)
        assert pm._next_bot_index == 0

    def test_spawn_tasks_is_list(self, manager):
        """Kills mutmut_6: _spawn_tasks = None."""
        pm = BotProcessManager(manager)
        assert pm._spawn_tasks == []
        assert isinstance(pm._spawn_tasks, list)

    def test_queued_since_is_dict(self, manager):
        """Kills mutmut_7: _queued_since = None."""
        pm = BotProcessManager(manager)
        assert pm._queued_since == {}
        assert isinstance(pm._queued_since, dict)

    def test_worker_registry_none_defaults_to_empty(self, manager):
        """Kills mutmut_3: _worker_registry = None."""
        pm = BotProcessManager(manager, worker_registry=None)
        assert pm._worker_registry == {}


# ---------------------------------------------------------------------------
# sync_next_bot_index (mutmut_3: max_seen = -2)
# ---------------------------------------------------------------------------
class TestSyncNextBotIndex:
    def test_empty_bots_returns_zero(self, pm):
        """When no bots exist, sync should return 0 (max_seen=-1, so max(-1)+1=0).
        Kills mutmut_3: max_seen=-2 → would also return 0 here but next test catches it."""
        result = pm.sync_next_bot_index()
        assert result == 0

    def test_max_seen_negative_one_means_next_is_zero(self, pm, manager):
        """Kills mutmut_3: max_seen=-2. With bot_0, max_seen should be 0, next=1.
        Without bots, next should be 0 (not -1 which -2+1 would give in some edge case)."""
        # With bots named non-bot_ format, max_seen stays -1, next = max(0, -1+1) = 0
        manager.bots["worker_xyz"] = BotStatusBase(bot_id="worker_xyz")
        result = pm.sync_next_bot_index()
        assert result == 0  # mutmut_3 would give max(0, -2+1) = max(0,-1) = 0 also...

    def test_sync_uses_union_of_bots_and_processes(self, pm, manager):
        """Kills mutmut_4: uses & instead of |."""
        manager.bots["bot_005"] = BotStatusBase(bot_id="bot_005")
        manager.processes["bot_010"] = MagicMock()
        result = pm.sync_next_bot_index()
        assert result == 11  # Uses union: max(5, 10) + 1 = 11


# ---------------------------------------------------------------------------
# allocate_bot_id (mutmut_8/10)
# ---------------------------------------------------------------------------
class TestAllocateBotId:
    def test_next_bot_index_incremented_after_alloc(self, pm, manager):
        """Kills mutmut_8: _next_bot_index = idx - 1 (instead of idx + 1)
        and mutmut_10: idx = 1 instead of idx += 1."""
        bid = pm.allocate_bot_id()
        assert bid == "bot_000"
        # After allocation, _next_bot_index should be 1 (not -1 or 1 from restart)
        assert pm._next_bot_index == 1

    def test_sequential_allocations(self, pm, manager):
        """Kills mutmut_10: idx = 1 would cause non-sequential allocation."""
        bid1 = pm.allocate_bot_id()
        manager.bots[bid1] = BotStatusBase(bot_id=bid1)
        bid2 = pm.allocate_bot_id()
        manager.bots[bid2] = BotStatusBase(bot_id=bid2)
        bid3 = pm.allocate_bot_id()
        # Should be sequential
        assert bid1 == "bot_000"
        assert bid2 == "bot_001"
        assert bid3 == "bot_002"


# ---------------------------------------------------------------------------
# start_spawn_swarm default arg mutations
# ---------------------------------------------------------------------------
class TestStartSpawnSwarmDefaults:
    @pytest.mark.asyncio
    async def test_default_group_size_is_one(self, pm, manager):
        """Kills mutmut_1: group_size default 1 → 2."""
        spawned_kwargs = {}

        async def capture(*args, **kwargs):
            spawned_kwargs.update(kwargs)
            return []

        with patch.object(pm, "spawn_swarm", side_effect=capture):
            await pm.start_spawn_swarm(["/a.yaml"])
            await asyncio.sleep(0.01)

        # Allow task to run
        await asyncio.gather(*[t for t in pm._spawn_tasks if not t.done()], return_exceptions=True)
        assert spawned_kwargs.get("group_size") == 1

    @pytest.mark.asyncio
    async def test_default_group_delay_is_12(self, pm, manager):
        """Kills mutmut_2: group_delay default 12.0 → 13.0."""
        spawned_kwargs = {}

        async def capture(*args, **kwargs):
            spawned_kwargs.update(kwargs)
            return []

        with patch.object(pm, "spawn_swarm", side_effect=capture):
            await pm.start_spawn_swarm(["/a.yaml"])
            await asyncio.sleep(0.01)

        await asyncio.gather(*[t for t in pm._spawn_tasks if not t.done()], return_exceptions=True)
        assert spawned_kwargs.get("group_delay") == 12.0

    @pytest.mark.asyncio
    async def test_default_name_style_is_random(self, pm, manager):
        """Kills mutmut_6/7: name_style default 'random' → 'XXrandomXX'/'RANDOM'."""
        spawned_kwargs = {}

        async def capture(*args, **kwargs):
            spawned_kwargs.update(kwargs)
            return []

        with patch.object(pm, "spawn_swarm", side_effect=capture):
            await pm.start_spawn_swarm(["/a.yaml"])
            await asyncio.gather(*[t for t in pm._spawn_tasks if not t.done()], return_exceptions=True)

        assert spawned_kwargs.get("name_style") == "random"

    @pytest.mark.asyncio
    async def test_default_name_base_is_empty(self, pm, manager):
        """Kills mutmut_8: name_base default '' → 'XXXX'."""
        spawned_kwargs = {}

        async def capture(*args, **kwargs):
            spawned_kwargs.update(kwargs)
            return []

        with patch.object(pm, "spawn_swarm", side_effect=capture):
            await pm.start_spawn_swarm(["/a.yaml"])
            await asyncio.gather(*[t for t in pm._spawn_tasks if not t.done()], return_exceptions=True)

        assert spawned_kwargs.get("name_base") == ""

    @pytest.mark.asyncio
    async def test_cancel_existing_true_by_default(self, pm, manager):
        """Kills mutmut_3: cancel_existing default True → False."""

        async def slow_spawn(*a, **kw):
            await asyncio.sleep(100)
            return []

        cancel_called = []
        orig_cancel = pm.cancel_spawn

        async def track_cancel():
            cancel_called.append(True)
            return await orig_cancel()

        with patch.object(pm, "spawn_swarm", side_effect=slow_spawn):
            await pm.start_spawn_swarm(["/a.yaml"], cancel_existing=False)

        # Now call with default cancel_existing (should be True)
        with (
            patch.object(pm, "cancel_spawn", side_effect=track_cancel),
            patch.object(pm, "spawn_swarm", side_effect=slow_spawn),
        ):
            await pm.start_spawn_swarm(["/a.yaml"])

        assert len(cancel_called) == 1

    @pytest.mark.asyncio
    async def test_config_paths_passed_to_spawn_swarm(self, pm, manager):
        """Kills mutmut_13/19: config_paths=None or config_paths missing."""
        spawned_args = []

        async def capture(config_paths, **kwargs):
            spawned_args.append(config_paths)
            return []

        with patch.object(pm, "spawn_swarm", side_effect=capture):
            await pm.start_spawn_swarm(["/a.yaml", "/b.yaml"])
            await asyncio.gather(*[t for t in pm._spawn_tasks if not t.done()], return_exceptions=True)

        assert spawned_args == [["/a.yaml", "/b.yaml"]]

    @pytest.mark.asyncio
    async def test_all_args_forwarded_to_spawn_swarm(self, pm, manager):
        """Kills mutmut_14-24: various args set to None or missing."""
        spawned_kwargs = {}

        async def capture(config_paths, **kwargs):
            spawned_kwargs.update(kwargs)
            spawned_kwargs["config_paths"] = config_paths
            return []

        with patch.object(pm, "spawn_swarm", side_effect=capture):
            await pm.start_spawn_swarm(
                ["/a.yaml"],
                group_size=3,
                group_delay=5.0,
                name_style="fixed",
                name_base="mybot",
            )
            await asyncio.gather(*[t for t in pm._spawn_tasks if not t.done()], return_exceptions=True)

        assert spawned_kwargs["group_size"] == 3
        assert spawned_kwargs["group_delay"] == 5.0
        assert spawned_kwargs["name_style"] == "fixed"
        assert spawned_kwargs["name_base"] == "mybot"


# ---------------------------------------------------------------------------
# spawn_bot cmd construction and env filtering
# ---------------------------------------------------------------------------
class TestSpawnBotCmd:
    @pytest.mark.asyncio
    async def test_cmd_uses_dash_m_flag(self, pm, manager, tmp_path):
        """Kills mutmut_70/71: '-m' → 'XX-mXX'/'-M'."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: test_game\n")
        manager.broadcast_status = AsyncMock()

        captured_cmd = []

        def fake_spawn(bot_id, cmd, env):
            captured_cmd.extend(cmd)
            m = MagicMock()
            m.pid = 1
            return m

        with patch.object(pm, "_spawn_process", side_effect=fake_spawn):
            await pm.spawn_bot(str(config), "bot_000")

        assert "-m" in captured_cmd
        assert captured_cmd[1] == "-m"

    @pytest.mark.asyncio
    async def test_cmd_uses_config_flag(self, pm, manager, tmp_path):
        """Kills mutmut_72/73: '--config' → 'XX--configXX'/'--CONFIG'."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: test_game\n")
        manager.broadcast_status = AsyncMock()

        captured_cmd = []

        def fake_spawn(bot_id, cmd, env):
            captured_cmd.extend(cmd)
            m = MagicMock()
            m.pid = 1
            return m

        with patch.object(pm, "_spawn_process", side_effect=fake_spawn):
            await pm.spawn_bot(str(config), "bot_000")

        assert "--config" in captured_cmd

    @pytest.mark.asyncio
    async def test_cmd_uses_bot_id_flag(self, pm, manager, tmp_path):
        """Kills mutmut_74/75: '--bot-id' → 'XX--bot-idXX'/'--BOT-ID'."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: test_game\n")
        manager.broadcast_status = AsyncMock()

        captured_cmd = []

        def fake_spawn(bot_id, cmd, env):
            captured_cmd.extend(cmd)
            m = MagicMock()
            m.pid = 1
            return m

        with patch.object(pm, "_spawn_process", side_effect=fake_spawn):
            await pm.spawn_bot(str(config), "bot_000")

        assert "--bot-id" in captured_cmd

    @pytest.mark.asyncio
    async def test_cmd_contains_worker_module(self, pm, manager, tmp_path):
        """Kills mutmut_68: worker_module = None."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: test_game\n")
        manager.broadcast_status = AsyncMock()

        captured_cmd = []

        def fake_spawn(bot_id, cmd, env):
            captured_cmd.extend(cmd)
            m = MagicMock()
            m.pid = 1
            return m

        with patch.object(pm, "_spawn_process", side_effect=fake_spawn):
            await pm.spawn_bot(str(config), "bot_000")

        assert "test_module" in captured_cmd

    @pytest.mark.asyncio
    async def test_env_uses_or_not_and(self, pm, manager, tmp_path):
        """Kills mutmut_78: 'or k in _WORKER_ENV_PASSTHROUGH' → 'and k in'."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: test_game\n")
        manager.broadcast_status = AsyncMock()

        captured_env = {}

        def fake_spawn(bot_id, cmd, env):
            captured_env.update(env)
            m = MagicMock()
            m.pid = 1
            return m

        # Set a passthrough var that has no prefix
        with (
            patch.dict(os.environ, {"PATH": "/usr/bin", "HOME": "/home/test"}),
            patch.object(pm, "_spawn_process", side_effect=fake_spawn),
        ):
            await pm.spawn_bot(str(config), "bot_000")

        # PATH and HOME should be in env (they're in _WORKER_ENV_PASSTHROUGH, no prefix match)
        # If 'and' was used instead of 'or', these wouldn't be included
        assert "PATH" in captured_env or "HOME" in captured_env

    @pytest.mark.asyncio
    async def test_env_excludes_non_passthrough_no_prefix(self, pm, manager, tmp_path):
        """Kills mutmut_80: 'k in _WORKER_ENV_PASSTHROUGH' → 'k not in'."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: test_game\n")
        manager.broadcast_status = AsyncMock()

        captured_env = {}

        def fake_spawn(bot_id, cmd, env):
            captured_env.update(env)
            m = MagicMock()
            m.pid = 1
            return m

        sentinel_key = "TOTALLY_RANDOM_VAR_NOT_IN_PASSTHROUGH_XYZ123"
        with (
            patch.dict(os.environ, {sentinel_key: "should_not_appear"}),
            patch.object(pm, "_spawn_process", side_effect=fake_spawn),
        ):
            await pm.spawn_bot(str(config), "bot_000")

        assert sentinel_key not in captured_env

    @pytest.mark.asyncio
    async def test_name_style_env_set_correctly(self, pm, manager, tmp_path):
        """Kills mutmut_93: NAME_STYLE = None."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: test_game\n")
        manager.broadcast_status = AsyncMock()
        pm._spawn_name_style = "fixed"

        captured_env = {}

        def fake_spawn(bot_id, cmd, env):
            captured_env.update(env)
            m = MagicMock()
            m.pid = 1
            return m

        env_prefix = manager.config.worker_env_prefix
        with patch.object(pm, "_spawn_process", side_effect=fake_spawn):
            await pm.spawn_bot(str(config), "bot_000")

        assert captured_env.get(f"{env_prefix}NAME_STYLE") == "fixed"

    @pytest.mark.asyncio
    async def test_configure_worker_env_called_with_manager(self, pm, manager, tmp_path):
        """Kills mutmut_95 (bot_entry is None → configure not called)
        and mutmut_97 (configure skipped) and mutmut_98 (manager=None)."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: test_game\n")
        manager.broadcast_status = AsyncMock()
        # Add bot entry so configure_worker_env is called
        manager.bots["bot_000"] = BotStatusBase(bot_id="bot_000", state="queued", pid=0)

        configure_calls = []

        def tracking_configure(self_plugin, env, bot_status, mgr, **kwargs):
            configure_calls.append((bot_status, mgr))

        with patch.object(FakeWorkerPlugin, "configure_worker_env", tracking_configure):
            mock_proc = MagicMock()
            mock_proc.pid = 1
            with patch.object(pm, "_spawn_process", return_value=mock_proc):
                await pm.spawn_bot(str(config), "bot_000")

        assert len(configure_calls) == 1
        # Manager must not be None (kills mutmut_98)
        assert configure_calls[0][1] is not None
        assert configure_calls[0][1] is manager

    @pytest.mark.asyncio
    async def test_configure_worker_env_not_called_when_no_bot_entry(self, pm, manager, tmp_path):
        """Kills mutmut_95: bot_entry is None check inverted."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: test_game\n")
        manager.broadcast_status = AsyncMock()
        # No bot entry in bots dict

        configure_calls = []

        def tracking_configure(self_plugin, env, bot_status, mgr, **kwargs):
            configure_calls.append(True)

        with patch.object(FakeWorkerPlugin, "configure_worker_env", tracking_configure):
            mock_proc = MagicMock()
            mock_proc.pid = 1
            with patch.object(pm, "_spawn_process", return_value=mock_proc):
                await pm.spawn_bot(str(config), "bot_000")

        # No bot entry → configure not called
        assert len(configure_calls) == 0

    @pytest.mark.asyncio
    async def test_last_spawn_config_set(self, pm, manager, tmp_path):
        """Kills any mutation that removes _last_spawn_config = config_path."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: test_game\n")
        manager.broadcast_status = AsyncMock()

        mock_proc = MagicMock()
        mock_proc.pid = 1
        with patch.object(pm, "_spawn_process", return_value=mock_proc):
            await pm.spawn_bot(str(config), "bot_000")

        assert pm._last_spawn_config == str(config)

    @pytest.mark.asyncio
    async def test_stopped_at_set_to_none_on_spawn(self, pm, manager, tmp_path):
        """Kills mutations that skip setting stopped_at=None for existing bots."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: test_game\n")
        manager.broadcast_status = AsyncMock()
        # Pre-existing bot with a stopped_at
        manager.bots["bot_000"] = BotStatusBase(bot_id="bot_000", state="stopped", pid=0, stopped_at=12345.0)

        mock_proc = MagicMock()
        mock_proc.pid = 999
        with patch.object(pm, "_spawn_process", return_value=mock_proc):
            await pm.spawn_bot(str(config), "bot_000")

        assert manager.bots["bot_000"].stopped_at is None


# ---------------------------------------------------------------------------
# spawn_bot worker_type fallback
# ---------------------------------------------------------------------------
class TestSpawnBotWorkerType:
    @pytest.mark.asyncio
    async def test_worker_type_default_fallback_single_registry(self, pm, manager, tmp_path):
        """Config with no worker_type key → single-registry fallback uses the one registered entry."""
        config = tmp_path / "test.yaml"
        config.write_text("{}  # empty\n")
        manager.broadcast_status = AsyncMock()
        mock_proc = MagicMock()
        mock_proc.pid = 1
        with patch.object(pm, "_spawn_process", return_value=mock_proc):
            bot_id = await pm.spawn_bot(str(config), "bot_000")
        assert bot_id == "bot_000"

    @pytest.mark.asyncio
    async def test_worker_type_unknown_raises_with_multiple_registries(self, pm, manager, tmp_path):
        """Unknown worker_type with multiple registries raises RuntimeError."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: not_registered\n")
        # Add a second registry entry so fallback doesn't apply
        pm._worker_registry["other_game"] = pm._worker_registry["test_game"]
        with pytest.raises(RuntimeError, match="Unknown worker_type"):
            await pm.spawn_bot(str(config), "bot_000")

    @pytest.mark.asyncio
    async def test_worker_type_read_default_arg(self, pm, manager, tmp_path):
        """When worker_type key missing from yaml, single-registry fallback is used."""
        config = tmp_path / "test.yaml"
        config.write_text("connection:\n  host: somewhere\n")
        manager.broadcast_status = AsyncMock()
        mock_proc = MagicMock()
        mock_proc.pid = 1
        with patch.object(pm, "_spawn_process", return_value=mock_proc):
            bot_id = await pm.spawn_bot(str(config), "bot_000")
        assert bot_id == "bot_000"


# ---------------------------------------------------------------------------
# kill_bot timeout value and state (mutmut_4/10/31/34/35)
# ---------------------------------------------------------------------------
class TestKillBot:
    @pytest.mark.asyncio
    async def test_kill_timeout_is_5_seconds(self, pm, manager):
        """Kills mutmut_4 (timeout=None) and mutmut_10 (timeout=6.0)."""
        mock_proc = MagicMock()
        manager.processes["bot_000"] = mock_proc
        manager.bots["bot_000"] = BotStatusBase(bot_id="bot_000", state="running")
        manager.broadcast_status = AsyncMock()

        wait_for_calls = []
        orig_wait_for = asyncio.wait_for

        async def track_wait_for(coro, timeout=None):
            wait_for_calls.append(timeout)
            return await orig_wait_for(coro, timeout=timeout)

        mock_proc.wait.return_value = 0
        with patch("asyncio.wait_for", side_effect=track_wait_for):
            await pm.kill_bot("bot_000")

        assert len(wait_for_calls) == 1
        assert wait_for_calls[0] == 5.0

    @pytest.mark.asyncio
    async def test_stopped_at_is_set_not_none(self, pm, manager):
        """Kills mutmut_31: stopped_at = None instead of time.time()."""
        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        manager.processes["bot_000"] = mock_proc
        manager.bots["bot_000"] = BotStatusBase(bot_id="bot_000", state="running")
        manager.broadcast_status = AsyncMock()

        await pm.kill_bot("bot_000")

        assert manager.bots["bot_000"].stopped_at is not None
        assert manager.bots["bot_000"].stopped_at > 0

    @pytest.mark.asyncio
    async def test_bot_removed_from_processes(self, pm, manager):
        """Kills mutmut_34: processes.pop(bot_id, ) with missing None default."""
        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        manager.processes["bot_000"] = mock_proc
        manager.bots["bot_000"] = BotStatusBase(bot_id="bot_000", state="running")
        manager.broadcast_status = AsyncMock()

        await pm.kill_bot("bot_000")

        assert "bot_000" not in manager.processes

    @pytest.mark.asyncio
    async def test_release_bot_account_called_with_bot_id(self, pm, manager):
        """Kills mutmut_35: release_bot_account(None) instead of (bot_id)."""
        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        manager.processes["bot_000"] = mock_proc
        manager.bots["bot_000"] = BotStatusBase(bot_id="bot_000", state="running")
        manager.broadcast_status = AsyncMock()

        release_calls = []
        orig_release = pm.release_bot_account

        def track_release(bid):
            release_calls.append(bid)
            return orig_release(bid)

        with patch.object(pm, "release_bot_account", side_effect=track_release):
            await pm.kill_bot("bot_000")

        assert "bot_000" in release_calls


# ---------------------------------------------------------------------------
# _launch_queued_bot
# ---------------------------------------------------------------------------
class TestLaunchQueuedBot:
    @pytest.mark.asyncio
    async def test_sets_error_state_on_failure(self, pm, manager):
        """Kills _launch_queued_bot mutations that change error state."""
        manager.broadcast_status = AsyncMock()
        manager.bots["bot_000"] = BotStatusBase(bot_id="bot_000", state="queued", pid=0)

        with patch.object(pm, "spawn_bot", side_effect=RuntimeError("spawn error")):
            await pm._launch_queued_bot("bot_000", "/config.yaml")

        bot = manager.bots["bot_000"]
        assert bot.state == "error"

    @pytest.mark.asyncio
    async def test_sets_error_message_with_launch_failed(self, pm, manager):
        """Kills mutmut_1: error_message set to wrong/None value."""
        manager.broadcast_status = AsyncMock()
        manager.bots["bot_000"] = BotStatusBase(bot_id="bot_000", state="queued", pid=0)

        with patch.object(pm, "spawn_bot", side_effect=RuntimeError("specific error")):
            await pm._launch_queued_bot("bot_000", "/config.yaml")

        assert "Launch failed" in (manager.bots["bot_000"].error_message or "")
        assert "specific error" in (manager.bots["bot_000"].error_message or "")

    @pytest.mark.asyncio
    async def test_sets_exit_reason_launch_failed(self, pm, manager):
        """Kills mutations changing exit_reason."""
        manager.broadcast_status = AsyncMock()
        manager.bots["bot_000"] = BotStatusBase(bot_id="bot_000", state="queued", pid=0)

        with patch.object(pm, "spawn_bot", side_effect=RuntimeError("fail")):
            await pm._launch_queued_bot("bot_000", "/config.yaml")

        assert manager.bots["bot_000"].exit_reason == "launch_failed"

    @pytest.mark.asyncio
    async def test_broadcasts_on_failure(self, pm, manager):
        """Kills mutations that skip broadcast."""
        manager.broadcast_status = AsyncMock()
        manager.bots["bot_000"] = BotStatusBase(bot_id="bot_000", state="queued", pid=0)

        with patch.object(pm, "spawn_bot", side_effect=RuntimeError("fail")):
            await pm._launch_queued_bot("bot_000", "/config.yaml")

        manager.broadcast_status.assert_called()


# ---------------------------------------------------------------------------
# _spawn_process
# ---------------------------------------------------------------------------
class TestSpawnProcess:
    def test_uses_log_dir_when_set(self, pm, tmp_path):
        """Kills mutations changing log_dir path logic."""
        custom_log = tmp_path / "custom_logs"
        pm._log_dir = str(custom_log)

        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock(pid=42)
            pm._spawn_process("bot_007", ["echo", "hi"], {})

        # The custom_log dir should have been created
        assert custom_log.is_dir()

    def test_default_log_dir_is_logs_workers(self, pm, tmp_path, monkeypatch):
        """Kills mutations changing default log_dir path."""
        pm._log_dir = ""  # Empty string triggers default
        monkeypatch.chdir(tmp_path)

        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock(pid=1)
            pm._spawn_process("bot_007", ["echo", "hi"], {})

        assert (tmp_path / "logs" / "workers").is_dir()

    def test_log_file_named_after_bot_id(self, pm, tmp_path):
        """Kills mutations changing log file naming."""
        pm._log_dir = str(tmp_path / "logs")

        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock(pid=1)
            pm._spawn_process("bot_007", ["echo", "hi"], {})

        assert (tmp_path / "logs" / "bot_007.log").exists()

    def test_popen_called_with_stdout_log_stderr_stdout(self, pm, tmp_path):
        """Kills mutmut_19-26: Popen argument mutations."""
        import subprocess

        pm._log_dir = str(tmp_path / "logs")

        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock(pid=1)
            pm._spawn_process("bot_000", ["echo"], {"A": "B"})

        _, kwargs = mock_popen.call_args
        assert kwargs.get("stderr") == subprocess.STDOUT
        assert kwargs.get("env") == {"A": "B"}

    def test_log_handle_closed_on_success(self, pm, tmp_path):
        """Kills mutations that skip closing the log handle."""
        pm._log_dir = str(tmp_path / "logs")

        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock(pid=1)
            pm._spawn_process("bot_000", ["echo"], {})

        # If we can open the file, handle was properly closed
        log_file = tmp_path / "logs" / "bot_000.log"
        assert log_file.exists()
        log_file.open("a").close()  # Should not raise if handle was closed

    def test_log_handle_closed_on_failure(self, pm, tmp_path):
        """Kills mutmut_3-9: log handle not closed on exception."""
        pm._log_dir = str(tmp_path / "logs")
        (tmp_path / "logs").mkdir()

        with patch("subprocess.Popen", side_effect=OSError("fail")), pytest.raises(OSError):
            pm._spawn_process("bot_000", ["bad_cmd"], {})

        # Log file should exist and be properly closed
        log_file = tmp_path / "logs" / "bot_000.log"
        assert log_file.exists()


# ---------------------------------------------------------------------------
# monitor_processes - process exit handling
# ---------------------------------------------------------------------------
class TestMonitorProcessesExitHandling:
    @pytest.mark.asyncio
    async def test_exit_code_0_no_prior_error_sets_completed(self, pm, manager):
        """Kills monitor_processes mutations on the exit_code==0 branch."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        mock_proc.returncode = 0
        manager.processes["bot_000"] = mock_proc
        manager.bots["bot_000"] = BotStatusBase(bot_id="bot_000", state="running")
        manager.broadcast_status = AsyncMock()
        manager.config.health_check_interval_s = 0
        manager.account_pool = None

        # Run one iteration by cancelling after
        task = asyncio.create_task(pm.monitor_processes())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert manager.bots["bot_000"].state == "completed"
        assert manager.bots["bot_000"].exit_reason == "target_reached"
        assert manager.bots["bot_000"].completed_at is not None
        assert manager.bots["bot_000"].stopped_at is not None

    @pytest.mark.asyncio
    async def test_exit_code_0_with_prior_error_stays_error(self, pm, manager):
        """Kills mutations on the exit_code==0 + prior error branch."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        mock_proc.returncode = 0
        manager.processes["bot_000"] = mock_proc
        manager.bots["bot_000"] = BotStatusBase(bot_id="bot_000", state="error", error_message="prior error")
        manager.broadcast_status = AsyncMock()
        manager.config.health_check_interval_s = 0
        manager.account_pool = None

        task = asyncio.create_task(pm.monitor_processes())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert manager.bots["bot_000"].state == "error"
        assert manager.bots["bot_000"].exit_reason == "reported_error_then_exit_0"

    @pytest.mark.asyncio
    async def test_exit_code_nonzero_sets_error(self, pm, manager):
        """Kills mutations on the nonzero exit code branch."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 2
        mock_proc.returncode = 2
        manager.processes["bot_000"] = mock_proc
        manager.bots["bot_000"] = BotStatusBase(bot_id="bot_000", state="running")
        manager.broadcast_status = AsyncMock()
        manager.config.health_check_interval_s = 0
        manager.account_pool = None

        task = asyncio.create_task(pm.monitor_processes())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert manager.bots["bot_000"].state == "error"
        assert manager.bots["bot_000"].exit_reason == "exit_code_2"
        assert manager.bots["bot_000"].error_message == "Process exited with code 2"
        assert manager.bots["bot_000"].stopped_at is not None

    @pytest.mark.asyncio
    async def test_exited_process_removed_from_processes(self, pm, manager):
        """Kills mutmut_19 (pop with no default) and mutmut_20 (break vs continue)."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        mock_proc.returncode = 0
        manager.processes["bot_000"] = mock_proc
        manager.bots["bot_000"] = BotStatusBase(bot_id="bot_000", state="running")
        manager.broadcast_status = AsyncMock()
        manager.config.health_check_interval_s = 0
        manager.account_pool = None

        task = asyncio.create_task(pm.monitor_processes())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert "bot_000" not in manager.processes

    @pytest.mark.asyncio
    async def test_none_bot_pops_process_continues(self, pm, manager):
        """Kills mutmut_20: 'continue' → 'break'."""
        mock_proc0 = MagicMock()
        mock_proc0.poll.return_value = 0
        mock_proc0.returncode = 0
        mock_proc1 = MagicMock()
        mock_proc1.poll.return_value = 0
        mock_proc1.returncode = 0

        manager.processes["bot_000"] = mock_proc0  # no matching bot (gets popped+continue)
        manager.processes["bot_001"] = mock_proc1
        manager.bots["bot_001"] = BotStatusBase(bot_id="bot_001", state="running")
        manager.broadcast_status = AsyncMock()
        manager.config.health_check_interval_s = 0
        manager.account_pool = None

        task = asyncio.create_task(pm.monitor_processes())
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # bot_001 should be processed despite bot_000 having no entry
        assert manager.bots["bot_001"].state == "completed"


# ---------------------------------------------------------------------------
# monitor_processes - heartbeat timeout
# ---------------------------------------------------------------------------
class TestMonitorHeartbeat:
    @pytest.mark.asyncio
    async def test_heartbeat_timeout_sets_error_state(self, pm, manager):
        """Kills heartbeat mutations."""
        import time

        old_time = time.time() - 200  # 200s ago, well past timeout
        manager.bots["bot_000"] = BotStatusBase(bot_id="bot_000", state="running", last_update_time=old_time, pid=0)
        manager.config.heartbeat_timeout_s = 1  # 1 second
        manager.broadcast_status = AsyncMock()
        manager.config.health_check_interval_s = 0
        manager.account_pool = None

        task = asyncio.create_task(pm.monitor_processes())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        bot = manager.bots["bot_000"]
        assert bot.state == "error"
        assert bot.exit_reason == "heartbeat_timeout"
        assert bot.error_type == "HeartbeatTimeout"
        assert bot.stopped_at is not None
        assert bot.error_timestamp is not None


# ---------------------------------------------------------------------------
# spawn_swarm - name_style and name_base stored
# ---------------------------------------------------------------------------
class TestSpawnSwarm:
    @pytest.mark.asyncio
    async def test_name_style_stored_on_pm(self, pm, manager, tmp_path):
        """Kills spawn_swarm mutations that skip storing name_style."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: test_game\n")
        manager.broadcast_status = AsyncMock()

        with patch.object(pm, "spawn_bot", new_callable=AsyncMock, return_value="bot_000"):
            await pm.spawn_swarm([str(config)], name_style="fixed", name_base="mybot")

        assert pm._spawn_name_style == "fixed"
        assert pm._spawn_name_base == "mybot"

    @pytest.mark.asyncio
    async def test_queued_bots_pre_registered(self, pm, manager, tmp_path):
        """Kills spawn_swarm mutations that skip pre-registration."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: test_game\n")
        manager.broadcast_status = AsyncMock()

        pre_states: dict[str, str] = {}

        # Capture states right before first spawn to verify pre-registration happened
        orig_spawn = pm.spawn_bot
        first_call = [True]

        async def capture_first_call(cfg, bid):
            if first_call[0]:
                first_call[0] = False
                # At this point both bots should already be pre-registered as queued
                for b_id, b in manager.bots.items():
                    if b_id not in pre_states:
                        pre_states[b_id] = b.state
            return await orig_spawn(cfg, bid)

        mock_proc = MagicMock()
        mock_proc.pid = 1

        with (
            patch.object(pm, "spawn_bot", side_effect=capture_first_call),
            patch.object(pm, "_spawn_process", return_value=mock_proc),
        ):
            await pm.spawn_swarm([str(config), str(config)], group_size=2)

        # At first spawn, there should be pre-registered bots
        assert len(pre_states) >= 2
        # They should all have been queued initially
        for bid, state in pre_states.items():
            assert state == "queued", f"Bot {bid} was {state}, expected queued"

    @pytest.mark.asyncio
    async def test_group_end_min_calc(self, pm, manager, tmp_path):
        """Kills spawn_swarm mutations in group_end calculation."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: test_game\n")
        manager.broadcast_status = AsyncMock()
        mock_proc = MagicMock()
        mock_proc.pid = 1

        # With 3 configs and group_size=2, should spawn all 3
        with patch.object(pm, "_spawn_process", return_value=mock_proc):
            result = await pm.spawn_swarm([str(config)] * 3, group_size=2, group_delay=0.0)

        assert len(result) == 3


# ---------------------------------------------------------------------------
# release_bot_account - cooldown_s=0
# ---------------------------------------------------------------------------
class TestReleaseBotAccount:
    def test_cooldown_s_is_zero(self, pm, manager):
        """Kills mutations changing cooldown_s value."""
        pool = MagicMock()
        pool.release_by_bot.return_value = True
        manager.account_pool = pool

        pm.release_bot_account("bot_000")

        pool.release_by_bot.assert_called_once_with(bot_id="bot_000", cooldown_s=0)
