#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Tests for cli.py validation and error handling — mutation coverage."""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest

from undef.terminal.cli import _build_parser, _cmd_listen


class TestParserValidation:
    """Test argument parser validation."""

    def test_proxy_host_is_required(self) -> None:
        """Proxy command requires host argument."""
        with pytest.raises(SystemExit):
            _build_parser().parse_args(["proxy"])

    def test_proxy_bbs_port_is_required(self) -> None:
        """Proxy command requires bbs_port argument."""
        with pytest.raises(SystemExit):
            _build_parser().parse_args(["proxy", "host"])

    def test_proxy_port_must_be_int(self) -> None:
        """Proxy --port must be an integer."""
        with pytest.raises(SystemExit):
            _build_parser().parse_args(["proxy", "host", "23", "--port", "not_an_int"])

    def test_proxy_bbs_port_must_be_int(self) -> None:
        """Proxy bbs_port must be an integer."""
        with pytest.raises(SystemExit):
            _build_parser().parse_args(["proxy", "host", "not_an_int"])

    def test_proxy_transport_choices_validated(self) -> None:
        """Proxy --transport must be in choices."""
        with pytest.raises(SystemExit):
            _build_parser().parse_args(["proxy", "host", "23", "--transport", "invalid"])

    def test_proxy_transport_choices_case_sensitive(self) -> None:
        """Proxy --transport choices are case-sensitive."""
        with pytest.raises(SystemExit):
            _build_parser().parse_args(["proxy", "host", "23", "--transport", "SSH"])

    def test_proxy_port_short_flag(self) -> None:
        """Proxy -p is short flag for --port."""
        args = _build_parser().parse_args(["proxy", "host", "23", "-p", "9000"])
        assert args.port == 9000

    def test_listen_ws_url_is_required(self) -> None:
        """Listen command requires ws_url argument."""
        with pytest.raises(SystemExit):
            _build_parser().parse_args(["listen"])

    def test_listen_port_must_be_int(self) -> None:
        """Listen --port must be an integer."""
        with pytest.raises(SystemExit):
            _build_parser().parse_args(["listen", "ws://url", "--port", "not_int"])

    def test_listen_ssh_port_must_be_int(self) -> None:
        """Listen --ssh-port must be an integer."""
        with pytest.raises(SystemExit):
            _build_parser().parse_args(["listen", "ws://url", "--ssh-port", "not_int"])

    def test_listen_port_short_flag(self) -> None:
        """Listen -p is short flag for --port."""
        args = _build_parser().parse_args(["listen", "ws://url", "-p", "2323"])
        assert args.port == 2323

    def test_listen_port_zero_allowed(self) -> None:
        """Listen --port can be 0 (to disable)."""
        args = _build_parser().parse_args(["listen", "ws://url", "--port", "0"])
        assert args.port == 0

    def test_listen_ssh_port_zero_default(self) -> None:
        """Listen --ssh-port defaults to 0 (disabled)."""
        args = _build_parser().parse_args(["listen", "ws://url"])
        assert args.ssh_port == 0


class TestCmdListenValidation:
    """Test _cmd_listen validation logic."""

    def test_cmd_listen_both_ports_zero_exits_with_code_1(self) -> None:
        """_cmd_listen exits with code 1 when both ports are 0."""
        args = _build_parser().parse_args(["listen", "ws://localhost", "--port", "0", "--ssh-port", "0"])
        captured = io.StringIO()
        with pytest.raises(SystemExit) as exc_info, patch("sys.stderr", captured):
            _cmd_listen(args)
        assert exc_info.value.code == 1

    def test_cmd_listen_both_ports_zero_prints_error(self) -> None:
        """_cmd_listen prints error message when both ports are 0."""
        args = _build_parser().parse_args(["listen", "ws://localhost", "--port", "0", "--ssh-port", "0"])
        captured = io.StringIO()
        with pytest.raises(SystemExit), patch("sys.stderr", captured):
            _cmd_listen(args)
        output = captured.getvalue()
        assert "non-zero" in output or "at least one" in output

    def test_cmd_listen_telnet_port_nonzero_succeeds(self) -> None:
        """_cmd_listen with telnet_port > 0 should proceed."""
        args = _build_parser().parse_args(["listen", "ws://localhost", "--port", "2112"])
        # Should not exit immediately due to port validation
        assert args.port == 2112

    def test_cmd_listen_ssh_port_nonzero_succeeds(self) -> None:
        """_cmd_listen with ssh_port > 0 should proceed."""
        args = _build_parser().parse_args(["listen", "ws://localhost", "--ssh-port", "2222"])
        # Should not exit immediately due to port validation
        assert args.ssh_port == 2222


class TestParserDefaults:
    """Test parser default values."""

    def test_proxy_port_default(self) -> None:
        """Proxy --port defaults to 8765."""
        args = _build_parser().parse_args(["proxy", "host", "23"])
        assert args.port == 8765

    def test_proxy_bind_default(self) -> None:
        """Proxy --bind defaults to 0.0.0.0."""
        args = _build_parser().parse_args(["proxy", "host", "23"])
        assert args.bind == "0.0.0.0"

    def test_proxy_path_default(self) -> None:
        """Proxy --path defaults to /ws/terminal."""
        args = _build_parser().parse_args(["proxy", "host", "23"])
        assert args.path == "/ws/terminal"

    def test_proxy_transport_default(self) -> None:
        """Proxy --transport defaults to telnet."""
        args = _build_parser().parse_args(["proxy", "host", "23"])
        assert args.transport == "telnet"

    def test_listen_port_default(self) -> None:
        """Listen --port defaults to 2112."""
        args = _build_parser().parse_args(["listen", "ws://url"])
        assert args.port == 2112

    def test_listen_bind_default(self) -> None:
        """Listen --bind defaults to 0.0.0.0."""
        args = _build_parser().parse_args(["listen", "ws://url"])
        assert args.bind == "0.0.0.0"

    def test_listen_server_key_default(self) -> None:
        """Listen --server-key defaults to None."""
        args = _build_parser().parse_args(["listen", "ws://url"])
        assert args.server_key is None


class TestParserFunctionAssignment:
    """Test that parser assigns correct command functions."""

    def test_proxy_command_func_assigned(self) -> None:
        """Proxy subcommand has func attribute."""
        args = _build_parser().parse_args(["proxy", "host", "23"])
        assert hasattr(args, "func")
        assert args.func is not None

    def test_listen_command_func_assigned(self) -> None:
        """Listen subcommand has func attribute."""
        args = _build_parser().parse_args(["listen", "ws://url"])
        assert hasattr(args, "func")
        assert args.func is not None

    def test_proxy_and_listen_funcs_different(self) -> None:
        """Proxy and listen have different func references."""
        proxy_args = _build_parser().parse_args(["proxy", "host", "23"])
        listen_args = _build_parser().parse_args(["listen", "ws://url"])
        assert proxy_args.func != listen_args.func


class TestParserSubcommandRequired:
    """Test that subcommand is required."""

    def test_no_subcommand_exits(self) -> None:
        """Parser requires a subcommand."""
        with pytest.raises(SystemExit):
            _build_parser().parse_args([])

    def test_invalid_subcommand_exits(self) -> None:
        """Parser rejects invalid subcommand."""
        with pytest.raises(SystemExit):
            _build_parser().parse_args(["invalid"])
