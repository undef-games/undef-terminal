#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Tests for TelnetWsGateway and _make_process_handler."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from undef.terminal.gateway._gateway import (
    TelnetWsGateway,
    _make_process_handler,
)


def _make_ws_context(ws_mock: AsyncMock) -> MagicMock:
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=ws_mock)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# _make_process_handler
# ---------------------------------------------------------------------------


class TestMakeProcessHandler:
    async def test_returns_callable(self) -> None:
        handler = await _make_process_handler("ws://test", None, "passthrough")
        assert callable(handler)

    async def test_handler_connects_and_pipes(self) -> None:
        handler = await _make_process_handler("ws://test", None, "passthrough")

        process = MagicMock()
        process.stdin = AsyncMock()
        process.stdin.read = AsyncMock(return_value=b"")
        process.stdout = MagicMock()
        process.exit = MagicMock()

        ws_mock = AsyncMock()
        ws_mock.__aiter__ = MagicMock(return_value=iter([]))
        ws_mock.send = AsyncMock()

        mock_ws_mod = MagicMock()
        mock_ws_mod.connect.return_value = _make_ws_context(ws_mock)

        with patch.dict("sys.modules", {"websockets": mock_ws_mod}):
            await handler(process)

        process.exit.assert_called_once_with(0)

    async def test_handler_with_resume_token(self, tmp_path: Path) -> None:
        tf = tmp_path / "token"
        tf.write_text("resume_tok")
        handler = await _make_process_handler("ws://test", tf, "passthrough")

        process = MagicMock()
        process.stdin = AsyncMock()
        process.stdin.read = AsyncMock(return_value=b"")
        process.stdout = MagicMock()
        process.exit = MagicMock()

        ws_mock = AsyncMock()
        ws_mock.__aiter__ = MagicMock(return_value=iter([]))
        ws_mock.send = AsyncMock()

        mock_ws_mod = MagicMock()
        mock_ws_mod.connect.return_value = _make_ws_context(ws_mock)

        with patch.dict("sys.modules", {"websockets": mock_ws_mod}):
            await handler(process)

        # First send should be resume
        first = ws_mock.send.call_args_list[0][0][0]
        assert "resume" in first

    async def test_handler_exception_calls_exit(self) -> None:
        handler = await _make_process_handler("ws://test", None, "passthrough")

        process = MagicMock()
        process.stdin = AsyncMock()
        process.stdout = MagicMock()
        process.exit = MagicMock()

        mock_ws_mod = MagicMock()
        mock_ws_mod.connect.side_effect = OSError("connection refused")

        with patch.dict("sys.modules", {"websockets": mock_ws_mod}):
            await handler(process)

        process.exit.assert_called_once_with(0)

    async def test_handler_exit_exception_suppressed(self) -> None:
        handler = await _make_process_handler("ws://test", None, "passthrough")

        process = MagicMock()
        process.stdin = AsyncMock()
        process.stdout = MagicMock()
        process.exit = MagicMock(side_effect=RuntimeError("exit failed"))

        mock_ws_mod = MagicMock()
        mock_ws_mod.connect.side_effect = OSError("fail")

        with patch.dict("sys.modules", {"websockets": mock_ws_mod}):
            # Should not raise despite exit() raising
            await handler(process)


# ---------------------------------------------------------------------------
# TelnetWsGateway
# ---------------------------------------------------------------------------


class TestTelnetWsGateway:
    def test_init(self) -> None:
        gw = TelnetWsGateway("ws://test")
        assert gw._ws_url == "ws://test"
        assert gw._color_mode == "passthrough"
        assert gw._token_file is None

    def test_init_with_options(self, tmp_path: Path) -> None:
        tf = tmp_path / "token"
        gw = TelnetWsGateway("ws://test", token_file=tf, color_mode="256")
        assert gw._token_file == tf
        assert gw._color_mode == "256"

    async def test_start_returns_server(self) -> None:
        gw = TelnetWsGateway("ws://test")
        server = await gw.start("127.0.0.1", 0)
        try:
            assert isinstance(server, asyncio.AbstractServer)
        finally:
            server.close()
            await server.wait_closed()

    async def test_handle_reconnects_on_ws_drop(self) -> None:
        gw = TelnetWsGateway("ws://test")

        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = MagicMock(spec=asyncio.StreamWriter)
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        # First call: ws fails (reader not at eof), second call: reader at eof
        call_count = 0

        async def mock_pipe_ws(*args: Any, **kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("ws dropped")

        reader.at_eof = MagicMock(side_effect=[False, False, True])

        with (
            patch("undef.terminal.gateway._gateway._pipe_ws", side_effect=mock_pipe_ws),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await gw._handle(reader, writer)

        assert call_count == 2
        writer.close.assert_called_once()

    async def test_handle_stops_when_reader_eof_initially(self) -> None:
        gw = TelnetWsGateway("ws://test")

        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.at_eof = MagicMock(return_value=True)
        writer = MagicMock(spec=asyncio.StreamWriter)
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with patch("undef.terminal.gateway._gateway._pipe_ws", new_callable=AsyncMock) as mock_pipe:
            await gw._handle(reader, writer)
            mock_pipe.assert_not_called()

    async def test_handle_stops_when_reader_eof_after_pipe(self) -> None:
        gw = TelnetWsGateway("ws://test")

        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = MagicMock(spec=asyncio.StreamWriter)
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        # First at_eof: False (enter loop), pipe runs, second at_eof: True
        reader.at_eof = MagicMock(side_effect=[False, True])

        with patch("undef.terminal.gateway._gateway._pipe_ws", new_callable=AsyncMock):
            await gw._handle(reader, writer)

        writer.close.assert_called_once()

    async def test_handle_exhausts_reconnects(self) -> None:
        gw = TelnetWsGateway("ws://test")

        reader = AsyncMock(spec=asyncio.StreamReader)
        # Never at EOF — force all reconnect attempts
        reader.at_eof = MagicMock(return_value=False)
        writer = MagicMock(spec=asyncio.StreamWriter)
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with (
            patch(
                "undef.terminal.gateway._gateway._pipe_ws",
                new_callable=AsyncMock,
                side_effect=ConnectionError("fail"),
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await gw._handle(reader, writer)

        writer.close.assert_called_once()

    async def test_handle_cleanup_on_writer_error(self) -> None:
        gw = TelnetWsGateway("ws://test")

        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.at_eof = MagicMock(return_value=True)
        writer = MagicMock(spec=asyncio.StreamWriter)
        writer.close = MagicMock(side_effect=RuntimeError("close failed"))
        writer.wait_closed = AsyncMock()

        # Should not raise
        await gw._handle(reader, writer)
