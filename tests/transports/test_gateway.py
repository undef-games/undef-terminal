#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Tests for undef.terminal.gateway — TelnetWsGateway (and helpers)."""

from __future__ import annotations

import asyncio

import pytest
import websockets
import websockets.server

from undef.terminal.gateway import (
    TelnetWsGateway,
    _apply_color_mode,
    _delete_token,
    _handle_ws_control,
    _normalize_crlf,
    _pipe_ws,
    _read_token,
    _strip_iac,
    _tcp_to_ws,
    _write_token,
    _ws_to_tcp,
)

# ---------------------------------------------------------------------------
# Pump helper unit tests
# ---------------------------------------------------------------------------


class TestTcpToWs:
    async def test_forwards_bytes_as_text(self) -> None:
        sent: list[str] = []

        class MockWs:
            async def send(self, data: str) -> None:
                sent.append(data)

        reader = asyncio.StreamReader()
        reader.feed_data(b"hello")
        reader.feed_eof()

        await _tcp_to_ws(reader, MockWs())
        assert sent == ["hello"]

    async def test_stops_on_eof(self) -> None:
        sent: list[str] = []

        class MockWs:
            async def send(self, data: str) -> None:
                sent.append(data)

        reader = asyncio.StreamReader()
        reader.feed_eof()

        await _tcp_to_ws(reader, MockWs())
        assert sent == []


def _async_iter(items):
    """Return an async iterator over *items*."""

    async def _gen():
        for item in items:
            yield item

    return _gen()


class TestWsToTcp:
    async def test_forwards_str_message(self) -> None:
        written: list[bytes] = []
        drained: list[bool] = []

        class MockWriter:
            def write(self, data: bytes) -> None:
                written.append(data)

            async def drain(self) -> None:
                drained.append(True)

        from asyncio import StreamWriter
        from typing import cast

        await _ws_to_tcp(_async_iter(["world"]), cast("StreamWriter", MockWriter()))
        assert written == [b"world"]
        assert drained

    async def test_forwards_bytes_message(self) -> None:
        written: list[bytes] = []

        class MockWriter:
            def write(self, data: bytes) -> None:
                written.append(data)

            async def drain(self) -> None:
                pass

        from asyncio import StreamWriter
        from typing import cast

        await _ws_to_tcp(_async_iter([b"\xff\xfe"]), cast("StreamWriter", MockWriter()))
        assert written == [b"\xff\xfe"]


# ---------------------------------------------------------------------------
# TelnetWsGateway — integration via real local WS server
# ---------------------------------------------------------------------------


from typing import Any


async def _start_ws_echo_server(banner: bytes = b"") -> tuple[Any, int]:
    """Start a local WebSocket server that optionally sends a banner then echoes."""

    async def handler(ws: websockets.ServerConnection) -> None:
        if banner:
            await ws.send(banner.decode("latin-1"))
        async for msg in ws:
            await ws.send(msg)

    srv = await websockets.serve(handler, "127.0.0.1", 0)
    port = srv.sockets[0].getsockname()[1]
    return srv, port


