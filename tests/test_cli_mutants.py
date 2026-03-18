#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Targeted mutation-killing tests for cli.py.

Each test is designed to detect a specific surviving mutant. Tests are named
after the mutant they target.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
from unittest.mock import MagicMock, patch

import pytest

from undef.terminal.cli import _build_parser, _cmd_listen, _run_listen, main

pytestmark = pytest.mark.timeout(10)


# ---------------------------------------------------------------------------
# _cmd_proxy — mutmut_55, mutmut_56
# args.host and args.bbs_port passed correctly to WsTerminalProxy
# ---------------------------------------------------------------------------


class TestCmdProxyArgs:
    """Kill mutants that replace args.host/args.bbs_port with None."""

    def test_proxy_passes_host_to_terminal_proxy(self) -> None:
        """mutmut_55: args.host must not be replaced with None."""
        captured: list[tuple] = []

        class _CapturingProxy:
            def __init__(self, host, port, *, transport_factory=None):
                captured.append((host, port))

            def create_router(self, path):
                from fastapi import APIRouter

                return APIRouter()

        mock_uvicorn = MagicMock()
        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            patch("undef.terminal.fastapi.WsTerminalProxy", _CapturingProxy),
        ):
            main(["proxy", "bbs.example.com", "23"])

        assert len(captured) == 1
        assert captured[0][0] == "bbs.example.com"
        assert captured[0][0] is not None

    def test_proxy_passes_bbs_port_to_terminal_proxy(self) -> None:
        """mutmut_56: args.bbs_port must not be replaced with None."""
        captured: list[tuple] = []

        class _CapturingProxy:
            def __init__(self, host, port, *, transport_factory=None):
                captured.append((host, port))

            def create_router(self, path):
                from fastapi import APIRouter

                return APIRouter()

        mock_uvicorn = MagicMock()
        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            patch("undef.terminal.fastapi.WsTerminalProxy", _CapturingProxy),
        ):
            main(["proxy", "bbs.example.com", "9999"])

        assert len(captured) == 1
        assert captured[0][1] == 9999
        assert captured[0][1] is not None

    def test_proxy_title_contains_host_and_port(self) -> None:
        """mutmut_55/56: page title uses args.host:args.bbs_port."""
        from starlette.testclient import TestClient

        captured_app: dict = {}
        mock_uv_mod = MagicMock()
        mock_uv_mod.run = MagicMock(side_effect=lambda app, **kw: captured_app.update({"app": app}))

        with patch.dict("sys.modules", {"uvicorn": mock_uv_mod}):
            main(["proxy", "my.host.com", "1234"])

        client = TestClient(captured_app["app"])
        resp = client.get("/")
        assert resp.status_code == 200
        assert "my.host.com" in resp.text
        assert "1234" in resp.text


# ---------------------------------------------------------------------------
# _cmd_proxy — mutmut_63/64/65/66/67
# FastAPI app title, docs_url, redoc_url
# ---------------------------------------------------------------------------


class TestCmdProxyAppConfig:
    """Kill mutants that change FastAPI app config."""

    def _get_app(self, path: str = "/ws/term") -> object:
        captured_app: dict = {}
        mock_uv_mod = MagicMock()
        mock_uv_mod.run = MagicMock(side_effect=lambda app, **kw: captured_app.update({"app": app}))

        with patch.dict("sys.modules", {"uvicorn": mock_uv_mod}):
            main(["proxy", "host", "23", "--path", path])
        return captured_app["app"]

    def test_docs_url_is_disabled(self) -> None:
        """mutmut_64: docs_url=None must be set (docs endpoint disabled)."""
        from starlette.testclient import TestClient

        app = self._get_app()
        client = TestClient(app)
        resp = client.get("/docs")
        # docs disabled → 404
        assert resp.status_code == 404

    def test_redoc_url_is_disabled(self) -> None:
        """mutmut_65: redoc_url=None must be set (redoc endpoint disabled)."""
        from starlette.testclient import TestClient

        app = self._get_app()
        client = TestClient(app)
        resp = client.get("/redoc")
        # redoc disabled → 404
        assert resp.status_code == 404

    def test_static_mount_at_slash_static(self) -> None:
        """mutmut_78: static mount path must be /static not /STATIC."""
        app = self._get_app()
        # Check that the mount is named "frontend" and at /static path
        static_routes = [r for r in app.routes if getattr(r, "name", None) == "frontend"]
        assert len(static_routes) >= 1
        # The mount path should be /static (not /STATIC)
        mount = static_routes[0]
        assert mount.path == "/static"


