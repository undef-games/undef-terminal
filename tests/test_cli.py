#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Tests for undef.terminal.cli (uterm entry point)."""

from __future__ import annotations

import asyncio
import contextlib
import sys
from unittest.mock import MagicMock, patch

import pytest

from undef.terminal.cli import _build_parser, main

# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestParser:
    def test_proxy_minimal(self) -> None:
        args = _build_parser().parse_args(["proxy", "bbs.example.com", "23"])
        assert args.host == "bbs.example.com"
        assert args.bbs_port == 23
        assert args.port == 8765
        assert args.bind == "0.0.0.0"
        assert args.path == "/ws/terminal"
        assert args.transport == "telnet"

    def test_proxy_all_options(self) -> None:
        args = _build_parser().parse_args([
            "proxy", "bbs.example.com", "23",
            "--port", "9000",
            "--bind", "127.0.0.1",
            "--path", "/ws/bbs",
            "--transport", "ssh",
        ])
        assert args.port == 9000
        assert args.bind == "127.0.0.1"
        assert args.path == "/ws/bbs"
        assert args.transport == "ssh"

    def test_proxy_short_port_flag(self) -> None:
        args = _build_parser().parse_args(["proxy", "host", "23", "-p", "1234"])
        assert args.port == 1234

    def test_no_subcommand_exits(self) -> None:
        with pytest.raises(SystemExit):
            _build_parser().parse_args([])

    def test_invalid_transport_exits(self) -> None:
        with pytest.raises(SystemExit):
            _build_parser().parse_args(["proxy", "host", "23", "--transport", "ftp"])

    def test_bbs_port_must_be_int(self) -> None:
        with pytest.raises(SystemExit):
            _build_parser().parse_args(["proxy", "host", "notanint"])


# ---------------------------------------------------------------------------
# _cmd_proxy tests (mock uvicorn so we don't actually start a server)
# ---------------------------------------------------------------------------


class TestCmdProxy:
    def _make_args(self, **overrides):
        args = _build_parser().parse_args(["proxy", "bbs.example.com", "23"])
        for k, v in overrides.items():
            setattr(args, k, v)
        return args

    def test_proxy_calls_uvicorn_run(self) -> None:
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            main(["proxy", "bbs.example.com", "23"])

        mock_uvicorn.run.assert_called_once()
        call_kwargs = mock_uvicorn.run.call_args
        assert call_kwargs.kwargs["host"] == "0.0.0.0"
        assert call_kwargs.kwargs["port"] == 8765

    def test_proxy_custom_port_and_bind(self) -> None:
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            main(["proxy", "bbs.example.com", "23", "--port", "9000", "--bind", "127.0.0.1"])

        call_kwargs = mock_uvicorn.run.call_args
        assert call_kwargs.kwargs["host"] == "127.0.0.1"
        assert call_kwargs.kwargs["port"] == 9000

    def test_proxy_app_has_ws_route(self) -> None:
        """The FastAPI app passed to uvicorn includes the WS router."""
        captured_app = {}
        mock_uvicorn = MagicMock(side_effect=lambda app, **kw: captured_app.update({"app": app}))
        mock_uv_mod = MagicMock()
        mock_uv_mod.run = mock_uvicorn

        with patch.dict("sys.modules", {"uvicorn": mock_uv_mod}):
            main(["proxy", "bbs.example.com", "23", "--path", "/ws/bbs"])

        app = captured_app["app"]
        routes = {r.path for r in app.routes}
        assert "/ws/bbs" in routes

    def test_missing_uvicorn_exits(self) -> None:
        """SystemExit(1) when uvicorn is not installed."""
        original = sys.modules.get("uvicorn")
        sys.modules["uvicorn"] = None  # type: ignore[assignment]
        try:
            with pytest.raises(SystemExit) as exc_info:
                main(["proxy", "bbs.example.com", "23"])
            assert exc_info.value.code == 1
        finally:
            if original is None:
                sys.modules.pop("uvicorn", None)
            else:
                sys.modules["uvicorn"] = original

    def test_ssh_transport_selected(self) -> None:
        """--transport ssh uses SSHTransport, or exits cleanly if asyncssh missing."""
        mock_uvicorn = MagicMock()
        mock_ssh_module = MagicMock()
        mock_ssh_module.SSHTransport = MagicMock()
        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn, "undef.terminal.transports.ssh": mock_ssh_module}),
        ):
            # Just verify the SSH branch is exercised without raising unexpectedly
            try:
                main(["proxy", "bbs.example.com", "22", "--transport", "ssh"])
            except SystemExit as exc:
                assert exc.code == 1  # only acceptable exit is missing-dep


