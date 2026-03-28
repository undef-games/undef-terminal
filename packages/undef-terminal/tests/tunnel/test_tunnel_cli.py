#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Tests for the ``uterm tunnel`` CLI subcommand."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from undef.terminal.cli import _build_parser
from undef.terminal.cli.tunnel import (
    _CHANNEL_TCP,
    _create_tunnel,
    _read_token,
    _relay_tcp_to_ws,
    _relay_ws_to_tcp,
)
from undef.terminal.tunnel.protocol import FLAG_EOF, TunnelFrame, decode_frame


class TestTunnelArgParsing:
    def test_tunnel_subcommand_recognised(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["tunnel", "8080", "-s", "https://example.com"])
        assert args.port == 8080
        assert args.server == "https://example.com"

    def test_tunnel_requires_port(self) -> None:
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["tunnel", "-s", "https://example.com"])

    def test_tunnel_requires_server(self) -> None:
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["tunnel", "8080"])

    def test_tunnel_has_func(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["tunnel", "3000", "-s", "https://x.com"])
        assert hasattr(args, "func")

    def test_tunnel_all_flags(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(
            [
                "tunnel",
                "9090",
                "-s",
                "https://x.com",
                "--token",
                "tok123",
                "--display-name",
                "my-server",
            ]
        )
        assert args.port == 9090
        assert args.token == "tok123"
        assert args.display_name == "my-server"


class TestCreateTunnel:
    def test_success(self) -> None:
        resp = json.dumps(
            {
                "tunnel_id": "tunnel-abc",
                "ws_endpoint": "ws://x/tunnel/tunnel-abc",
                "worker_token": "wt",
                "share_url": "http://x/s/tunnel-abc?token=st",
            }
        ).encode()
        with patch("undef.terminal.cli.tunnel.urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__ = lambda s: MagicMock(read=lambda: resp)
            mock_open.return_value.__exit__ = MagicMock(return_value=False)
            result = _create_tunnel("https://example.com", "test", None, 8080)
        assert result["tunnel_id"] == "tunnel-abc"

    def test_http_error(self) -> None:
        import urllib.error

        with (
            patch("undef.terminal.cli.tunnel.urllib.request.urlopen") as mock_open,
            pytest.raises(SystemExit),
        ):
            mock_open.side_effect = urllib.error.HTTPError(
                "http://x",
                500,
                "fail",
                {},
                None,  # type: ignore[arg-type]
            )
            _create_tunnel("https://example.com", "test", None, 8080)

    def test_url_error(self) -> None:
        import urllib.error

        with (
            patch("undef.terminal.cli.tunnel.urllib.request.urlopen") as mock_open,
            pytest.raises(SystemExit),
        ):
            mock_open.side_effect = urllib.error.URLError("no host")
            _create_tunnel("https://example.com", "test", None, 8080)


class TestReadToken:
    def test_explicit_token(self) -> None:
        args = MagicMock(token="my-tok", token_file=None)
        assert _read_token(args) == "my-tok"

    def test_no_token(self) -> None:
        args = MagicMock(token=None, token_file="/nonexistent")
        assert _read_token(args) is None


class TestRelayTcpToWs:
    @pytest.mark.asyncio
    async def test_sends_data_frames(self) -> None:
        reader = AsyncMock()
        reader.read = AsyncMock(side_effect=[b"hello", b"world", b""])
        sent: list[bytes] = []
        ws_send = AsyncMock(side_effect=lambda d: sent.append(d))

        await _relay_tcp_to_ws(reader, ws_send)

        assert len(sent) == 3  # 2 data + 1 EOF
        # First two are data frames on channel 2
        assert sent[0][0] == _CHANNEL_TCP
        assert sent[1][0] == _CHANNEL_TCP
        # Last is EOF
        frame = decode_frame(sent[2])
        assert frame.is_eof and frame.channel == _CHANNEL_TCP

    @pytest.mark.asyncio
    async def test_handles_connection_error(self) -> None:
        reader = AsyncMock()
        reader.read = AsyncMock(side_effect=ConnectionError("gone"))
        ws_send = AsyncMock()
        await _relay_tcp_to_ws(reader, ws_send)  # should not raise


class TestRelayWsToTcp:
    @pytest.mark.asyncio
    async def test_writes_to_tcp(self) -> None:
        writer = AsyncMock()
        writer.close = MagicMock()
        frames = [
            TunnelFrame(channel=_CHANNEL_TCP, flags=0, payload=b"hello"),
            TunnelFrame(channel=_CHANNEL_TCP, flags=FLAG_EOF, payload=b""),
        ]
        ws_recv = AsyncMock(side_effect=frames)

        await _relay_ws_to_tcp(ws_recv, writer)

        writer.write.assert_called_once_with(b"hello")
        writer.drain.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_non_tcp_channel(self) -> None:
        writer = AsyncMock()
        writer.close = MagicMock()
        frames = [
            TunnelFrame(channel=0x01, flags=0, payload=b"terminal data"),
            TunnelFrame(channel=_CHANNEL_TCP, flags=FLAG_EOF, payload=b""),
        ]
        ws_recv = AsyncMock(side_effect=frames)

        await _relay_ws_to_tcp(ws_recv, writer)

        writer.write.assert_not_called()
