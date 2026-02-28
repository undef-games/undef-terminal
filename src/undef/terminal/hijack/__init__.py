#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Hijack infrastructure for human-in-the-loop terminal takeover.

The hijack system lets a human operator pause an automated bot, send keystrokes
directly, step through individual loop iterations, and then resume automation.

Three layers:

- :class:`~undef.terminal.hijack.base.HijackBase` — mixin for the worker/bot side.
  Drop into any async class; call :meth:`await_if_hijacked` at checkpoints.

- :class:`~undef.terminal.hijack.hub.TermHub` — server-side registry.
  Tracks which bots are connected, manages leases, routes input/output.

- :class:`~undef.terminal.hijack.bridge.TermBridge` — worker-side WS client.
  Connects the bot to the hub, forwards terminal output, receives control commands.

- :mod:`~undef.terminal.hijack.routes` — FastAPI WebSocket + REST routes.
  Mount via ``hub.create_router()`` onto any FastAPI app.

Requires the ``websocket`` extra for ``hub``, ``bridge``, and ``routes``::

    pip install 'undef-terminal[websocket]'

``base.py`` has no optional deps.
"""

from __future__ import annotations

from undef.terminal.hijack.base import HijackBase

__all__ = ["HijackBase"]