# ---------------------------------------------------------------------------
# listen subcommand parser tests
# ---------------------------------------------------------------------------


class TestListenParser:
    def test_listen_minimal(self) -> None:
        args = _build_parser().parse_args(["listen", "wss://warp.undef.games/ws/terminal"])
        assert args.ws_url == "wss://warp.undef.games/ws/terminal"
        assert args.port == 2112
        assert args.ssh_port == 0
        assert args.bind == "0.0.0.0"
        assert args.server_key is None

    def test_listen_all_options(self) -> None:
        args = _build_parser().parse_args([
            "listen", "wss://example.com/ws",
            "--port", "2323",
            "--ssh-port", "2222",
            "--bind", "127.0.0.1",
            "--server-key", "/etc/host_key",
        ])
        assert args.port == 2323
        assert args.ssh_port == 2222
        assert args.bind == "127.0.0.1"
        assert args.server_key == "/etc/host_key"

    def test_listen_short_port(self) -> None:
        args = _build_parser().parse_args(["listen", "ws://localhost/ws", "-p", "9999"])
        assert args.port == 9999

    def test_listen_disable_telnet(self) -> None:
        args = _build_parser().parse_args(["listen", "ws://localhost/ws", "--port", "0"])
        assert args.port == 0

    def test_listen_missing_url_exits(self) -> None:
        with pytest.raises(SystemExit):
            _build_parser().parse_args(["listen"])


# ---------------------------------------------------------------------------
# _cmd_listen tests
# ---------------------------------------------------------------------------


class TestCmdListen:
    async def test_listen_starts_telnet_gateway(self) -> None:
        """_run_listen starts a TCP server and can be cancelled cleanly."""
        import websockets

        async def _handler(ws) -> None:
            await ws.send("hi")

        ws_srv = await websockets.serve(_handler, "127.0.0.1", 0)
        ws_port = ws_srv.sockets[0].getsockname()[1]
        ws_url = f"ws://127.0.0.1:{ws_port}"
        try:
            from undef.terminal.cli import _run_listen
            from undef.terminal.gateway import SshWsGateway, TelnetWsGateway

            task = asyncio.create_task(
                _run_listen(ws_url, "127.0.0.1", 0, 0, None, TelnetWsGateway, SshWsGateway)
            )
            await asyncio.sleep(0)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, SystemExit):
                await task
        finally:
            ws_srv.close()

    async def test_listen_e2e_telnet_client(self) -> None:
        """Full pipe: telnet client → TelnetWsGateway → WS echo server."""
        import websockets

        banner = b"gateway works!\r\n"

        async def _handler(ws) -> None:
            await ws.send(banner.decode("latin-1"))
            async for msg in ws:
                await ws.send(msg)

        ws_srv = await websockets.serve(_handler, "127.0.0.1", 0)
        ws_port = ws_srv.sockets[0].getsockname()[1]
        try:
            from undef.terminal.gateway import TelnetWsGateway

            gw = TelnetWsGateway(f"ws://127.0.0.1:{ws_port}")
            tcp_srv = await gw.start("127.0.0.1", 0)
            tcp_port = tcp_srv.sockets[0].getsockname()[1]

            reader, writer = await asyncio.open_connection("127.0.0.1", tcp_port)
            data = await asyncio.wait_for(reader.read(256), timeout=2.0)
            writer.close()
            tcp_srv.close()
        finally:
            ws_srv.close()

        assert b"gateway works!" in data
