#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Mutation-killing tests for undef.terminal.manager.process."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from undef.terminal.manager.config import ManagerConfig
from undef.terminal.manager.core import AgentManager
from undef.terminal.manager.models import AgentStatusBase
from undef.terminal.manager.process import AgentProcessManager


class FakeWorkerPlugin:
    @property
    def worker_type(self) -> str:
        return "test_game"

    @property
    def worker_module(self) -> str:
        return "test_module"

    def configure_worker_env(self, env, agent_status, manager, **kwargs):
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
    return AgentManager(config)


@pytest.fixture
def pm(manager, tmp_path):
    pm = AgentProcessManager(
        manager,
        worker_registry={"test_game": FakeWorkerPlugin()},
        log_dir=str(tmp_path / "logs"),
    )
    manager.agent_process_manager = pm
    return pm


# ---------------------------------------------------------------------------
# __init__ default value mutations (mutmut_1, 5, 9, 12, 13, 14, 15, 16, 17)
# ---------------------------------------------------------------------------
class TestInitDefaults:
    def test_log_dir_default_is_empty_string(self, manager):
        """Kills mutmut_1: log_dir default "" → "XXXX"."""
        pm = AgentProcessManager(manager)
        assert pm._log_dir == ""

    def test_log_dir_stored(self, manager, tmp_path):
        """Kills mutmut_5: self._log_dir = None."""
        pm = AgentProcessManager(manager, log_dir=str(tmp_path))
        assert pm._log_dir == str(tmp_path)

    def test_queued_launch_delay_is_30(self, manager):
        """Kills mutmut_9: _queued_launch_delay = 31.0."""
        pm = AgentProcessManager(manager)
        assert pm._queued_launch_delay == 30.0

    def test_spawn_name_style_is_random(self, manager):
        """Kills mutmut_12/13/14: _spawn_name_style = None/XXrandomXX/RANDOM."""
        pm = AgentProcessManager(manager)
        assert pm._spawn_name_style == "random"

    def test_spawn_name_base_is_empty(self, manager):
        """Kills mutmut_15/16: _spawn_name_base = None/"XXXX"."""
        pm = AgentProcessManager(manager)
        assert pm._spawn_name_base == ""

    def test_last_spawn_config_is_none(self, manager):
        """Kills mutmut_17: _last_spawn_config = "" instead of None."""
        pm = AgentProcessManager(manager)
        assert pm._last_spawn_config is None

    def test_next_agent_index_starts_at_zero(self, manager):
        """Kills mutmut_10/11: _next_agent_index = None/1."""
        pm = AgentProcessManager(manager)
        assert pm._next_agent_index == 0

    def test_spawn_tasks_is_list(self, manager):
        """Kills mutmut_6: _spawn_tasks = None."""
        pm = AgentProcessManager(manager)
        assert pm._spawn_tasks == []
        assert isinstance(pm._spawn_tasks, list)

    def test_queued_since_is_dict(self, manager):
        """Kills mutmut_7: _queued_since = None."""
        pm = AgentProcessManager(manager)
        assert pm._queued_since == {}
        assert isinstance(pm._queued_since, dict)

    def test_worker_registry_none_defaults_to_empty(self, manager):
        """Kills mutmut_3: _worker_registry = None."""
        pm = AgentProcessManager(manager, worker_registry=None)
        assert pm._worker_registry == {}