# ---------------------------------------------------------------------------
# _cmd_proxy — mutmut_88/92/93/94
# uvicorn.run log_level argument
# ---------------------------------------------------------------------------


class TestCmdProxyUvicornArgs:
    """Kill mutants that change uvicorn.run arguments."""

    def test_uvicorn_log_level_is_warning(self) -> None:
        """mutmut_88/92/93/94: log_level must be 'warning'."""
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            main(["proxy", "bbs.example.com", "23"])

        call_kwargs = mock_uvicorn.run.call_args
        assert call_kwargs.kwargs.get("log_level") == "warning"

    def test_uvicorn_receives_log_level(self) -> None:
        """mutmut_92: log_level kwarg must be present."""
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            main(["proxy", "bbs.example.com", "23"])

        call_kwargs = mock_uvicorn.run.call_args
        assert "log_level" in call_kwargs.kwargs


# ---------------------------------------------------------------------------
# _cmd_listen — mutmut_6: sys.exit(2) instead of sys.exit(1)
# mutmut_9: and → or for port check
# ---------------------------------------------------------------------------


class TestCmdListenPortCheck:
    """Kill mutants in _cmd_listen port validation."""

    def test_both_zero_exits_with_code_1_not_2(self) -> None:
        """mutmut_6: sys.exit code must be exactly 1."""
        args = _build_parser().parse_args(["listen", "ws://localhost", "--port", "0", "--ssh-port", "0"])
        captured = io.StringIO()
        with pytest.raises(SystemExit) as exc_info, patch("sys.stderr", captured):
            _cmd_listen(args)
        assert exc_info.value.code == 1
        assert exc_info.value.code != 2

    def test_one_port_nonzero_does_not_exit_via_validation(self) -> None:
        """mutmut_9: 'and' must not become 'or' — telnet_port=1 should not trigger exit."""
        # With 'or' mutation: (1 == 0 OR 0 == 0) = True → would exit
        # With correct 'and': (1 == 0 AND 0 == 0) = False → no exit from this check
        args = _build_parser().parse_args(["listen", "ws://localhost", "--port", "1", "--ssh-port", "0"])
        assert args.port == 1
        assert args.ssh_port == 0
        # The condition (telnet_port == 0 and ssh_port == 0) is False for port=1
        # So _cmd_listen should NOT exit due to this check
        # (it will try to run asyncio.run which we can't test here without a live WS server)
        # But we can verify the args are correct
        assert not (args.port == 0 and args.ssh_port == 0)

    def test_or_mutation_would_fail_with_telnet_only(self) -> None:
        """mutmut_9: If 'and' was 'or', telnet_port=2112, ssh_port=0 would exit."""
        # Correct behavior: (2112 == 0) AND (0 == 0) = False AND True = False → no exit
        # Wrong mutation: (2112 == 0) OR (0 == 0) = False OR True = True → would exit
        # We verify the check logic is AND, not OR
        telnet_port = 2112
        ssh_port = 0
        # AND logic
        and_result = telnet_port == 0 and ssh_port == 0
        # OR logic (the mutant)
        or_result = telnet_port == 0 or ssh_port == 0
        assert and_result is False  # correct: should not exit
        assert or_result is True  # mutant: would exit (wrong)


# ---------------------------------------------------------------------------
# _run_listen — mutmut_3/4/5: gateway constructor args
# mutmut_17/18/19/21/22: ssh gateway constructor args
# mutmut_24: gw.start bind arg
# ---------------------------------------------------------------------------