class TestTelnetWsGateway:
    async def test_start_returns_server(self) -> None:
        ws_srv, ws_port = await _start_ws_echo_server()
        try:
            gw = TelnetWsGateway(f"ws://127.0.0.1:{ws_port}")
            tcp_srv = await gw.start("127.0.0.1", 0)
            assert tcp_srv is not None
            tcp_srv.close()
        finally:
            ws_srv.close()

    async def test_banner_forwarded_to_telnet_client(self) -> None:
        """Data sent by the WS server arrives at the telnet client."""
        banner = b"Welcome to warp!\r\n"
        ws_srv, ws_port = await _start_ws_echo_server(banner=banner)
        try:
            gw = TelnetWsGateway(f"ws://127.0.0.1:{ws_port}")
            tcp_srv = await gw.start("127.0.0.1", 0)
            from asyncio import Server

            assert isinstance(tcp_srv, Server)
            assert tcp_srv.sockets is not None
            tcp_port = tcp_srv.sockets[0].getsockname()[1]

            reader, writer = await asyncio.open_connection("127.0.0.1", tcp_port)
            data = await asyncio.wait_for(reader.read(256), timeout=2.0)
            writer.close()
            tcp_srv.close()
        finally:
            ws_srv.close()

        assert banner.decode("utf-8") in data.decode("utf-8")

    async def test_client_data_forwarded_to_ws(self) -> None:
        """Data sent by the telnet client is echoed back via the WS server."""
        ws_srv, ws_port = await _start_ws_echo_server()
        try:
            gw = TelnetWsGateway(f"ws://127.0.0.1:{ws_port}")
            tcp_srv = await gw.start("127.0.0.1", 0)
            from asyncio import Server

            assert isinstance(tcp_srv, Server)
            assert tcp_srv.sockets is not None
            tcp_port = tcp_srv.sockets[0].getsockname()[1]

            reader, writer = await asyncio.open_connection("127.0.0.1", tcp_port)
            writer.write(b"ping")
            await writer.drain()
            data = await asyncio.wait_for(reader.read(256), timeout=2.0)
            writer.close()
            tcp_srv.close()
        finally:
            ws_srv.close()

        assert b"ping" in data

    async def test_disconnect_cleans_up(self) -> None:
        """Closing the telnet client closes cleanly without hanging."""
        ws_srv, ws_port = await _start_ws_echo_server()
        try:
            gw = TelnetWsGateway(f"ws://127.0.0.1:{ws_port}")
            tcp_srv = await gw.start("127.0.0.1", 0)
            from asyncio import Server

            assert isinstance(tcp_srv, Server)
            assert tcp_srv.sockets is not None
            tcp_port = tcp_srv.sockets[0].getsockname()[1]

            reader, writer = await asyncio.open_connection("127.0.0.1", tcp_port)
            writer.close()
            # Brief pause to let gateway detect disconnect
            await asyncio.sleep(0.1)
            tcp_srv.close()
        finally:
            ws_srv.close()

    async def test_missing_websockets_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import sys

        original = sys.modules.get("websockets")
        sys.modules["websockets"] = None  # type: ignore[assignment]
        try:
            with pytest.raises(ImportError, match="websockets"):
                TelnetWsGateway("ws://localhost:9999")
        finally:
            if original is None:
                sys.modules.pop("websockets", None)
            else:
                sys.modules["websockets"] = original


# ---------------------------------------------------------------------------
# _pipe_ws integration
# ---------------------------------------------------------------------------


class TestPipeWs:
    async def test_pipe_ws_connects_and_exits_on_eof(self) -> None:
        """_pipe_ws connects to a WS server and exits cleanly when reader hits EOF."""
        ws_srv, ws_port = await _start_ws_echo_server()
        try:
            reader = asyncio.StreamReader()
            reader.feed_eof()  # immediate EOF → _tcp_to_ws exits quickly

            class MockWriter:
                def write(self, data: bytes) -> None:
                    pass

                async def drain(self) -> None:
                    pass

                def close(self) -> None:
                    pass

                async def wait_closed(self) -> None:
                    pass

            # Should complete without hanging
            from asyncio import StreamWriter
            from typing import cast

            await asyncio.wait_for(
                _pipe_ws(reader, cast("StreamWriter", MockWriter()), f"ws://127.0.0.1:{ws_port}"),
                timeout=3.0,
            )
        finally:
            ws_srv.close()


class TestSshWsGatewayInit:
    def test_init_requires_asyncssh(self) -> None:
        """SshWsGateway can be created when asyncssh is available."""
        import asyncssh  # noqa: F401

        from undef.terminal.gateway import SshWsGateway

        gw = SshWsGateway("wss://example.com/ws")
        assert gw._ws_url == "wss://example.com/ws"
        assert gw._server_key is None

    def test_init_with_server_key(self, tmp_path) -> None:
        from undef.terminal.gateway import SshWsGateway

        key_path = tmp_path / "key.pem"
        key_path.write_text("dummy")
        gw = SshWsGateway("wss://example.com/ws", server_key=str(key_path))
        assert gw._server_key == str(key_path)


