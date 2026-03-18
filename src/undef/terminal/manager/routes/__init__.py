#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Swarm manager API route package."""

from __future__ import annotations

# Import submodules to trigger route registration on the shared router.
from undef.terminal.manager.routes import bot_ops, bot_update, spawn, status
from undef.terminal.manager.routes.models import router

__all__ = ["router"]
