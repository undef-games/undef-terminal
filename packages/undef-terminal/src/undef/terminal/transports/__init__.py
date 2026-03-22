#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Transport adapters for undef-terminal."""

from __future__ import annotations

from undef.terminal.transports.base import ConnectionTransport
from undef.terminal.transports.chaos import ChaosTransport
from undef.terminal.transports.ssh import SSHStreamReader, SSHStreamWriter, start_ssh_server
from undef.terminal.transports.telnet import TelnetClient, TelnetTransport, start_telnet_server
from undef.terminal.transports.websocket import WebSocketStreamReader, WebSocketStreamWriter

__all__ = [
    "ChaosTransport",
    "ConnectionTransport",
    "SSHStreamReader",
    "SSHStreamWriter",
    "TelnetClient",
    "TelnetTransport",
    "WebSocketStreamReader",
    "WebSocketStreamWriter",
    "start_ssh_server",
    "start_telnet_server",
]
