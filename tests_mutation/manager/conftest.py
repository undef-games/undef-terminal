#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Shared fixtures for tests_mutation/manager/ — used by files that don't define their own."""

from __future__ import annotations

import pytest

from undef.terminal.manager.config import ManagerConfig
from undef.terminal.manager.core import SwarmManager
from undef.terminal.manager.process import BotProcessManager


class _FakeWorkerPlugin:
    @property
    def worker_type(self) -> str:
        return "test_game"

    @property
    def worker_module(self) -> str:
        return "test_worker_module"

    def configure_worker_env(self, env, bot_status, manager, **kwargs):  # type: ignore[no-untyped-def]
        env["TEST_CUSTOM"] = "value"


@pytest.fixture
def config(tmp_path):  # type: ignore[no-untyped-def]
    return ManagerConfig(
        state_file=str(tmp_path / "state.json"),
        timeseries_dir=str(tmp_path / "metrics"),
        log_dir=str(tmp_path / "logs"),
    )


@pytest.fixture
def manager(config):  # type: ignore[no-untyped-def]
    return SwarmManager(config)


@pytest.fixture
def pm(manager, tmp_path):  # type: ignore[no-untyped-def]
    process_manager = BotProcessManager(
        manager,
        worker_registry={"test_game": _FakeWorkerPlugin()},
        log_dir=str(tmp_path / "logs"),
    )
    manager.bot_process_manager = process_manager
    return process_manager
