#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Tests for TelnetClient and start_telnet_server."""

from __future__ import annotations

import asyncio

import pytest

from tests.helpers.mock_server import MockTelnetServer
from undef.terminal.transports.telnet import (
    DO,
    ECHO,
    IAC,
    NAWS,
    WILL,
    TelnetClient,
    start_telnet_server,
)


class TestTelnetConstants:
    def test_iac_value(self) -> None:
        assert IAC == 255

    def test_will_value(self) -> None:
        assert WILL == 251

    def test_do_value(self) -> None:
        assert DO == 253


class TestTelnetClient:
    async def test_connect_and_receive(self) -> None:
        async with MockTelnetServer(send=b"hello") as srv, TelnetClient("127.0.0.1", srv.port) as client:
            data = await client.read(5)
        assert data == b"hello"

    async def test_write_and_server_receives(self) -> None:
        async with MockTelnetServer() as srv:
            async with TelnetClient("127.0.0.1", srv.port) as client:
                client.write(b"ping")
                await client.drain()
            await srv.wait_for_connection()
        assert srv.received == b"ping"

    async def test_not_connected_raises(self) -> None:
        client = TelnetClient("127.0.0.1", 9999)
        with pytest.raises(RuntimeError, match="not connected"):
            await client.read(1)

    def test_will_builds_correct_bytes(self) -> None:
        client = TelnetClient("127.0.0.1", 9999)
        assert client.will(ECHO) == bytes([IAC, WILL, ECHO])

    def test_do_builds_correct_bytes(self) -> None:
        client = TelnetClient("127.0.0.1", 9999)
        assert client.do(NAWS) == bytes([IAC, DO, NAWS])


class TestStartTelnetServer:
    async def test_server_sends_handshake(self, free_port: int) -> None:
        received: list[bytes] = []
        connected = asyncio.Event()

        async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            writer.close()
            connected.set()

        server = await start_telnet_server(handler, host="127.0.0.1", port=free_port)
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", free_port)
            # Read the handshake — at least 15 bytes (5 IAC sequences × 3 bytes each)
            data = await asyncio.wait_for(reader.read(64), timeout=2.0)
            received.append(data)
            writer.close()
        finally:
            server.close()
            await server.wait_closed()

        handshake = received[0]
        # Verify handshake starts with IAC WILL ECHO
        assert handshake[:3] == bytes([IAC, WILL, ECHO])
        # Verify IAC DO NAWS is somewhere in the handshake
        assert bytes([IAC, DO, NAWS]) in handshake

    async def test_handler_called_with_reader_writer(self, free_port: int) -> None:
        handler_called = asyncio.Event()

        async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            writer.write(b"ok")
            await writer.drain()
            writer.close()
            handler_called.set()

        server = await start_telnet_server(handler, host="127.0.0.1", port=free_port)
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", free_port)
            # Read handshake + "ok"
            await asyncio.wait_for(reader.read(64), timeout=2.0)
            await asyncio.wait_for(handler_called.wait(), timeout=2.0)
            writer.close()
        finally:
            server.close()
            await server.wait_closed()

        assert handler_called.is_set()
