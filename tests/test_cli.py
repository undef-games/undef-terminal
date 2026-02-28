#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Tests for undef.terminal.cli (uterm entry point)."""

from __future__ import annotations

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
