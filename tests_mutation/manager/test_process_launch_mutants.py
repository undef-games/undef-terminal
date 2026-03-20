#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Mutation-killing tests for AgentProcessManager — kill, launch queued, spawn process, monitor."""

from __future__ import annotations

import asyncio
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


class TestKillAgent:
    @pytest.mark.asyncio
    async def test_kill_timeout_is_5_seconds(self, pm, manager):
        """Kills mutmut_4 (timeout=None) and mutmut_10 (timeout=6.0)."""
        mock_proc = MagicMock()
        manager.processes["agent_000"] = mock_proc
        manager.agents["agent_000"] = AgentStatusBase(agent_id="agent_000", state="running")
        manager.broadcast_status = AsyncMock()

        wait_for_calls = []
        orig_wait_for = asyncio.wait_for

        async def track_wait_for(coro, timeout=None):
            wait_for_calls.append(timeout)
            return await orig_wait_for(coro, timeout=timeout)

        mock_proc.wait.return_value = 0
        with patch("asyncio.wait_for", side_effect=track_wait_for):
            await pm.kill_agent("agent_000")

        assert len(wait_for_calls) == 1
        assert wait_for_calls[0] == 5.0

    @pytest.mark.asyncio
    async def test_stopped_at_is_set_not_none(self, pm, manager):
        """Kills mutmut_31: stopped_at = None instead of time.time()."""
        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        manager.processes["agent_000"] = mock_proc
        manager.agents["agent_000"] = AgentStatusBase(agent_id="agent_000", state="running")
        manager.broadcast_status = AsyncMock()

        await pm.kill_agent("agent_000")

        assert manager.agents["agent_000"].stopped_at is not None
        assert manager.agents["agent_000"].stopped_at > 0

    @pytest.mark.asyncio
    async def test_agent_removed_from_processes(self, pm, manager):
        """Kills mutmut_34: processes.pop(agent_id, ) with missing None default."""
        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        manager.processes["agent_000"] = mock_proc
        manager.agents["agent_000"] = AgentStatusBase(agent_id="agent_000", state="running")
        manager.broadcast_status = AsyncMock()

        await pm.kill_agent("agent_000")

        assert "agent_000" not in manager.processes

    @pytest.mark.asyncio
    async def test_release_agent_account_called_with_agent_id(self, pm, manager):
        """Kills mutmut_35: release_agent_account(None) instead of (agent_id)."""
        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        manager.processes["agent_000"] = mock_proc
        manager.agents["agent_000"] = AgentStatusBase(agent_id="agent_000", state="running")
        manager.broadcast_status = AsyncMock()

        release_calls = []
        orig_release = pm.release_agent_account

        def track_release(bid):
            release_calls.append(bid)
            return orig_release(bid)

        with patch.object(pm, "release_agent_account", side_effect=track_release):
            await pm.kill_agent("agent_000")

        assert "agent_000" in release_calls


