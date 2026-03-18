#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Generic swarm manager for bot orchestration.

Public API::

    from undef.terminal.manager import create_manager_app, ManagerConfig, SwarmManager
    from undef.terminal.manager.models import BotStatusBase, SwarmStatus, SpawnBatchRequest
    from undef.terminal.manager.protocols import (
        AccountPoolPlugin, IdentityStorePlugin, ManagedBotPlugin,
        StatusUpdatePlugin, TimeseriesPlugin, WorkerRegistryPlugin,
    )

    app, manager = create_manager_app(ManagerConfig(), worker_registry={...})
"""

from __future__ import annotations

from undef.terminal.manager.app import create_manager_app
from undef.terminal.manager.config import ManagerConfig
from undef.terminal.manager.core import SwarmManager
from undef.terminal.manager.models import BotStatusBase, SwarmStatus

__all__ = [
    "BotStatusBase",
    "ManagerConfig",
    "SwarmManager",
    "SwarmStatus",
    "create_manager_app",
]