class TestSshWsGatewayStart:
    async def test_start_ephemeral_key(self) -> None:
        """SshWsGateway.start() creates an asyncssh server with ephemeral key."""
        import asyncssh

        from undef.terminal.gateway import SshWsGateway

        gw = SshWsGateway("wss://example.com/ws")
        srv = await gw.start("127.0.0.1", 0)
        assert isinstance(srv, asyncssh.SSHAcceptor)
        try:
            pass
        finally:
            srv.close()
            await srv.wait_closed()

    async def test_start_with_file_key(self, tmp_path) -> None:
        """SshWsGateway.start() loads a host key from file when provided."""
        import asyncssh

        from undef.terminal.gateway import SshWsGateway

        key = asyncssh.generate_private_key("ssh-ed25519")
        key_path = tmp_path / "host_key"
        key_path.write_bytes(key.export_private_key())

        gw = SshWsGateway("wss://example.com/ws", server_key=str(key_path))
        srv = await gw.start("127.0.0.1", 0)
        import asyncssh

        assert isinstance(srv, asyncssh.SSHAcceptor)
        try:
            pass
        finally:
            srv.close()
            await srv.wait_closed()

    async def test_start_missing_key_file_raises(self, tmp_path) -> None:
        """SshWsGateway.start() raises FileNotFoundError for a missing key path."""
        from undef.terminal.gateway import SshWsGateway

        gw = SshWsGateway("wss://example.com/ws", server_key=str(tmp_path / "no_such_key"))
        with pytest.raises(FileNotFoundError, match="SSH host key not found"):
            await gw.start("127.0.0.1", 0)

    async def test_start_key_path_is_directory_raises(self, tmp_path) -> None:
        """SshWsGateway.start() raises ValueError when key path is a directory."""
        from undef.terminal.gateway import SshWsGateway

        gw = SshWsGateway("wss://example.com/ws", server_key=str(tmp_path))
        with pytest.raises(ValueError, match="not a file"):
            await gw.start("127.0.0.1", 0)


class TestSshToWs:
    async def test_ssh_to_ws_str_data(self) -> None:
        from undef.terminal.gateway import _ssh_to_ws

        sent = []

        class _MockWs:
            async def send(self, data: object) -> None:
                sent.append(data)

        class _MockStdin:
            def __init__(self) -> None:
                self._data = ["hello", ""]

            async def read(self, n: int) -> str:
                return self._data.pop(0)

        class _MockProcess:
            stdin = _MockStdin()

        await _ssh_to_ws(_MockProcess(), _MockWs())
        assert sent == ["hello"]

    async def test_ssh_to_ws_bytes_data(self) -> None:
        from undef.terminal.gateway import _ssh_to_ws

        sent = []

        class _MockWs:
            async def send(self, data: object) -> None:
                sent.append(data)

        class _MockStdin:
            def __init__(self) -> None:
                self._data = [b"hello", b""]

            async def read(self, n: int) -> bytes:
                return self._data.pop(0)

        class _MockProcess:
            stdin = _MockStdin()

        await _ssh_to_ws(_MockProcess(), _MockWs())
        assert "hello" in sent[0]

    async def test_ssh_to_ws_exception_exits(self) -> None:
        from undef.terminal.gateway import _ssh_to_ws

        class _MockWs:
            async def send(self, data: object) -> None:
                pass

        class _MockStdin:
            async def read(self, n: int) -> bytes:
                raise RuntimeError("broken")

        class _MockProcess:
            stdin = _MockStdin()

        # Should exit cleanly without raising
        await _ssh_to_ws(_MockProcess(), _MockWs())