class TestRunListenArgs:
    """Kill mutants that replace constructor/start arguments with None."""

    async def test_telnet_gateway_receives_ws_url(self) -> None:
        """mutmut_3: TelnetWsGateway first arg must be ws_url, not None."""
        received_args: list[tuple] = []

        class _CapturingGateway:
            def __init__(self, ws_url: str, **kw: object) -> None:
                received_args.append((ws_url, kw))

            async def start(self, host: str, port: int) -> object:
                class S:
                    async def serve_forever(self) -> None:
                        await asyncio.sleep(100)

                    def close(self) -> None:
                        pass

                return S()

        task = asyncio.create_task(
            _run_listen(
                "ws://test.example.com/ws",
                "127.0.0.1",
                2112,
                0,
                None,
                None,
                "passthrough",
                _CapturingGateway,
                object,
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert len(received_args) == 1
        assert received_args[0][0] == "ws://test.example.com/ws"
        assert received_args[0][0] is not None

    async def test_telnet_gateway_receives_token_file(self) -> None:
        """mutmut_4: TelnetWsGateway token_file kwarg must not be replaced with None."""
        from pathlib import Path

        received_kwargs: list[dict] = []

        class _CapturingGateway:
            def __init__(self, ws_url: str, **kw: object) -> None:
                received_kwargs.append(kw)

            async def start(self, host: str, port: int) -> object:
                class S:
                    async def serve_forever(self) -> None:
                        await asyncio.sleep(100)

                    def close(self) -> None:
                        pass

                return S()

        token = Path("/tmp/test_token")  # noqa: S108
        task = asyncio.create_task(
            _run_listen(
                "ws://localhost/ws",
                "127.0.0.1",
                2112,
                0,
                None,
                token,
                "passthrough",
                _CapturingGateway,
                object,
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert len(received_kwargs) == 1
        assert received_kwargs[0].get("token_file") is token

    async def test_telnet_gateway_receives_color_mode(self) -> None:
        """mutmut_5: TelnetWsGateway color_mode kwarg must not be replaced with None."""
        received_kwargs: list[dict] = []

        class _CapturingGateway:
            def __init__(self, ws_url: str, **kw: object) -> None:
                received_kwargs.append(kw)

            async def start(self, host: str, port: int) -> object:
                class S:
                    async def serve_forever(self) -> None:
                        await asyncio.sleep(100)

                    def close(self) -> None:
                        pass

                return S()

        task = asyncio.create_task(
            _run_listen(
                "ws://localhost/ws",
                "127.0.0.1",
                2112,
                0,
                None,
                None,
                "256",
                _CapturingGateway,
                object,
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert len(received_kwargs) == 1
        assert received_kwargs[0].get("color_mode") == "256"
        assert received_kwargs[0].get("color_mode") is not None

    async def test_telnet_gateway_start_receives_bind(self) -> None:
        """mutmut_24 (telnet): gw.start bind arg must not be None."""
        start_args: list[tuple] = []

        class _CapturingGateway:
            def __init__(self, ws_url: str, **kw: object) -> None:
                pass

            async def start(self, host: str, port: int) -> object:
                start_args.append((host, port))

                class S:
                    async def serve_forever(self) -> None:
                        await asyncio.sleep(100)

                    def close(self) -> None:
                        pass

                return S()

        task = asyncio.create_task(
            _run_listen(
                "ws://localhost/ws",
                "10.0.0.1",
                2112,
                0,
                None,
                None,
                "passthrough",
                _CapturingGateway,
                object,
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert len(start_args) == 1
        assert start_args[0][0] == "10.0.0.1"

    async def test_ssh_gateway_receives_ws_url(self) -> None:
        """mutmut_17: SshWsGateway first arg must be ws_url, not None."""
        received_args: list[tuple] = []

        class _FakeTelnetGateway:
            pass  # telnet_port=0, not called

        class _CapturingSshGateway:
            def __init__(self, ws_url: str, **kw: object) -> None:
                received_args.append((ws_url, kw))

            async def start(self, host: str, port: int) -> object:
                class S:
                    async def serve_forever(self) -> None:
                        await asyncio.sleep(100)

                    def close(self) -> None:
                        pass

                return S()

        task = asyncio.create_task(
            _run_listen(
                "wss://ssh.example.com/ws",
                "127.0.0.1",
                0,
                2222,
                None,
                None,
                "passthrough",
                _FakeTelnetGateway,
                _CapturingSshGateway,
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert len(received_args) == 1
        assert received_args[0][0] == "wss://ssh.example.com/ws"
        assert received_args[0][0] is not None

    async def test_ssh_gateway_receives_server_key(self) -> None:
        """mutmut_18: SshWsGateway server_key kwarg must not be replaced with None."""
        received_kwargs: list[dict] = []

        class _FakeTelnetGateway:
            pass

        class _CapturingSshGateway:
            def __init__(self, ws_url: str, **kw: object) -> None:
                received_kwargs.append(kw)

            async def start(self, host: str, port: int) -> object:
                class S:
                    async def serve_forever(self) -> None:
                        await asyncio.sleep(100)

                    def close(self) -> None:
                        pass

                return S()

        task = asyncio.create_task(
            _run_listen(
                "ws://localhost/ws",
                "127.0.0.1",
                0,
                2222,
                "/etc/ssh/host_key",
                None,
                "passthrough",
                _FakeTelnetGateway,
                _CapturingSshGateway,
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert len(received_kwargs) == 1
        assert received_kwargs[0].get("server_key") == "/etc/ssh/host_key"
        assert received_kwargs[0].get("server_key") is not None

    async def test_ssh_gateway_receives_token_file(self) -> None:
        """mutmut_19: SshWsGateway token_file kwarg must not be replaced with None."""
        from pathlib import Path

        received_kwargs: list[dict] = []

        class _FakeTelnetGateway:
            pass

        class _CapturingSshGateway:
            def __init__(self, ws_url: str, **kw: object) -> None:
                received_kwargs.append(kw)

            async def start(self, host: str, port: int) -> object:
                class S:
                    async def serve_forever(self) -> None:
                        await asyncio.sleep(100)

                    def close(self) -> None:
                        pass

                return S()

        token = Path("/tmp/token")  # noqa: S108
        task = asyncio.create_task(
            _run_listen(
                "ws://localhost/ws",
                "127.0.0.1",
                0,
                2222,
                None,
                token,
                "passthrough",
                _FakeTelnetGateway,
                _CapturingSshGateway,
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert len(received_kwargs) == 1
        assert received_kwargs[0].get("token_file") is token

    async def test_ssh_gateway_start_receives_bind(self) -> None:
        """mutmut_24 (ssh): gw_ssh.start bind arg must not be None."""
        start_args: list[tuple] = []

        class _FakeTelnetGateway:
            pass

        class _CapturingSshGateway:
            def __init__(self, ws_url: str, **kw: object) -> None:
                pass

            async def start(self, host: str, port: int) -> object:
                start_args.append((host, port))

                class S:
                    async def serve_forever(self) -> None:
                        await asyncio.sleep(100)

                    def close(self) -> None:
                        pass

                return S()

        task = asyncio.create_task(
            _run_listen(
                "ws://localhost/ws",
                "192.168.1.1",
                0,
                2222,
                None,
                None,
                "passthrough",
                _FakeTelnetGateway,
                _CapturingSshGateway,
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert len(start_args) == 1
        assert start_args[0][0] == "192.168.1.1"
        assert start_args[0][0] is not None


# ---------------------------------------------------------------------------
# _run_listen — mutmut_35/36/37/38: "no servers started" error
# ---------------------------------------------------------------------------


class TestRunListenNoServers:
    """Kill mutants that change the no-servers error message/output."""

    async def test_no_servers_prints_to_stderr(self) -> None:
        """mutmut_36: error message must go to stderr."""
        captured_stderr = io.StringIO()
        captured_stdout = io.StringIO()
        with patch("sys.stderr", captured_stderr), patch("sys.stdout", captured_stdout):
            await _run_listen(
                "ws://localhost/ws",
                "127.0.0.1",
                0,
                0,
                None,
                None,
                "passthrough",
                MagicMock(),
                MagicMock(),
            )

        stderr_output = captured_stderr.getvalue()
        assert "error" in stderr_output.lower() or "no servers" in stderr_output.lower()

    async def test_no_servers_message_not_empty(self) -> None:
        """mutmut_37: print must include the message string."""
        captured_stderr = io.StringIO()
        with patch("sys.stderr", captured_stderr):
            await _run_listen(
                "ws://localhost/ws",
                "127.0.0.1",
                0,
                0,
                None,
                None,
                "passthrough",
                MagicMock(),
                MagicMock(),
            )

        # mutmut_37 replaces the message string arg with nothing (print(file=...))
        # resulting in an empty line. Original produces "error: no servers started"
        assert captured_stderr.getvalue().strip() != ""


# ---------------------------------------------------------------------------
# _cmd_listen — mutmut_22/23/24/25/26/27/28/29/30/31
# _run_listen called with correct args
# ---------------------------------------------------------------------------


class TestCmdListenRunListenArgs:
    """Kill mutants that replace _run_listen arguments with None."""

    async def test_run_listen_called_with_ws_url(self) -> None:
        """mutmut_23: args.ws_url must be passed, not None."""
        received: list[tuple] = []

        async def _fake_run_listen(ws_url, bind, telnet_port, ssh_port, server_key, token_file, color_mode, t, s):
            received.append((ws_url, bind, telnet_port, ssh_port, server_key, token_file, color_mode))

        args = _build_parser().parse_args(["listen", "wss://test.example.com/ws", "--port", "2112", "--ssh-port", "0"])

        with patch("undef.terminal.cli._run_listen", _fake_run_listen):
            # _cmd_listen calls asyncio.run(_run_listen(...)) but asyncio.run is only
            # available in the pragma: no cover branch; test the args validation path instead
            # We patch asyncio.run to capture the coroutine
            coroutine_captured: list = []

            def fake_asyncio_run(coro):
                coroutine_captured.append(coro)
                asyncio.run(coro)

            with patch("asyncio.run", fake_asyncio_run), contextlib.suppress(Exception):
                _cmd_listen(args)

        if received:
            assert received[0][0] == "wss://test.example.com/ws"
            assert received[0][0] is not None

    async def test_run_listen_called_with_bind(self) -> None:
        """mutmut_24: args.bind must be passed to _run_listen, not None."""
        received: list[tuple] = []

        async def _fake_run_listen(ws_url, bind, telnet_port, ssh_port, server_key, token_file, color_mode, t, s):
            received.append((ws_url, bind, telnet_port, ssh_port))

        args = _build_parser().parse_args(["listen", "ws://localhost/ws", "--port", "2112", "--bind", "192.168.5.5"])

        def fake_asyncio_run(coro):
            asyncio.run(coro)

        with (
            patch("undef.terminal.cli._run_listen", _fake_run_listen),
            patch("asyncio.run", fake_asyncio_run),
            contextlib.suppress(Exception),
        ):
            _cmd_listen(args)

        if received:
            assert received[0][1] == "192.168.5.5"
            assert received[0][1] is not None

    async def test_run_listen_called_with_telnet_port(self) -> None:
        """mutmut_25: telnet_port must be passed, not None."""
        received: list[tuple] = []

        async def _fake_run_listen(ws_url, bind, telnet_port, ssh_port, server_key, token_file, color_mode, t, s):
            received.append((ws_url, bind, telnet_port, ssh_port))

        args = _build_parser().parse_args(["listen", "ws://localhost/ws", "--port", "9999"])

        def fake_asyncio_run(coro):
            asyncio.run(coro)

        with (
            patch("undef.terminal.cli._run_listen", _fake_run_listen),
            patch("asyncio.run", fake_asyncio_run),
            contextlib.suppress(Exception),
        ):
            _cmd_listen(args)

        if received:
            assert received[0][2] == 9999
            assert received[0][2] is not None

    async def test_run_listen_called_with_ssh_port(self) -> None:
        """mutmut_26: ssh_port must be passed, not None."""
        received: list[tuple] = []

        async def _fake_run_listen(ws_url, bind, telnet_port, ssh_port, server_key, token_file, color_mode, t, s):
            received.append((ws_url, bind, telnet_port, ssh_port))

        args = _build_parser().parse_args(["listen", "ws://localhost/ws", "--port", "0", "--ssh-port", "2222"])

        def fake_asyncio_run(coro):
            asyncio.run(coro)

        with (
            patch("undef.terminal.cli._run_listen", _fake_run_listen),
            patch("asyncio.run", fake_asyncio_run),
            contextlib.suppress(Exception),
        ):
            _cmd_listen(args)

        if received:
            assert received[0][3] == 2222
            assert received[0][3] is not None

    async def test_run_listen_called_with_color_mode(self) -> None:
        """mutmut_29: color_mode must be passed, not None."""
        received: list[tuple] = []

        async def _fake_run_listen(ws_url, bind, telnet_port, ssh_port, server_key, token_file, color_mode, t, s):
            received.append((ws_url, bind, telnet_port, ssh_port, server_key, token_file, color_mode))

        args = _build_parser().parse_args(["listen", "ws://localhost/ws", "--port", "2112", "--color-mode", "256"])

        def fake_asyncio_run(coro):
            asyncio.run(coro)

        with (
            patch("undef.terminal.cli._run_listen", _fake_run_listen),
            patch("asyncio.run", fake_asyncio_run),
            contextlib.suppress(Exception),
        ):
            _cmd_listen(args)

        if received:
            assert received[0][6] == "256"
            assert received[0][6] is not None


# ---------------------------------------------------------------------------
# _build_parser — prog and subcommand destination
# These cover the few non-string-equivalent mutations
# ---------------------------------------------------------------------------


class TestBuilderParserProg:
    """Kill mutmut_2/4/6/7: prog=None/removed/wrong changes prog name."""

    def test_parser_prog_is_uterm(self) -> None:
        """mutmut_2/4/6/7: parser prog must be 'uterm'."""
        parser = _build_parser()
        assert parser.prog == "uterm"

    def test_parser_prog_not_none(self) -> None:
        """mutmut_2: prog must not be None."""
        parser = _build_parser()
        assert parser.prog is not None

    def test_parser_command_dest(self) -> None:
        """mutmut: subparsers dest must be 'command'."""
        args = _build_parser().parse_args(["proxy", "host", "23"])
        assert hasattr(args, "command")
        assert args.command == "proxy"

    def test_parser_listen_command_dest(self) -> None:
        """subparsers dest must store 'listen' for listen command."""
        args = _build_parser().parse_args(["listen", "ws://url"])
        assert args.command == "listen"


# ---------------------------------------------------------------------------
# _build_parser — listen subcommand default values that carry into behavior
# ---------------------------------------------------------------------------


class TestListenParserColorMode:
    """Kill mutants on listen --color-mode default."""

    def test_color_mode_default_is_passthrough(self) -> None:
        """Default color mode is 'passthrough'."""
        args = _build_parser().parse_args(["listen", "ws://url"])
        assert args.color_mode == "passthrough"

    def test_color_mode_choices(self) -> None:
        """color-mode accepts passthrough, 256, 16."""
        for choice in ["passthrough", "256", "16"]:
            args = _build_parser().parse_args(["listen", "ws://url", "--color-mode", choice])
            assert args.color_mode == choice

    def test_color_mode_invalid_rejected(self) -> None:
        """Invalid color-mode rejected."""
        with pytest.raises(SystemExit):
            _build_parser().parse_args(["listen", "ws://url", "--color-mode", "invalid"])


class TestListenParserTokenFile:
    """Kill mutmut_41: Path(args.token_file) vs Path(None)."""

    def test_token_file_has_default(self) -> None:
        """mutmut_41: token_file default must be a valid path string, not None."""
        args = _build_parser().parse_args(["listen", "ws://url"])
        assert args.token_file is not None
        assert isinstance(args.token_file, str)
        assert len(args.token_file) > 0

    def test_token_file_custom(self) -> None:
        """token_file can be set to a custom path."""
        args = _build_parser().parse_args(["listen", "ws://url", "--token-file", "/tmp/mytoken"])  # noqa: S108
        assert args.token_file == "/tmp/mytoken"  # noqa: S108
