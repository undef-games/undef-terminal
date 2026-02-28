#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Tests for TelnetTransport (full RFC 854 client)."""

from __future__ import annotations

import asyncio

import pytest

from tests.helpers.mock_server import MockTelnetServer
from undef.terminal.transports.telnet import IAC, TelnetTransport


class TestTelnetTransportConnect:
    async def test_connect_and_receive(self) -> None:
        async with MockTelnetServer(send=b"hello") as srv:
            t = TelnetTransport()
            await t.connect("127.0.0.1", srv.port)
            assert t.is_connected()
            await t.disconnect()
        assert not t.is_connected()

    async def test_not_connected_raises(self) -> None:
        t = TelnetTransport()
        with pytest.raises(ConnectionError):
            await t.send(b"test")

    async def test_receive_not_connected_raises(self) -> None:
        t = TelnetTransport()
        with pytest.raises(ConnectionError):
            await t.receive(128, 100)


async def _read_until(
    reader: asyncio.StreamReader,
    needle: bytes,
    *,
    max_bytes: int = 512,
    timeout: float = 2.0,
) -> bytes:
    """Accumulate bytes from *reader* until *needle* is found or timeout expires.

    TelnetTransport sends Telnet option negotiation bytes (IAC sequences) as a
    separate write from the actual payload.  A single ``reader.read(n)`` call can
    therefore return only the negotiation bytes, causing tests to miss the payload.
    This helper keeps reading until it either finds the expected content or times out.
    """
    data = bytearray()
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline and len(data) < max_bytes:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            break
        try:
            chunk = await asyncio.wait_for(reader.read(max_bytes), timeout=min(remaining, 0.1))
        except TimeoutError:
            if needle in data:
                break
            continue
        if not chunk:
            break
        data.extend(chunk)
        if needle in data:
            break
    return bytes(data)


class TestTelnetTransportSend:
    async def test_iac_escaping(self) -> None:
        """0xFF bytes in data must be escaped to 0xFF 0xFF."""
        wire_data: bytes = b""
        ready = asyncio.Event()

        async def _handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            nonlocal wire_data
            wire_data = await _read_until(reader, b"\xff\xff")
            writer.close()
            ready.set()

        server = await asyncio.start_server(_handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]  # type: ignore[index]
        try:
            t = TelnetTransport()
            await t.connect("127.0.0.1", port)
            await t.send(b"\xff\x00\xff")
            await asyncio.wait_for(ready.wait(), timeout=2.0)
        finally:
            server.close()
            await server.wait_closed()

        # Both 0xFF bytes should be doubled on the wire
        assert b"\xff\xff" in wire_data

    async def test_send_plain_data(self) -> None:
        wire_data: bytes = b""
        ready = asyncio.Event()

        async def _handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            nonlocal wire_data
            wire_data = await _read_until(reader, b"ping")
            writer.close()
            ready.set()

        server = await asyncio.start_server(_handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]  # type: ignore[index]
        try:
            t = TelnetTransport()
            await t.connect("127.0.0.1", port)
            await t.send(b"ping")
            await asyncio.wait_for(ready.wait(), timeout=2.0)
        finally:
            server.close()
            await server.wait_closed()

        assert b"ping" in wire_data


class TestTelnetTransportNAWS:
    async def test_set_size_when_not_connected_raises(self) -> None:
        t = TelnetTransport()
        with pytest.raises(ConnectionError):
            await t.set_size(80, 25)

    async def test_set_size_sends_naws(self) -> None:
        """Verify that set_size sends the NAWS subnegotiation bytes."""
        received: list[bytes] = []
        ready = asyncio.Event()

        naws_marker = bytes([IAC, 250, 31])  # IAC SB NAWS

        async def _handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            data = await _read_until(reader, naws_marker)
            received.append(data)
            writer.close()
            ready.set()

        server = await asyncio.start_server(_handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]  # type: ignore[index]
        try:
            t = TelnetTransport()
            await t.connect("127.0.0.1", port)
            await t.set_size(132, 50)
            await asyncio.wait_for(ready.wait(), timeout=2.0)
        finally:
            server.close()
            await server.wait_closed()

        # NAWS bytes: IAC SB 31 (cols_hi cols_lo rows_hi rows_lo) IAC SE
        wire = received[0]
        assert naws_marker in wire


class TestTelnetTransportIACParsing:
    def test_parse_telnet_buffer_plain_data(self) -> None:
        data = b"Hello World"
        payload, events, consumed = TelnetTransport._parse_telnet_buffer(data)
        assert payload == b"Hello World"
        assert events == []
        assert consumed == len(data)

    def test_parse_telnet_buffer_escaped_iac(self) -> None:
        data = bytes([IAC, IAC])
        payload, events, consumed = TelnetTransport._parse_telnet_buffer(data)
        assert payload == bytes([IAC])
        assert events == []

    def test_parse_telnet_buffer_negotiate(self) -> None:
        from undef.terminal.transports.telnet import DO, ECHO

        data = bytes([IAC, DO, ECHO])
        payload, events, consumed = TelnetTransport._parse_telnet_buffer(data)
        assert payload == b""
        assert len(events) == 1
        assert events[0] == ("negotiate", DO, ECHO)

    def test_parse_telnet_buffer_incomplete(self) -> None:
        """Incomplete IAC sequence should not be consumed."""
        data = bytes([IAC])
        payload, events, consumed = TelnetTransport._parse_telnet_buffer(data)
        assert payload == b""
        assert consumed == 0
