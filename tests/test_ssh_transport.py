#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Tests for SSHStreamReader and SSHStreamWriter (mock asyncssh process)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("asyncssh", reason="asyncssh not installed; skip SSH transport tests")

from undef.terminal.transports.ssh import SSHStreamReader, SSHStreamWriter  # noqa: E402


class MockStdin:
    def __init__(self, data: bytes | str) -> None:
        self._data = data

    async def read(self, n: int = -1) -> bytes | str:
        return self._data


class MockStdout:
    def __init__(self) -> None:
        self.written: bytearray = bytearray()

    def write(self, data: bytes) -> None:
        self.written.extend(data)

    async def drain(self) -> None:
        pass


class MockProcess:
    def __init__(self, stdin_data: bytes | str = b"") -> None:
        self.stdin = MockStdin(stdin_data)
        self.stdout = MockStdout()
        self._exited = False
        self._closed = False

    def exit(self, code: int) -> None:
        self._exited = True

    def close(self) -> None:
        self._closed = True

    def get_extra_info(self, name: str) -> object:
        if name == "peername":
            return ("127.0.0.1", 12345)
        return None


class TestSSHStreamReader:
    async def test_read_bytes(self) -> None:
        proc = MockProcess(stdin_data=b"hello")
        reader = SSHStreamReader(proc)
        data = await reader.read(5)
        assert data == b"hello"

    async def test_read_str_encodes_latin1(self) -> None:
        proc = MockProcess(stdin_data="hello")
        reader = SSHStreamReader(proc)
        data = await reader.read(5)
        assert data == b"hello"

    async def test_read_on_error_returns_empty(self) -> None:
        import asyncssh

        proc = MockProcess()
        proc.stdin = MagicMock()
        proc.stdin.read = AsyncMock(side_effect=asyncssh.Error("test", "msg", 0))
        reader = SSHStreamReader(proc)
        data = await reader.read(5)
        assert data == b""


class TestSSHStreamWriter:
    def test_write_passes_bytes(self) -> None:
        proc = MockProcess()
        writer = SSHStreamWriter(proc)
        writer.write(b"test data")
        assert bytes(proc.stdout.written) == b"test data"

    def test_write_after_close_is_noop(self) -> None:
        proc = MockProcess()
        writer = SSHStreamWriter(proc)
        writer.close()
        writer.write(b"ignored")
        assert bytes(proc.stdout.written) == b""

    async def test_drain_flushes(self) -> None:
        proc = MockProcess()
        writer = SSHStreamWriter(proc)
        writer.write(b"data")
        await writer.drain()  # should not raise

    def test_get_extra_info_peername(self) -> None:
        proc = MockProcess()
        writer = SSHStreamWriter(proc)
        peer = writer.get_extra_info("peername")
        assert peer == ("127.0.0.1", 12345)

    def test_get_extra_info_unknown(self) -> None:
        proc = MockProcess()
        writer = SSHStreamWriter(proc)
        assert writer.get_extra_info("unknown", "default") == "default"

    def test_close_exits_process(self) -> None:
        proc = MockProcess()
        writer = SSHStreamWriter(proc)
        writer.close()
        assert proc._exited