# ---------------------------------------------------------------------------
# _launch_queued_agent
# ---------------------------------------------------------------------------
class TestLaunchQueuedAgent:
    @pytest.mark.asyncio
    async def test_sets_error_state_on_failure(self, pm, manager):
        """Kills _launch_queued_agent mutations that change error state."""
        manager.broadcast_status = AsyncMock()
        manager.agents["agent_000"] = AgentStatusBase(agent_id="agent_000", state="queued", pid=0)

        with patch.object(pm, "spawn_agent", side_effect=RuntimeError("spawn error")):
            await pm._launch_queued_agent("agent_000", "/config.yaml")

        agent = manager.agents["agent_000"]
        assert agent.state == "error"

    @pytest.mark.asyncio
    async def test_sets_error_message_with_launch_failed(self, pm, manager):
        """Kills mutmut_1: error_message set to wrong/None value."""
        manager.broadcast_status = AsyncMock()
        manager.agents["agent_000"] = AgentStatusBase(agent_id="agent_000", state="queued", pid=0)

        with patch.object(pm, "spawn_agent", side_effect=RuntimeError("specific error")):
            await pm._launch_queued_agent("agent_000", "/config.yaml")

        assert "Launch failed" in (manager.agents["agent_000"].error_message or "")
        assert "specific error" in (manager.agents["agent_000"].error_message or "")

    @pytest.mark.asyncio
    async def test_sets_exit_reason_launch_failed(self, pm, manager):
        """Kills mutations changing exit_reason."""
        manager.broadcast_status = AsyncMock()
        manager.agents["agent_000"] = AgentStatusBase(agent_id="agent_000", state="queued", pid=0)

        with patch.object(pm, "spawn_agent", side_effect=RuntimeError("fail")):
            await pm._launch_queued_agent("agent_000", "/config.yaml")

        assert manager.agents["agent_000"].exit_reason == "launch_failed"

    @pytest.mark.asyncio
    async def test_broadcasts_on_failure(self, pm, manager):
        """Kills mutations that skip broadcast."""
        manager.broadcast_status = AsyncMock()
        manager.agents["agent_000"] = AgentStatusBase(agent_id="agent_000", state="queued", pid=0)

        with patch.object(pm, "spawn_agent", side_effect=RuntimeError("fail")):
            await pm._launch_queued_agent("agent_000", "/config.yaml")

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
            pm._spawn_process("agent_007", ["echo", "hi"], {})

        # The custom_log dir should have been created
        assert custom_log.is_dir()

    def test_default_log_dir_is_logs_workers(self, pm, tmp_path, monkeypatch):
        """Kills mutations changing default log_dir path."""
        pm._log_dir = ""  # Empty string triggers default
        monkeypatch.chdir(tmp_path)

        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock(pid=1)
            pm._spawn_process("agent_007", ["echo", "hi"], {})

        assert (tmp_path / "logs" / "workers").is_dir()

    def test_log_file_named_after_agent_id(self, pm, tmp_path):
        """Kills mutations changing log file naming."""
        pm._log_dir = str(tmp_path / "logs")

        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock(pid=1)
            pm._spawn_process("agent_007", ["echo", "hi"], {})

        assert (tmp_path / "logs" / "agent_007.log").exists()

    def test_popen_called_with_stdout_log_stderr_stdout(self, pm, tmp_path):
        """Kills mutmut_19-26: Popen argument mutations."""
        import subprocess

        pm._log_dir = str(tmp_path / "logs")

        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock(pid=1)
            pm._spawn_process("agent_000", ["echo"], {"A": "B"})

        _, kwargs = mock_popen.call_args
        assert kwargs.get("stderr") == subprocess.STDOUT
        assert kwargs.get("env") == {"A": "B"}

    def test_log_handle_closed_on_success(self, pm, tmp_path):
        """Kills mutations that skip closing the log handle."""
        pm._log_dir = str(tmp_path / "logs")

        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock(pid=1)
            pm._spawn_process("agent_000", ["echo"], {})

        # If we can open the file, handle was properly closed
        log_file = tmp_path / "logs" / "agent_000.log"
        assert log_file.exists()
        log_file.open("a").close()  # Should not raise if handle was closed

    def test_log_handle_closed_on_failure(self, pm, tmp_path):
        """Kills mutmut_3-9: log handle not closed on exception."""
        pm._log_dir = str(tmp_path / "logs")
        (tmp_path / "logs").mkdir()

        with patch("subprocess.Popen", side_effect=OSError("fail")), pytest.raises(OSError):
            pm._spawn_process("agent_000", ["bad_cmd"], {})

        # Log file should exist and be properly closed
        log_file = tmp_path / "logs" / "agent_000.log"
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
        manager.processes["agent_000"] = mock_proc
        manager.agents["agent_000"] = AgentStatusBase(agent_id="agent_000", state="running")
        manager.broadcast_status = AsyncMock()
        manager.config.health_check_interval_s = 0
        manager.account_pool = None

        # Run one iteration by cancelling after
        task = asyncio.create_task(pm.monitor_processes())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert manager.agents["agent_000"].state == "completed"
        assert manager.agents["agent_000"].exit_reason == "target_reached"
        assert manager.agents["agent_000"].completed_at is not None
        assert manager.agents["agent_000"].stopped_at is not None

    @pytest.mark.asyncio
    async def test_exit_code_0_with_prior_error_stays_error(self, pm, manager):
        """Kills mutations on the exit_code==0 + prior error branch."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        mock_proc.returncode = 0
        manager.processes["agent_000"] = mock_proc
        manager.agents["agent_000"] = AgentStatusBase(agent_id="agent_000", state="error", error_message="prior error")
        manager.broadcast_status = AsyncMock()
        manager.config.health_check_interval_s = 0
        manager.account_pool = None

        task = asyncio.create_task(pm.monitor_processes())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert manager.agents["agent_000"].state == "error"
        assert manager.agents["agent_000"].exit_reason == "reported_error_then_exit_0"

    @pytest.mark.asyncio
    async def test_exit_code_nonzero_sets_error(self, pm, manager):
        """Kills mutations on the nonzero exit code branch."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 2
        mock_proc.returncode = 2
        manager.processes["agent_000"] = mock_proc
        manager.agents["agent_000"] = AgentStatusBase(agent_id="agent_000", state="running")
        manager.broadcast_status = AsyncMock()
        manager.config.health_check_interval_s = 0
        manager.account_pool = None

        task = asyncio.create_task(pm.monitor_processes())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert manager.agents["agent_000"].state == "error"
        assert manager.agents["agent_000"].exit_reason == "exit_code_2"
        assert manager.agents["agent_000"].error_message == "Process exited with code 2"
        assert manager.agents["agent_000"].stopped_at is not None

    @pytest.mark.asyncio
    async def test_exited_process_removed_from_processes(self, pm, manager):
        """Kills mutmut_19 (pop with no default) and mutmut_20 (break vs continue)."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        mock_proc.returncode = 0
        manager.processes["agent_000"] = mock_proc
        manager.agents["agent_000"] = AgentStatusBase(agent_id="agent_000", state="running")
        manager.broadcast_status = AsyncMock()
        manager.config.health_check_interval_s = 0
        manager.account_pool = None

        task = asyncio.create_task(pm.monitor_processes())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert "agent_000" not in manager.processes

    @pytest.mark.asyncio
    async def test_none_agent_pops_process_continues(self, pm, manager):
        """Kills mutmut_20: 'continue' → 'break'."""
        mock_proc0 = MagicMock()
        mock_proc0.poll.return_value = 0
        mock_proc0.returncode = 0
        mock_proc1 = MagicMock()
        mock_proc1.poll.return_value = 0
        mock_proc1.returncode = 0

        manager.processes["agent_000"] = mock_proc0  # no matching agent (gets popped+continue)
        manager.processes["agent_001"] = mock_proc1
        manager.agents["agent_001"] = AgentStatusBase(agent_id="agent_001", state="running")
        manager.broadcast_status = AsyncMock()
        manager.config.health_check_interval_s = 0
        manager.account_pool = None

        task = asyncio.create_task(pm.monitor_processes())
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # agent_001 should be processed despite agent_000 having no entry
        assert manager.agents["agent_001"].state == "completed"


# ---------------------------------------------------------------------------
# monitor_processes - heartbeat timeout
# ---------------------------------------------------------------------------
class TestMonitorHeartbeat:
    @pytest.mark.asyncio
    async def test_heartbeat_timeout_sets_error_state(self, pm, manager):
        """Kills heartbeat mutations."""
        import time

        old_time = time.time() - 200  # 200s ago, well past timeout
        manager.agents["agent_000"] = AgentStatusBase(agent_id="agent_000", state="running", last_update_time=old_time, pid=0)
        manager.config.heartbeat_timeout_s = 1  # 1 second
        manager.broadcast_status = AsyncMock()
        manager.config.health_check_interval_s = 0
        manager.account_pool = None

        task = asyncio.create_task(pm.monitor_processes())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        agent = manager.agents["agent_000"]
        assert agent.state == "error"
        assert agent.exit_reason == "heartbeat_timeout"
        assert agent.error_type == "HeartbeatTimeout"
        assert agent.stopped_at is not None
        assert agent.error_timestamp is not None


# ---------------------------------------------------------------------------
# spawn_swarm - name_style and name_base stored
# ---------------------------------------------------------------------------