class TestWsToSsh:
    async def test_ws_to_ssh_str_message(self) -> None:
        from undef.terminal.gateway import _ws_to_ssh

        written = []

        class _MockStdout:
            def write(self, data: object) -> None:
                written.append(data)

        class _MockProcess:
            stdout = _MockStdout()

        async def _gen():
            yield "hello"

        await _ws_to_ssh(_gen(), _MockProcess())
        assert "hello" in written

    async def test_ws_to_ssh_bytes_message(self) -> None:
        from undef.terminal.gateway import _ws_to_ssh

        written = []

        class _MockStdout:
            def write(self, data: object) -> None:
                written.append(data)

        class _MockProcess:
            stdout = _MockStdout()

        async def _gen():
            yield b"world"

        await _ws_to_ssh(_gen(), _MockProcess())
        assert "world" in written[0]


class TestTelnetWsGatewayHandleException:
    async def test_handle_exception_closes_writer(self) -> None:
        """_handle closes writer even when _pipe_ws raises."""
        from unittest.mock import AsyncMock, MagicMock, patch

        gw = TelnetWsGateway("ws://localhost")
        reader = MagicMock()
        writer = MagicMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with patch("undef.terminal.gateway._pipe_ws", side_effect=RuntimeError("boom")):
            await gw._handle(reader, writer)

        writer.close.assert_called()


# ---------------------------------------------------------------------------
# Token file helpers
# ---------------------------------------------------------------------------


class TestTokenFileHelpers:
    def test_read_missing_returns_none(self, tmp_path) -> None:
        assert _read_token(tmp_path / "no_such_file") is None

    def test_write_then_read(self, tmp_path) -> None:
        p = tmp_path / "token"
        _write_token(p, "mytoken")
        assert _read_token(p) == "mytoken"

    def test_write_empty_returns_none(self, tmp_path) -> None:
        p = tmp_path / "token"
        _write_token(p, "")
        assert _read_token(p) is None

    def test_write_creates_parent_dirs(self, tmp_path) -> None:
        p = tmp_path / "nested" / "dir" / "token"
        _write_token(p, "abc")
        assert p.read_text() == "abc"

    def test_delete_existing(self, tmp_path) -> None:
        p = tmp_path / "token"
        p.write_text("x")
        _delete_token(p)
        assert not p.exists()

    def test_delete_missing_no_raise(self, tmp_path) -> None:
        _delete_token(tmp_path / "no_such_file")  # must not raise


# ---------------------------------------------------------------------------
# JSON control message handler
# ---------------------------------------------------------------------------


class TestHandleWsControl:
    async def test_session_token_saves_file_and_returns_true(self, tmp_path) -> None:
        token_file = tmp_path / "tok"
        written: list[bytes] = []

        async def _write_fn(data: bytes) -> None:
            written.append(data)

        result = await _handle_ws_control('{"type": "session_token", "token": "abc123"}', token_file, _write_fn)
        assert result is True
        assert token_file.read_text() == "abc123"
        assert written == []

    async def test_resume_ok_writes_text_and_returns_true(self) -> None:
        written: list[bytes] = []

        async def _write_fn(data: bytes) -> None:
            written.append(data)

        result = await _handle_ws_control('{"type": "resume_ok"}', None, _write_fn)
        assert result is True
        assert b"Session resumed" in written[0]

    async def test_resume_failed_deletes_token_and_returns_true(self, tmp_path) -> None:
        token_file = tmp_path / "tok"
        token_file.write_text("old_token")
        written: list[bytes] = []

        async def _write_fn(data: bytes) -> None:
            written.append(data)

        result = await _handle_ws_control('{"type": "resume_failed"}', token_file, _write_fn)
        assert result is True
        assert not token_file.exists()

    async def test_plain_text_returns_false(self) -> None:
        async def _write_fn(data: bytes) -> None:
            pass

        assert await _handle_ws_control("hello world", None, _write_fn) is False

    async def test_malformed_json_returns_false(self) -> None:
        async def _write_fn(data: bytes) -> None:
            pass

        assert await _handle_ws_control("{not json}", None, _write_fn) is False

    async def test_no_token_file_skips_write(self) -> None:
        """session_token with token_file=None should not write or raise."""

        async def _write_fn(data: bytes) -> None:
            pass

        result = await _handle_ws_control('{"type": "session_token", "token": "x"}', None, _write_fn)
        assert result is False  # token_file is None → skip write

    async def test_resume_failed_no_token_file_no_raise(self) -> None:
        async def _write_fn(data: bytes) -> None:
            pass

        result = await _handle_ws_control('{"type": "resume_failed"}', None, _write_fn)
        assert result is True


