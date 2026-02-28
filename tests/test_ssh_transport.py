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


class TestSSHStreamWriterEdgeCases:
    def test_write_with_os_error_calls_close(self) -> None:
        proc = MockProcess()
        proc.stdout = MagicMock()
        proc.stdout.write = MagicMock(side_effect=OSError("broken pipe"))
        writer = SSHStreamWriter(proc)
        writer.write(b"data")
        assert writer._closed  # error → close called

    async def test_drain_when_closed_noop(self) -> None:
        proc = MockProcess()
        writer = SSHStreamWriter(proc)
        writer._closed = True
        await writer.drain()  # should not raise or call stdout.drain

    async def test_drain_with_os_error_calls_close(self) -> None:
        proc = MockProcess()
        proc.stdout.drain = AsyncMock(side_effect=OSError("broken"))
        writer = SSHStreamWriter(proc)
        await writer.drain()
        assert writer._closed

    def test_get_extra_info_no_peername(self) -> None:
        proc = MockProcess()
        proc.get_extra_info = MagicMock(return_value=None)
        writer = SSHStreamWriter(proc)
        result = writer.get_extra_info("peername")
        assert result is None


class TestTerminalSSHServer:
    def test_connection_made_increments_count(self) -> None:
        from undef.terminal.transports.ssh import TerminalSSHServer, _ip_connections

        _ip_connections.clear()
        server = TerminalSSHServer()
        conn = MagicMock()
        conn.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        server.connection_made(conn)
        assert _ip_connections.get("127.0.0.1", 0) >= 1
        _ip_connections.clear()

    def test_connection_made_rate_limit(self) -> None:
        from undef.terminal.transports.ssh import TerminalSSHServer, _ip_connections

        _ip_connections.clear()
        _ip_connections["10.0.0.1"] = 10  # over limit
        server = TerminalSSHServer()
        conn = MagicMock()
        conn.get_extra_info = MagicMock(return_value=("10.0.0.1", 5678))
        server.connection_made(conn)
        conn.close.assert_called_once()
        _ip_connections.clear()

    def test_connection_made_no_peer(self) -> None:
        from undef.terminal.transports.ssh import TerminalSSHServer, _ip_connections

        _ip_connections.clear()
        server = TerminalSSHServer()
        conn = MagicMock()
        conn.get_extra_info = MagicMock(return_value=None)
        # Should not raise even with no peer info
        server.connection_made(conn)
        _ip_connections.clear()

    def test_connection_lost_decrements_count(self) -> None:
        from undef.terminal.transports.ssh import TerminalSSHServer, _ip_connections

        _ip_connections.clear()
        _ip_connections["127.0.0.1"] = 2
        server = TerminalSSHServer()
        server._peer_ip = "127.0.0.1"
        server.connection_lost(None)
        assert _ip_connections.get("127.0.0.1") == 1
        _ip_connections.clear()

    def test_connection_lost_removes_zero_count(self) -> None:
        from undef.terminal.transports.ssh import TerminalSSHServer, _ip_connections

        _ip_connections.clear()
        _ip_connections["127.0.0.1"] = 1
        server = TerminalSSHServer()
        server._peer_ip = "127.0.0.1"
        server.connection_lost(None)
        assert "127.0.0.1" not in _ip_connections

    def test_connection_lost_unknown_ip_noop(self) -> None:
        from undef.terminal.transports.ssh import TerminalSSHServer, _ip_connections

        _ip_connections.clear()
        server = TerminalSSHServer()
        server._peer_ip = "unknown_ip"
        server.connection_lost(None)  # should not raise

    def test_auth_methods(self) -> None:
        from undef.terminal.transports.ssh import TerminalSSHServer

        server = TerminalSSHServer()
        assert server.begin_auth("user") is True
        assert server.password_auth_supported() is True
        assert server.validate_password("user", "pass") is True
        assert server.public_key_auth_supported() is True
        assert server.validate_public_key("user", MagicMock()) is True


class TestGetOrCreateHostKey:
    def test_creates_new_key(self, tmp_path) -> None:
        from undef.terminal.transports.ssh import _get_or_create_host_key

        key = _get_or_create_host_key(tmp_path)
        assert key is not None
        assert (tmp_path / "ssh_host_key").exists()

    def test_loads_existing_key(self, tmp_path) -> None:
        import asyncssh
        from undef.terminal.transports.ssh import _get_or_create_host_key

        existing_key = asyncssh.generate_private_key("ssh-ed25519")
        (tmp_path / "ssh_host_key").write_bytes(existing_key.export_private_key())

        loaded = _get_or_create_host_key(tmp_path)
        assert loaded is not None

    def test_regenerates_corrupted_key(self, tmp_path) -> None:
        from undef.terminal.transports.ssh import _get_or_create_host_key

        (tmp_path / "ssh_host_key").write_bytes(b"not a valid key")
        key = _get_or_create_host_key(tmp_path)
        assert key is not None


class TestStartSshServer:
    async def test_start_ssh_server_basic(self, tmp_path) -> None:
        from undef.terminal.transports.ssh import start_ssh_server

        async def _handler(reader: object, writer: object) -> None:
            pass

        server = await start_ssh_server(_handler, host="127.0.0.1", port=0, host_key_path=tmp_path)
        try:
            assert server is not None
        finally:
            server.close()
            await server.wait_closed()



class TestGetOrCreateHostKeySaveFailure:
    def test_save_failure_logs_error_and_returns_key(self, tmp_path) -> None:
        """When saving the generated key fails, the key is still returned."""
        import stat
        from undef.terminal.transports.ssh import _get_or_create_host_key

        # Make the directory read-only so key_path.write_bytes() fails
        tmp_path.chmod(stat.S_IRUSR | stat.S_IXUSR)
        try:
            key = _get_or_create_host_key(tmp_path)
            assert key is not None
        finally:
            tmp_path.chmod(stat.S_IRWXU)
