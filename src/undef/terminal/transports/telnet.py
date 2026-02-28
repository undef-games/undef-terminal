#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Telnet transport for undef-terminal.

Provides:
- :func:`start_telnet_server` — asyncio TCP server with basic telnet negotiation.
- :class:`TelnetClient` — thin client wrapper around ``asyncio.open_connection``
  with IAC constants and negotiation helpers.
- Telnet protocol constants: ``IAC``, ``WILL``, ``WONT``, ``DO``, ``DONT``, ``SB``, ``SE``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Telnet protocol constants
# ---------------------------------------------------------------------------

IAC: int = 255  # Interpret As Command
WILL: int = 251  # Will perform option
WONT: int = 252  # Won't perform option
DO: int = 253  # Do perform option
DONT: int = 254  # Don't perform option
SB: int = 250  # Sub-negotiation Begin
SE: int = 240  # Sub-negotiation End

# Telnet options
ECHO: int = 1  # Echo
SGA: int = 3  # Suppress Go Ahead
NAWS: int = 31  # Negotiate About Window Size
LINEMODE: int = 34  # Linemode

# Terminal type subnegotiation
OPT_TTYPE: int = 24
TTYPE_IS: int = 0

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

ConnectionHandler = Callable[
    [asyncio.StreamReader, asyncio.StreamWriter],
    Coroutine[Any, Any, None],
]


def _build_telnet_handshake() -> bytes:
    """Build the initial telnet negotiation sequence.

    Sends:
    - IAC WILL ECHO   (server will handle echo)
    - IAC WILL SGA    (suppress go-ahead for full-duplex)
    - IAC DO SGA      (request client suppress go-ahead too)
    - IAC DONT LINEMODE (disable client-side line editing)
    - IAC DO NAWS     (request client window size)
    """
    return bytes(
        [
            IAC,
            WILL,
            ECHO,
            IAC,
            WILL,
            SGA,
            IAC,
            DO,
            SGA,
            IAC,
            DONT,
            LINEMODE,
            IAC,
            DO,
            NAWS,
        ]
    )


# ---------------------------------------------------------------------------
# Server-mode
# ---------------------------------------------------------------------------


async def start_telnet_server(
    handler: ConnectionHandler,
    host: str = "0.0.0.0",  # nosec B104
    port: int = 2102,
) -> asyncio.Server:
    """Create and start an asyncio TCP server with basic telnet negotiation.

    Sends the IAC negotiation preamble on each new connection, then delegates
    to *handler* with the raw ``(reader, writer)`` pair.

    Args:
        handler: Async callback ``(reader, writer) -> None`` called per connection.
        host: Network interface to bind to (default ``0.0.0.0``).
        port: TCP port number (default ``2102``).

    Returns:
        The running :class:`asyncio.Server` instance.
    """

    async def _client_cb(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peername = writer.get_extra_info("peername")
        addr = f"{peername[0]}:{peername[1]}" if peername else "unknown"
        logger.info("telnet client connected addr=%s", addr)

        try:
            writer.write(_build_telnet_handshake())
            await writer.drain()
        except (ConnectionResetError, BrokenPipeError, OSError):
            logger.warning("connection lost during handshake addr=%s", addr)
            writer.close()
            return

        # Brief pause for the client to process negotiation
        await asyncio.sleep(0.1)
        await handler(reader, writer)

    server = await asyncio.start_server(_client_cb, host, port)
    logger.info("telnet server started host=%s port=%d", host, port)
    return server


# ---------------------------------------------------------------------------
# Client-mode
# ---------------------------------------------------------------------------


class TelnetClient:
    """Thin asyncio telnet client with IAC negotiation helpers.

    Wraps ``asyncio.open_connection`` and provides methods to read/write
    bytes and respond to telnet IAC negotiations.

    Example::

        async with TelnetClient("bbs.example.com", 23) as client:
            data = await client.read(1024)
    """

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def connect(self) -> None:
        """Open the TCP connection."""
        self._reader, self._writer = await asyncio.open_connection(self._host, self._port)
        logger.debug("telnet client connected host=%s port=%d", self._host, self._port)

    async def close(self) -> None:
        """Close the TCP connection."""
        if self._writer is not None:
            self._writer.close()
            with contextlib.suppress(OSError, ConnectionResetError):
                await self._writer.wait_closed()
            self._writer = None
            self._reader = None

    async def __aenter__(self) -> TelnetClient:
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def read(self, n: int) -> bytes:
        """Read up to *n* bytes from the server."""
        if self._reader is None:
            raise RuntimeError("not connected")
        return await self._reader.read(n)

    async def readuntil(self, separator: bytes = b"\n") -> bytes:
        """Read until *separator* is found."""
        if self._reader is None:
            raise RuntimeError("not connected")
        return await self._reader.readuntil(separator)

    def write(self, data: bytes) -> None:
        """Write *data* to the server (buffered until :meth:`drain`)."""
        if self._writer is None:
            raise RuntimeError("not connected")
        self._writer.write(data)

    async def drain(self) -> None:
        """Flush the write buffer."""
        if self._writer is None:
            raise RuntimeError("not connected")
        await self._writer.drain()

    def will(self, option: int) -> bytes:
        """Build an IAC WILL *option* sequence."""
        return bytes([IAC, WILL, option])

    def wont(self, option: int) -> bytes:
        """Build an IAC WONT *option* sequence."""
        return bytes([IAC, WONT, option])

    def do(self, option: int) -> bytes:
        """Build an IAC DO *option* sequence."""
        return bytes([IAC, DO, option])

    def dont(self, option: int) -> bytes:
        """Build an IAC DONT *option* sequence."""
        return bytes([IAC, DONT, option])