# ---------------------------------------------------------------------------
# _ws_to_tcp — resume/control integration
# ---------------------------------------------------------------------------


def _async_iter(items):
    """Return an async iterator over *items*."""

    async def _gen():
        for item in items:
            yield item

    return _gen()


class TestWsToTcpResume:
    async def test_session_token_intercepted_not_forwarded(self, tmp_path) -> None:
        token_file = tmp_path / "tok"
        written: list[bytes] = []

        class MockWriter:
            def write(self, data: bytes) -> None:
                written.append(data)

            async def drain(self) -> None:
                pass

        from asyncio import StreamWriter
        from typing import cast

        msg = '{"type": "session_token", "token": "tok123"}'
        await _ws_to_tcp(_async_iter([msg]), cast("StreamWriter", MockWriter()), token_file=token_file)
        assert written == []
        assert token_file.read_text() == "tok123"

    async def test_resume_ok_sends_text_to_tcp(self) -> None:
        written: list[bytes] = []

        class MockWriter:
            def write(self, data: bytes) -> None:
                written.append(data)

            async def drain(self) -> None:
                pass

        from asyncio import StreamWriter
        from typing import cast

        await _ws_to_tcp(_async_iter(['{"type": "resume_ok"}']), cast("StreamWriter", MockWriter()))
        assert any(b"Session resumed" in w for w in written)

    async def test_resume_failed_deletes_token(self, tmp_path) -> None:
        token_file = tmp_path / "tok"
        token_file.write_text("old")
        written: list[bytes] = []

        class MockWriter:
            def write(self, data: bytes) -> None:
                written.append(data)

            async def drain(self) -> None:
                pass

        from asyncio import StreamWriter
        from typing import cast

        await _ws_to_tcp(
            _async_iter(['{"type": "resume_failed"}']),
            cast("StreamWriter", MockWriter()),
            token_file=token_file,
        )
        assert not token_file.exists()

    async def test_plain_text_forwarded(self) -> None:
        written: list[bytes] = []

        class MockWriter:
            def write(self, data: bytes) -> None:
                written.append(data)

            async def drain(self) -> None:
                pass

        from asyncio import StreamWriter
        from typing import cast

        await _ws_to_tcp(_async_iter(["hello"]), cast("StreamWriter", MockWriter()))
        assert b"hello" in written[0]


# ---------------------------------------------------------------------------
# _ws_to_tcp — CRLF normalization
# ---------------------------------------------------------------------------


class TestWsToTcpCrlf:
    async def test_bare_lf_becomes_crlf(self) -> None:
        written: list[bytes] = []

        class MockWriter:
            def write(self, data: bytes) -> None:
                written.append(data)

            async def drain(self) -> None:
                pass

        from asyncio import StreamWriter
        from typing import cast

        await _ws_to_tcp(_async_iter(["foo\nbar"]), cast("StreamWriter", MockWriter()))
        assert written[0] == b"foo\r\nbar"

    async def test_existing_crlf_not_doubled(self) -> None:
        written: list[bytes] = []

        class MockWriter:
            def write(self, data: bytes) -> None:
                written.append(data)

            async def drain(self) -> None:
                pass

        from asyncio import StreamWriter
        from typing import cast

        await _ws_to_tcp(_async_iter(["foo\r\nbar"]), cast("StreamWriter", MockWriter()))
        assert written[0] == b"foo\r\nbar"