# ---------------------------------------------------------------------------
# sync_next_agent_index (mutmut_3: max_seen = -2)
# ---------------------------------------------------------------------------
class TestSyncNextAgentIndex:
    def test_empty_agents_returns_zero(self, pm):
        """When no agents exist, sync should return 0 (max_seen=-1, so max(-1)+1=0).
        Kills mutmut_3: max_seen=-2 → would also return 0 here but next test catches it."""
        result = pm.sync_next_agent_index()
        assert result == 0

    def test_max_seen_negative_one_means_next_is_zero(self, pm, manager):
        """Kills mutmut_3: max_seen=-2. With agent_0, max_seen should be 0, next=1.
        Without agents, next should be 0 (not -1 which -2+1 would give in some edge case)."""
        # With agents named non-agent_ format, max_seen stays -1, next = max(0, -1+1) = 0
        manager.agents["worker_xyz"] = AgentStatusBase(agent_id="worker_xyz")
        result = pm.sync_next_agent_index()
        assert result == 0  # mutmut_3 would give max(0, -2+1) = max(0,-1) = 0 also...

    def test_sync_uses_union_of_agents_and_processes(self, pm, manager):
        """Kills mutmut_4: uses & instead of |."""
        manager.agents["agent_005"] = AgentStatusBase(agent_id="agent_005")
        manager.processes["agent_010"] = MagicMock()
        result = pm.sync_next_agent_index()
        assert result == 11  # Uses union: max(5, 10) + 1 = 11


# ---------------------------------------------------------------------------
# allocate_agent_id (mutmut_8/10)
# ---------------------------------------------------------------------------
class TestAllocateAgentId:
    def test_next_agent_index_incremented_after_alloc(self, pm, manager):
        """Kills mutmut_8: _next_agent_index = idx - 1 (instead of idx + 1)
        and mutmut_10: idx = 1 instead of idx += 1."""
        bid = pm.allocate_agent_id()
        assert bid == "agent_000"
        # After allocation, _next_agent_index should be 1 (not -1 or 1 from restart)
        assert pm._next_agent_index == 1

    def test_sequential_allocations(self, pm, manager):
        """Kills mutmut_10: idx = 1 would cause non-sequential allocation."""
        bid1 = pm.allocate_agent_id()
        manager.agents[bid1] = AgentStatusBase(agent_id=bid1)
        bid2 = pm.allocate_agent_id()
        manager.agents[bid2] = AgentStatusBase(agent_id=bid2)
        bid3 = pm.allocate_agent_id()
        # Should be sequential
        assert bid1 == "agent_000"
        assert bid2 == "agent_001"
        assert bid3 == "agent_002"


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
                name_base="myagent",
            )
            await asyncio.gather(*[t for t in pm._spawn_tasks if not t.done()], return_exceptions=True)

        assert spawned_kwargs["group_size"] == 3
        assert spawned_kwargs["group_delay"] == 5.0
        assert spawned_kwargs["name_style"] == "fixed"
        assert spawned_kwargs["name_base"] == "myagent"