# ---------------------------------------------------------------------------
# _normalize_crlf unit tests
# ---------------------------------------------------------------------------


class TestNormalizeCrlf:
    def test_bare_lf_converted(self) -> None:
        assert _normalize_crlf(b"a\nb") == b"a\r\nb"

    def test_crlf_not_doubled(self) -> None:
        assert _normalize_crlf(b"a\r\nb") == b"a\r\nb"

    def test_no_newline_unchanged(self) -> None:
        assert _normalize_crlf(b"hello") == b"hello"


# ---------------------------------------------------------------------------
# _ws_to_tcp — color mode
# ---------------------------------------------------------------------------


class TestWsToTcpColorMode:
    async def _collect(self, messages: list, **kwargs) -> bytes:
        written: list[bytes] = []

        class MockWriter:
            def write(self, data: bytes) -> None:
                written.append(data)

            async def drain(self) -> None:
                pass

        from asyncio import StreamWriter
        from typing import cast

        await _ws_to_tcp(_async_iter(messages), cast("StreamWriter", MockWriter()), **kwargs)
        return b"".join(written)

    async def test_passthrough_keeps_rgb(self) -> None:
        msg = "\x1b[38;2;10;20;30mtext\x1b[0m"
        out = await self._collect([msg], color_mode="passthrough")
        assert b"38;2;10;20;30m" in out

    async def test_256_transforms_rgb(self) -> None:
        msg = "\x1b[38;2;10;20;30mtext\x1b[0m"
        out = await self._collect([msg], color_mode="256")
        assert b"38;2;" not in out
        assert b"38;5;" in out

    async def test_16_transforms_rgb(self) -> None:
        msg = "\x1b[38;2;10;20;30mtext\x1b[0m"
        out = await self._collect([msg], color_mode="16")
        assert b"38;2;" not in out
        assert b"38;5;" not in out


# ---------------------------------------------------------------------------
# _apply_color_mode unit tests
# ---------------------------------------------------------------------------


class TestApplyColorMode:
    def test_passthrough_unchanged(self) -> None:
        raw = b"\x1b[38;2;10;20;30mtext\x1b[0m"
        assert _apply_color_mode(raw, "passthrough") == raw

    def test_256_rewrites_rgb_fg(self) -> None:
        raw = b"\x1b[38;2;10;20;30mFG\x1b[0m"
        out = _apply_color_mode(raw, "256")
        assert b"38;2;" not in out
        assert b"38;5;" in out

    def test_256_rewrites_rgb_bg(self) -> None:
        raw = b"\x1b[48;2;200;180;40mBG\x1b[0m"
        out = _apply_color_mode(raw, "256")
        assert b"48;2;" not in out
        assert b"48;5;" in out

    def test_16_rewrites_rgb_fg(self) -> None:
        raw = b"\x1b[38;2;10;20;30mFG\x1b[0m"
        out = _apply_color_mode(raw, "16")
        assert b"38;2;" not in out
        assert b"38;5;" not in out

    def test_16_rewrites_rgb_bg(self) -> None:
        raw = b"\x1b[48;2;200;180;40mBG\x1b[0m"
        out = _apply_color_mode(raw, "16")
        assert b"48;2;" not in out
        assert b"48;5;" not in out


# ---------------------------------------------------------------------------
# _pipe_ws — resume token
# ---------------------------------------------------------------------------


class TestPipeWsResume:
    async def test_token_file_present_sends_resume(self, tmp_path) -> None:
        """When a token file exists, the first WS message should be a resume JSON."""
        received: list[str] = []

        async def handler(ws: websockets.ServerConnection) -> None:
            received.extend([msg if isinstance(msg, str) else msg.decode() async for msg in ws])

        srv = await websockets.serve(handler, "127.0.0.1", 0)
        port = srv.sockets[0].getsockname()[1]
        try:
            token_file = tmp_path / "tok"
            _write_token(token_file, "resume_tok_abc")

            reader = asyncio.StreamReader()
            reader.feed_eof()

            class MockWriter:
                def write(self, data: bytes) -> None:
                    pass

                async def drain(self) -> None:
                    pass

                def close(self) -> None:
                    pass

                async def wait_closed(self) -> None:
                    pass

            from asyncio import StreamWriter
            from typing import cast

            await asyncio.wait_for(
                _pipe_ws(reader, cast("StreamWriter", MockWriter()), f"ws://127.0.0.1:{port}", token_file=token_file),
                timeout=3.0,
            )
        finally:
            srv.close()

        import json

        assert len(received) >= 1
        first = json.loads(received[0])
        assert first == {"type": "resume", "token": "resume_tok_abc"}

    async def test_no_token_file_sends_no_resume(self) -> None:
        """When no token file, no resume message is sent."""
        received: list[str] = []

        async def handler(ws: websockets.ServerConnection) -> None:
            received.extend([msg if isinstance(msg, str) else msg.decode() async for msg in ws])

        srv = await websockets.serve(handler, "127.0.0.1", 0)
        port = srv.sockets[0].getsockname()[1]
        try:
            reader = asyncio.StreamReader()
            reader.feed_eof()

            class MockWriter:
                def write(self, data: bytes) -> None:
                    pass

                async def drain(self) -> None:
                    pass

                def close(self) -> None:
                    pass

                async def wait_closed(self) -> None:
                    pass

            from asyncio import StreamWriter
            from typing import cast

            await asyncio.wait_for(
                _pipe_ws(reader, cast("StreamWriter", MockWriter()), f"ws://127.0.0.1:{port}"),
                timeout=3.0,
            )
        finally:
            srv.close()

        assert received == []


# ---------------------------------------------------------------------------
# IAC stripping
# ---------------------------------------------------------------------------


class TestIacStripping:
    def test_plain_data_unchanged(self) -> None:
        assert _strip_iac(b"hello") == b"hello"

    def test_iac_will_stripped(self) -> None:
        assert _strip_iac(bytes([255, 251, 1]) + b"hi") == b"hi"

    def test_iac_do_stripped(self) -> None:
        assert _strip_iac(bytes([255, 253, 3]) + b"x") == b"x"

    def test_iac_sb_stripped(self) -> None:
        data = bytes([255, 250, 1, 2, 3, 255, 240]) + b"after"
        assert _strip_iac(data) == b"after"

    def test_escaped_iac_preserved(self) -> None:
        assert _strip_iac(bytes([255, 255])) == bytes([255])

    def test_ip_maps_to_ctrl_c(self) -> None:
        assert _strip_iac(bytes([255, 244])) == bytes([0x03])

    def test_eof_maps_to_ctrl_d(self) -> None:
        assert _strip_iac(bytes([255, 236])) == bytes([0x04])

    async def test_telnet_true_strips_iac_in_tcp_to_ws(self) -> None:
        sent: list[str] = []

        class MockWs:
            async def send(self, data: str) -> None:
                sent.append(data)

        reader = asyncio.StreamReader()
        reader.feed_data(bytes([255, 251, 1]) + b"hi")
        reader.feed_eof()

        await _tcp_to_ws(reader, MockWs(), telnet=True)
        assert sent == ["hi"]

    async def test_telnet_false_does_not_strip(self) -> None:
        sent: list[str] = []

        class MockWs:
            async def send(self, data: str) -> None:
                sent.append(data)

        reader = asyncio.StreamReader()
        reader.feed_data(bytes([255, 251, 1]) + b"hi")
        reader.feed_eof()

        await _tcp_to_ws(reader, MockWs(), telnet=False)
        assert sent[0] == bytes([255, 251, 1]).decode("latin-1") + "hi"