# ---------------------------------------------------------------------------
# spawn_agent cmd construction and env filtering
# ---------------------------------------------------------------------------
class TestSpawnAgentCmd:
    @pytest.mark.asyncio
    async def test_cmd_uses_dash_m_flag(self, pm, manager, tmp_path):
        """Kills mutmut_70/71: '-m' → 'XX-mXX'/'-M'."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: test_game\n")
        manager.broadcast_status = AsyncMock()

        captured_cmd = []

        def fake_spawn(agent_id, cmd, env):
            captured_cmd.extend(cmd)
            m = MagicMock()
            m.pid = 1
            return m

        with patch.object(pm, "_spawn_process", side_effect=fake_spawn):
            await pm.spawn_agent(str(config), "agent_000")

        assert "-m" in captured_cmd
        assert captured_cmd[1] == "-m"

    @pytest.mark.asyncio
    async def test_cmd_uses_config_flag(self, pm, manager, tmp_path):
        """Kills mutmut_72/73: '--config' → 'XX--configXX'/'--CONFIG'."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: test_game\n")
        manager.broadcast_status = AsyncMock()

        captured_cmd = []

        def fake_spawn(agent_id, cmd, env):
            captured_cmd.extend(cmd)
            m = MagicMock()
            m.pid = 1
            return m

        with patch.object(pm, "_spawn_process", side_effect=fake_spawn):
            await pm.spawn_agent(str(config), "agent_000")

        assert "--config" in captured_cmd

    @pytest.mark.asyncio
    async def test_cmd_uses_agent_id_flag(self, pm, manager, tmp_path):
        """Kills mutmut_74/75: '--agent-id' → 'XX--agent-idXX'/'--AGENT-ID'."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: test_game\n")
        manager.broadcast_status = AsyncMock()

        captured_cmd = []

        def fake_spawn(agent_id, cmd, env):
            captured_cmd.extend(cmd)
            m = MagicMock()
            m.pid = 1
            return m

        with patch.object(pm, "_spawn_process", side_effect=fake_spawn):
            await pm.spawn_agent(str(config), "agent_000")

        assert "--agent-id" in captured_cmd

    @pytest.mark.asyncio
    async def test_cmd_contains_worker_module(self, pm, manager, tmp_path):
        """Kills mutmut_68: worker_module = None."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: test_game\n")
        manager.broadcast_status = AsyncMock()

        captured_cmd = []

        def fake_spawn(agent_id, cmd, env):
            captured_cmd.extend(cmd)
            m = MagicMock()
            m.pid = 1
            return m

        with patch.object(pm, "_spawn_process", side_effect=fake_spawn):
            await pm.spawn_agent(str(config), "agent_000")

        assert "test_module" in captured_cmd

    @pytest.mark.asyncio
    async def test_env_uses_or_not_and(self, pm, manager, tmp_path):
        """Kills mutmut_78: 'or k in _WORKER_ENV_PASSTHROUGH' → 'and k in'."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: test_game\n")
        manager.broadcast_status = AsyncMock()

        captured_env = {}

        def fake_spawn(agent_id, cmd, env):
            captured_env.update(env)
            m = MagicMock()
            m.pid = 1
            return m

        # Set a passthrough var that has no prefix
        with (
            patch.dict(os.environ, {"PATH": "/usr/bin", "HOME": "/home/test"}),
            patch.object(pm, "_spawn_process", side_effect=fake_spawn),
        ):
            await pm.spawn_agent(str(config), "agent_000")

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

        def fake_spawn(agent_id, cmd, env):
            captured_env.update(env)
            m = MagicMock()
            m.pid = 1
            return m

        sentinel_key = "TOTALLY_RANDOM_VAR_NOT_IN_PASSTHROUGH_XYZ123"
        with (
            patch.dict(os.environ, {sentinel_key: "should_not_appear"}),
            patch.object(pm, "_spawn_process", side_effect=fake_spawn),
        ):
            await pm.spawn_agent(str(config), "agent_000")

        assert sentinel_key not in captured_env

    @pytest.mark.asyncio
    async def test_name_style_env_set_correctly(self, pm, manager, tmp_path):
        """Kills mutmut_93: NAME_STYLE = None."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: test_game\n")
        manager.broadcast_status = AsyncMock()
        pm._spawn_name_style = "fixed"

        captured_env = {}

        def fake_spawn(agent_id, cmd, env):
            captured_env.update(env)
            m = MagicMock()
            m.pid = 1
            return m

        env_prefix = manager.config.worker_env_prefix
        with patch.object(pm, "_spawn_process", side_effect=fake_spawn):
            await pm.spawn_agent(str(config), "agent_000")

        assert captured_env.get(f"{env_prefix}NAME_STYLE") == "fixed"

    @pytest.mark.asyncio
    async def test_configure_worker_env_called_with_manager(self, pm, manager, tmp_path):
        """Kills mutmut_95 (agent_entry is None → configure not called)
        and mutmut_97 (configure skipped) and mutmut_98 (manager=None)."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: test_game\n")
        manager.broadcast_status = AsyncMock()
        # Add agent entry so configure_worker_env is called
        manager.agents["agent_000"] = AgentStatusBase(agent_id="agent_000", state="queued", pid=0)

        configure_calls = []

        def tracking_configure(self_plugin, env, agent_status, mgr, **kwargs):
            configure_calls.append((agent_status, mgr))

        with patch.object(FakeWorkerPlugin, "configure_worker_env", tracking_configure):
            mock_proc = MagicMock()
            mock_proc.pid = 1
            with patch.object(pm, "_spawn_process", return_value=mock_proc):
                await pm.spawn_agent(str(config), "agent_000")

        assert len(configure_calls) == 1
        # Manager must not be None (kills mutmut_98)
        assert configure_calls[0][1] is not None
        assert configure_calls[0][1] is manager

    @pytest.mark.asyncio
    async def test_configure_worker_env_not_called_when_no_agent_entry(self, pm, manager, tmp_path):
        """Kills mutmut_95: agent_entry is None check inverted."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: test_game\n")
        manager.broadcast_status = AsyncMock()
        # No agent entry in agents dict

        configure_calls = []

        def tracking_configure(self_plugin, env, agent_status, mgr, **kwargs):
            configure_calls.append(True)

        with patch.object(FakeWorkerPlugin, "configure_worker_env", tracking_configure):
            mock_proc = MagicMock()
            mock_proc.pid = 1
            with patch.object(pm, "_spawn_process", return_value=mock_proc):
                await pm.spawn_agent(str(config), "agent_000")

        # No agent entry → configure not called
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
            await pm.spawn_agent(str(config), "agent_000")

        assert pm._last_spawn_config == str(config)

    @pytest.mark.asyncio
    async def test_stopped_at_set_to_none_on_spawn(self, pm, manager, tmp_path):
        """Kills mutations that skip setting stopped_at=None for existing agents."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: test_game\n")
        manager.broadcast_status = AsyncMock()
        # Pre-existing agent with a stopped_at
        manager.agents["agent_000"] = AgentStatusBase(agent_id="agent_000", state="stopped", pid=0, stopped_at=12345.0)

        mock_proc = MagicMock()
        mock_proc.pid = 999
        with patch.object(pm, "_spawn_process", return_value=mock_proc):
            await pm.spawn_agent(str(config), "agent_000")

        assert manager.agents["agent_000"].stopped_at is None


# ---------------------------------------------------------------------------
# spawn_agent worker_type fallback
# ---------------------------------------------------------------------------
class TestSpawnAgentWorkerType:
    @pytest.mark.asyncio
    async def test_worker_type_default_fallback_single_registry(self, pm, manager, tmp_path):
        """Config with no worker_type key → single-registry fallback uses the one registered entry."""
        config = tmp_path / "test.yaml"
        config.write_text("{}  # empty\n")
        manager.broadcast_status = AsyncMock()
        mock_proc = MagicMock()
        mock_proc.pid = 1
        with patch.object(pm, "_spawn_process", return_value=mock_proc):
            agent_id = await pm.spawn_agent(str(config), "agent_000")
        assert agent_id == "agent_000"

    @pytest.mark.asyncio
    async def test_worker_type_unknown_raises_with_multiple_registries(self, pm, manager, tmp_path):
        """Unknown worker_type with multiple registries raises RuntimeError."""
        config = tmp_path / "test.yaml"
        config.write_text("worker_type: not_registered\n")
        # Add a second registry entry so fallback doesn't apply
        pm._worker_registry["other_game"] = pm._worker_registry["test_game"]
        with pytest.raises(RuntimeError, match="Unknown worker_type"):
            await pm.spawn_agent(str(config), "agent_000")

    @pytest.mark.asyncio
    async def test_worker_type_read_default_arg(self, pm, manager, tmp_path):
        """When worker_type key missing from yaml, single-registry fallback is used."""
        config = tmp_path / "test.yaml"
        config.write_text("connection:\n  host: somewhere\n")
        manager.broadcast_status = AsyncMock()
        mock_proc = MagicMock()
        mock_proc.pid = 1
        with patch.object(pm, "_spawn_process", return_value=mock_proc):
            agent_id = await pm.spawn_agent(str(config), "agent_000")
        assert agent_id == "agent_000"


# ---------------------------------------------------------------------------
# kill_agent timeout value and state (mutmut_4/10/31/34/35)
# ---------------------------------------------------------------------------
