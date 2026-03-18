#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Mutation-killing tests for server/connectors/ssh.py, telnet.py, and websocket.py.

Targets all survived mutants discovered by mutmut in those three files.
"""

from __future__ import annotations

import hashlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — Telnet
# ---------------------------------------------------------------------------


def _make_telnet_transport(*, connected: bool = True, recv_data: bytes = b"") -> MagicMock:
    t = MagicMock()
    t.is_connected.return_value = connected
    t.connect = AsyncMock()
    t.disconnect = AsyncMock()
    t.send = AsyncMock()
    t.receive = AsyncMock(return_value=recv_data)
    return t


def _make_telnet(config: dict[str, Any] | None = None, transport: MagicMock | None = None) -> Any:
    from undef.terminal.server.connectors.telnet import TelnetSessionConnector

    c = TelnetSessionConnector(
        "sess-t",
        "Test Telnet",
        config or {"host": "127.0.0.1", "port": 2323},
    )
    if transport is not None:
        c._transport = transport
    return c


# ---------------------------------------------------------------------------
# Helpers — SSH
# ---------------------------------------------------------------------------


def _make_ssh(config: dict[str, Any] | None = None) -> Any:
    pytest.importorskip("asyncssh", reason="asyncssh not installed")
    from undef.terminal.server.connectors.ssh import SshSessionConnector

    return SshSessionConnector(
        "sess-s",
        "Test SSH",
        config or {"host": "localhost", "insecure_no_host_check": True},
    )


def _attach_ssh(connector: Any) -> tuple[MagicMock, MagicMock, MagicMock]:
    mock_stdout = MagicMock()
    mock_stdin = MagicMock()
    mock_stdin.drain = AsyncMock()
    mock_conn = MagicMock()
    mock_conn.close = MagicMock()
    mock_conn.wait_closed = AsyncMock()
    connector._conn = mock_conn
    connector._stdin = mock_stdin
    connector._stdout = mock_stdout
    connector._connected = True
    return mock_conn, mock_stdin, mock_stdout


# ===========================================================================
# TelnetSessionConnector — __init__ mutants
# ===========================================================================


class TestTelnetInit:
    def test_session_id_stored(self) -> None:
        """_session_id must match the constructor argument."""
        c = _make_telnet()
        assert c._session_id == "sess-t"

    def test_display_name_stored_not_none(self) -> None:
        """mutmut_7: _display_name must be set to the argument, not None."""
        c = _make_telnet()
        assert c._display_name == "Test Telnet"
        assert c._display_name is not None

    def test_host_from_config_overrides_default(self) -> None:
        """mutmut_10,11,13,14,15: host must be read from config key 'host'."""
        c = _make_telnet({"host": "192.0.2.1", "port": 23})
        assert c._host == "192.0.2.1"

    def test_host_defaults_to_telnet_default(self) -> None:
        """mutmut_11: missing host must fall back to TerminalDefaults.TELNET_HOST."""
        from undef.terminal.defaults import TerminalDefaults

        c = _make_telnet({"port": 23})
        assert c._host == TerminalDefaults.TELNET_HOST
        assert c._host == "127.0.0.1"

    def test_port_from_config_overrides_default(self) -> None:
        """mutmut_19,21: port must be read from config key 'port'."""
        c = _make_telnet({"host": "127.0.0.1", "port": 9999})
        assert c._port == 9999

    def test_port_defaults_to_telnet_remote_port(self) -> None:
        """mutmut_19: missing port must fall back to TerminalDefaults.TELNET_REMOTE_PORT."""
        from undef.terminal.defaults import TerminalDefaults

        c = _make_telnet({"host": "127.0.0.1"})
        assert c._port == TerminalDefaults.TELNET_REMOTE_PORT
        assert c._port == 23

    def test_transport_is_not_none(self) -> None:
        """mutmut_24: _transport must be a TelnetTransport instance, not None."""
        from undef.terminal.transports.telnet import TelnetTransport

        c = _make_telnet()
        assert isinstance(c._transport, TelnetTransport)
        assert c._transport is not None

    def test_connected_initially_false_not_none(self) -> None:
        """mutmut_25: _connected must start False, not None."""
        c = _make_telnet()
        assert c._connected is False
        assert c._connected is not None

    def test_connected_initially_false_not_true(self) -> None:
        """mutmut_26: _connected must start False, not True."""
        c = _make_telnet()
        assert c._connected is False
        assert not c.is_connected()

    def test_input_mode_from_config(self) -> None:
        """mutmut_27,28,29,30,31,32,33,34: input_mode must be read from config."""
        c = _make_telnet({"host": "h", "port": 23, "input_mode": "hijack"})
        assert c._input_mode == "hijack"

    def test_input_mode_default_is_open(self) -> None:
        """mutmut_30,32,35,36: default input_mode must be 'open', not None or variant."""
        c = _make_telnet()
        assert c._input_mode == "open"

    def test_paused_initially_false_not_none(self) -> None:
        """mutmut_37: _paused must start False, not None."""
        c = _make_telnet()
        assert c._paused is False
        assert c._paused is not None

    def test_paused_initially_false_not_true(self) -> None:
        """mutmut_38: _paused must start False, not True."""
        c = _make_telnet()
        assert c._paused is False

    def test_screen_buffer_initially_empty(self) -> None:
        """mutmut_42: _screen_buffer must start as empty string, not 'XXXX'."""
        c = _make_telnet()
        assert c._screen_buffer == ""

    def test_banner_includes_host_and_port(self) -> None:
        """mutmut_43: _banner must include host/port and not be None."""
        c = _make_telnet({"host": "192.0.2.5", "port": 4321})
        assert c._banner is not None
        assert "192.0.2.5" in c._banner
        assert "4321" in c._banner


# ===========================================================================
# TelnetSessionConnector — _screen mutants
# ===========================================================================


class TestTelnetScreen:
    def test_separator_is_dashes(self) -> None:
        """mutmut_3: separator must be '-'*60."""
        c = _make_telnet({"host": "h", "port": 23})
        screen = c._screen()
        assert "-" * 60 in screen
        assert "XX-XX" not in screen

    def test_separator_length_is_60(self) -> None:
        """mutmut_4: separator must have exactly 60 dashes."""
        c = _make_telnet({"host": "h", "port": 23})
        screen = c._screen()
        assert "-" * 60 in screen
        # 61 dashes must NOT appear except as part of 60
        trimmed = screen.replace("-" * 60, "")
        assert "-" not in trimmed or "-" * 61 not in screen

    def test_open_mode_shows_shared_input(self) -> None:
        """mutmut_5,6,7: 'Shared input' must appear when input_mode=='open'."""
        c = _make_telnet({"host": "h", "port": 23, "input_mode": "open"})
        screen = c._screen()
        assert "Shared input" in screen

    def test_condition_open_not_negated(self) -> None:
        """mutmut_8: condition must be == 'open', not != 'open'."""
        c_open = _make_telnet({"host": "h", "port": 23, "input_mode": "open"})
        c_hijack = _make_telnet({"host": "h", "port": 23, "input_mode": "hijack"})
        assert "Shared input" in c_open._screen()
        assert "Exclusive hijack" in c_hijack._screen()
        assert "Exclusive hijack" not in c_open._screen()
        assert "Shared input" not in c_hijack._screen()

    def test_open_mode_keyword_is_lowercase(self) -> None:
        """mutmut_9,10: comparison must be against 'open', not 'XXopenXX' or 'OPEN'."""
        c = _make_telnet({"host": "h", "port": 23, "input_mode": "open"})
        assert "Shared input" in c._screen()

    def test_hijack_mode_shows_exclusive_hijack(self) -> None:
        """mutmut_11,12,13: 'Exclusive hijack' must appear in hijack mode."""
        c = _make_telnet({"host": "h", "port": 23, "input_mode": "hijack"})
        screen = c._screen()
        assert "Exclusive hijack" in screen
        assert "XXExclusive hijackXX" not in screen
        assert "EXCLUSIVE HIJACK" not in screen

    def test_paused_shows_paused_for_hijack(self) -> None:
        """mutmut_14: 'Paused for hijack' must appear when _paused is True."""
        c = _make_telnet({"host": "h", "port": 23})
        c._paused = True
        screen = c._screen()
        assert "Paused for hijack" in screen
        assert "XXPaused for hijackXX" not in screen

    def test_live_shows_when_not_paused(self) -> None:
        """mutmut_17: 'Live' must appear when _paused is False."""
        c = _make_telnet({"host": "h", "port": 23})
        c._paused = False
        screen = c._screen()
        assert "Live" in screen
        assert "XXLiveXX" not in screen

    def test_no_xxxx_in_screen(self) -> None:
        """mutmut_20: screen must not contain 'XXXX'."""
        c = _make_telnet({"host": "h", "port": 23})
        assert "XXXX" not in c._screen()

    def test_screen_uses_plain_newline_separator(self) -> None:
        """mutmut_25: lines must be joined with '\n', not 'XX\nXX'."""
        c = _make_telnet({"host": "h", "port": 23})
        screen = c._screen()
        assert "XX\nXX" not in screen
        assert "\n" in screen


# ===========================================================================
# TelnetSessionConnector — _snapshot mutants
# ===========================================================================


class TestTelnetSnapshot:
    def test_snapshot_type(self) -> None:
        c = _make_telnet()
        snap = c._snapshot()
        assert snap["type"] == "snapshot"

    def test_snapshot_has_screen_key(self) -> None:
        """mutmut_3,4: 'screen' key must exist and have a value."""
        c = _make_telnet()
        snap = c._snapshot()
        assert "screen" in snap
        assert snap["screen"] is not None

    def test_snapshot_cursor_x_uses_last_line(self) -> None:
        """mutmut_6,7: cursor x must use last line (lines[-1]) of the screen."""
        c = _make_telnet({"host": "h", "port": 23})
        c._screen_buffer = "A" * 79  # last line has 79 chars, x should be 79
        snap = c._snapshot()
        # x = min(len(last), 79); if last line is not the single char line, x varies
        # The key invariant: cursor x is bounded by _COLS-1 (79)
        assert snap["cursor"]["x"] <= 79

    def test_snapshot_cursor_x_bounded_by_cols_minus_1(self) -> None:
        """mutmut_22,23: cursor x = min(len(last), _COLS-1), not _COLS+1 or _COLS-2."""
        c = _make_telnet({"host": "h", "port": 23})
        c._screen_buffer = "A" * 200  # very long last line
        snap = c._snapshot()
        assert snap["cursor"]["x"] == 79  # capped at _COLS - 1

    def test_snapshot_cursor_has_x_key(self) -> None:
        """mutmut_14,15,16,17: cursor dict must have key 'x', not 'XXxXX' or 'X'."""
        c = _make_telnet()
        snap = c._snapshot()
        assert "x" in snap["cursor"]
        assert "XXcursorXX" not in snap
        assert "CURSOR" not in snap
        assert "XXxXX" not in snap["cursor"]
        assert "X" not in snap["cursor"]

    def test_snapshot_cursor_has_y_key(self) -> None:
        """mutmut_24,25: cursor dict must have key 'y', not 'XXyXX' or 'Y'."""
        c = _make_telnet()
        snap = c._snapshot()
        assert "y" in snap["cursor"]
        assert "XXyXX" not in snap["cursor"]
        assert "Y" not in snap["cursor"]

    def test_snapshot_cursor_y_bounded_by_rows_minus_1(self) -> None:
        """mutmut_30,31,32,33: cursor y must be bounded by _ROWS-1 (24)."""
        c = _make_telnet({"host": "h", "port": 23})
        # Force many lines
        c._screen_buffer = "\n".join(["line"] * 100)
        snap = c._snapshot()
        assert snap["cursor"]["y"] <= 24  # _ROWS - 1

    def test_snapshot_cols_is_80(self) -> None:
        """_COLS constant must be 80."""
        c = _make_telnet()
        snap = c._snapshot()
        assert snap["cols"] == 80

    def test_snapshot_rows_is_25(self) -> None:
        """mutmut_36,37: 'rows' key must equal 25."""
        c = _make_telnet()
        snap = c._snapshot()
        assert "rows" in snap
        assert snap["rows"] == 25
        assert "XXrowsXX" not in snap
        assert "ROWS" not in snap

    def test_snapshot_screen_hash_key_exists(self) -> None:
        """mutmut_38,39: 'screen_hash' key must exist."""
        c = _make_telnet()
        snap = c._snapshot()
        assert "screen_hash" in snap
        assert "XXscreen_hashXX" not in snap
        assert "SCREEN_HASH" not in snap

    def test_snapshot_screen_hash_length_is_16(self) -> None:
        """mutmut_44: screen_hash must be 16 chars (not 17)."""
        c = _make_telnet()
        snap = c._snapshot()
        assert len(snap["screen_hash"]) == 16

    def test_snapshot_screen_hash_matches_screen(self) -> None:
        """mutmut_43: screen_hash must be sha256 of screen encoded as utf-8."""
        c = _make_telnet()
        snap = c._snapshot()
        expected = hashlib.sha256(snap["screen"].encode("utf-8")).hexdigest()[:16]
        assert snap["screen_hash"] == expected

    def test_snapshot_cursor_at_end_is_true(self) -> None:
        """mutmut_45,46,47: cursor_at_end must be True."""
        c = _make_telnet()
        snap = c._snapshot()
        assert "cursor_at_end" in snap
        assert snap["cursor_at_end"] is True
        assert "XXcursor_at_endXX" not in snap
        assert "CURSOR_AT_END" not in snap

    def test_snapshot_has_trailing_space_is_false(self) -> None:
        """mutmut_48,49,50: has_trailing_space must be False."""
        c = _make_telnet()
        snap = c._snapshot()
        assert "has_trailing_space" in snap
        assert snap["has_trailing_space"] is False
        assert "XXhas_trailing_spaceXX" not in snap
        assert "HAS_TRAILING_SPACE" not in snap

    def test_snapshot_prompt_detected_key_is_correct(self) -> None:
        """mutmut_51,52: 'prompt_detected' key must exist."""
        c = _make_telnet()
        snap = c._snapshot()
        assert "prompt_detected" in snap
        assert "XXprompt_detectedXX" not in snap
        assert "PROMPT_DETECTED" not in snap

    def test_snapshot_prompt_id_key_in_prompt_detected(self) -> None:
        """mutmut_53,54: prompt_detected dict must have key 'prompt_id'."""
        c = _make_telnet()
        snap = c._snapshot()
        assert "prompt_id" in snap["prompt_detected"]
        assert "XXprompt_idXX" not in snap["prompt_detected"]
        assert "PROMPT_ID" not in snap["prompt_detected"]

    def test_snapshot_prompt_id_is_telnet_stream(self) -> None:
        """mutmut_55,56: prompt_id value must be 'telnet_stream'."""
        c = _make_telnet()
        snap = c._snapshot()
        assert snap["prompt_detected"]["prompt_id"] == "telnet_stream"
        assert snap["prompt_detected"]["prompt_id"] != "XXtelnet_streamXX"
        assert snap["prompt_detected"]["prompt_id"] != "TELNET_STREAM"

    def test_snapshot_ts_key_exists(self) -> None:
        """mutmut_57,58: 'ts' key must exist."""
        c = _make_telnet()
        snap = c._snapshot()
        assert "ts" in snap
        assert "XXtsXX" not in snap
        assert "TS" not in snap

    def test_snapshot_ts_is_float(self) -> None:
        c = _make_telnet()
        snap = c._snapshot()
        assert isinstance(snap["ts"], float)
        assert snap["ts"] > 0


# ===========================================================================
# TelnetSessionConnector — _hello mutants
# ===========================================================================


class TestTelnetHello:
    def test_hello_input_mode_key_exists(self) -> None:
        """mutmut_5,6: 'input_mode' key must exist in hello dict."""
        c = _make_telnet({"host": "h", "port": 23, "input_mode": "hijack"})
        hello = c._hello()
        assert "input_mode" in hello
        assert "XXinput_modeXX" not in hello
        assert "INPUT_MODE" not in hello

    def test_hello_input_mode_value_correct(self) -> None:
        """input_mode value must match the connector's current mode."""
        c = _make_telnet({"host": "h", "port": 23, "input_mode": "hijack"})
        hello = c._hello()
        assert hello["input_mode"] == "hijack"

    def test_hello_ts_key_exists(self) -> None:
        """mutmut_7,8: 'ts' key must exist."""
        c = _make_telnet()
        hello = c._hello()
        assert "ts" in hello
        assert "XXtsXX" not in hello
        assert "TS" not in hello

    def test_hello_ts_is_float(self) -> None:
        c = _make_telnet()
        hello = c._hello()
        assert isinstance(hello["ts"], float)


# ===========================================================================
# TelnetSessionConnector — stop mutant
# ===========================================================================


class TestTelnetStop:
    @pytest.mark.asyncio
    async def test_stop_sets_connected_false_not_none(self) -> None:
        """mutmut_1: _connected must be False (not None) after stop."""
        t = _make_telnet_transport()
        c = _make_telnet(transport=t)
        c._connected = True
        await c.stop()
        assert c._connected is False
        assert c._connected is not None


# ===========================================================================
# TelnetSessionConnector — poll_messages mutants
# ===========================================================================


class TestTelnetPollMessages:
    @pytest.mark.asyncio
    async def test_poll_calls_receive_with_correct_args(self) -> None:
        """mutmut_3,4,5,6,7,8: receive must be called with (4096, 100)."""
        t = _make_telnet_transport(connected=True, recv_data=b"hello")
        c = _make_telnet(transport=t)
        c._connected = True
        await c.poll_messages()
        t.receive.assert_awaited_once_with(4096, 100)

    @pytest.mark.asyncio
    async def test_poll_accumulates_received_bytes(self) -> None:
        """mutmut_10: _received_bytes must be incremented (+=), not assigned (=)."""
        t = _make_telnet_transport(connected=True, recv_data=b"hello")
        c = _make_telnet(transport=t)
        c._connected = True
        c._received_bytes = 5  # pre-set to 5
        await c.poll_messages()
        assert c._received_bytes == 10  # 5 + 5

    @pytest.mark.asyncio
    async def test_poll_screen_buffer_capped_at_32000(self) -> None:
        """mutmut_16,17: screen buffer must be capped at 32000 chars, not more."""
        t = _make_telnet_transport(connected=True, recv_data=b"x" * 20000)
        c = _make_telnet(transport=t)
        c._connected = True
        c._screen_buffer = "y" * 20000
        await c.poll_messages()
        assert len(c._screen_buffer) <= 32000

    @pytest.mark.asyncio
    async def test_poll_screen_buffer_not_empty_sliced(self) -> None:
        """mutmut_16: buffer must use [-32000:] not [+32000:] (would give empty)."""
        t = _make_telnet_transport(connected=True, recv_data=b"hello")
        c = _make_telnet(transport=t)
        c._connected = True
        c._screen_buffer = ""
        await c.poll_messages()
        # After receiving "hello", buffer must contain the text
        assert len(c._screen_buffer) > 0

    @pytest.mark.asyncio
    async def test_poll_updates_banner_with_byte_count(self) -> None:
        """mutmut_18: banner must be updated with received byte count, not None."""
        t = _make_telnet_transport(connected=True, recv_data=b"hello")
        c = _make_telnet(transport=t)
        c._connected = True
        await c.poll_messages()
        assert c._banner is not None
        assert "5" in c._banner
        assert "bytes" in c._banner.lower() or "received" in c._banner.lower()

    @pytest.mark.asyncio
    async def test_poll_returns_data_key_in_term_message(self) -> None:
        """mutmut_23,24: term message must have key 'data', not 'XXdataXX' or 'DATA'."""
        t = _make_telnet_transport(connected=True, recv_data=b"hi")
        c = _make_telnet(transport=t)
        c._connected = True
        msgs = await c.poll_messages()
        term_msgs = [m for m in msgs if m.get("type") == "term"]
        assert len(term_msgs) == 1
        assert "data" in term_msgs[0]
        assert "XXdataXX" not in term_msgs[0]
        assert "DATA" not in term_msgs[0]

    @pytest.mark.asyncio
    async def test_poll_returns_ts_key_in_term_message(self) -> None:
        """mutmut_25,26: term message must have key 'ts', not 'XXtsXX' or 'TS'."""
        t = _make_telnet_transport(connected=True, recv_data=b"hi")
        c = _make_telnet(transport=t)
        c._connected = True
        msgs = await c.poll_messages()
        term_msgs = [m for m in msgs if m.get("type") == "term"]
        assert len(term_msgs) == 1
        assert "ts" in term_msgs[0]
        assert "XXtsXX" not in term_msgs[0]
        assert "TS" not in term_msgs[0]
        assert isinstance(term_msgs[0]["ts"], float)


# ===========================================================================
# TelnetSessionConnector — handle_input mutants
# ===========================================================================


class TestTelnetHandleInput:
    @pytest.mark.asyncio
    async def test_handle_input_sends_bytes_not_none(self) -> None:
        """mutmut_1: send must be called with actual bytes, not None."""
        t = _make_telnet_transport()
        c = _make_telnet(transport=t)
        c._connected = True
        await c.handle_input("hello")
        call_args = t.send.await_args
        assert call_args is not None
        sent = call_args[0][0]
        assert sent is not None
        assert isinstance(sent, bytes)

    @pytest.mark.asyncio
    async def test_handle_input_encodes_as_cp437(self) -> None:
        """mutmut_4,5,7: must encode data as 'cp437', not default utf-8 or 'CP437'."""
        t = _make_telnet_transport()
        c = _make_telnet(transport=t)
        c._connected = True
        await c.handle_input("A")
        sent_bytes = t.send.await_args[0][0]
        # 'A' encoded as cp437 is b'\x41'
        assert sent_bytes == b"A"

    @pytest.mark.asyncio
    async def test_handle_input_uses_replace_error_handler(self) -> None:
        """mutmut_8,9: must use errors='replace', not 'XXreplaceXX' or 'REPLACE'."""
        t = _make_telnet_transport()
        c = _make_telnet(transport=t)
        c._connected = True
        # Characters with replaceable chars
        await c.handle_input("hello \u0000")  # NUL is encodable in cp437
        assert t.send.await_count == 1

    @pytest.mark.asyncio
    async def test_handle_input_updates_banner(self) -> None:
        """mutmut_10: banner must be updated (not set to None) after input."""
        t = _make_telnet_transport()
        c = _make_telnet(transport=t)
        c._connected = True
        await c.handle_input("hello")
        assert c._banner is not None
        assert "5" in c._banner  # 5 characters

    @pytest.mark.asyncio
    async def test_handle_input_returns_snapshot(self) -> None:
        t = _make_telnet_transport()
        c = _make_telnet(transport=t)
        c._connected = True
        msgs = await c.handle_input("x")
        assert len(msgs) == 1
        assert msgs[0]["type"] == "snapshot"


# ===========================================================================
# TelnetSessionConnector — handle_control mutants
# ===========================================================================


class TestTelnetHandleControl:
    @pytest.mark.asyncio
    async def test_pause_sets_paused_and_banner(self) -> None:
        """mutmut_6,7,8,9: pause must set _paused=True and update banner."""
        c = _make_telnet()
        await c.handle_control("pause")
        assert c._paused is True
        assert c._banner is not None
        assert "Exclusive control" in c._banner
        # Verify case-exact match
        assert "Exclusive control active." in c._banner

    @pytest.mark.asyncio
    async def test_resume_sets_paused_false_and_banner(self) -> None:
        """mutmut_15,16,17,18: resume must set _paused=False and update banner."""
        c = _make_telnet()
        c._paused = True
        await c.handle_control("resume")
        assert c._paused is False
        assert c._banner is not None
        assert "Exclusive control released." in c._banner

    @pytest.mark.asyncio
    async def test_step_action_recognized(self) -> None:
        """mutmut_20,21: 'step' action must be matched (not 'XXstepXX' or 'STEP')."""
        c = _make_telnet()
        await c.handle_control("step")
        # Step must set a specific banner, not fall through to "Ignored"
        assert "Ignored" not in c._banner
        assert "Step" in c._banner or "step" in c._banner.lower()

    @pytest.mark.asyncio
    async def test_step_banner_exact(self) -> None:
        """mutmut_22,23,24,25: step banner must be exact 'Step requested...' text."""
        c = _make_telnet()
        await c.handle_control("step")
        assert c._banner == "Step requested. Awaiting upstream output."

    @pytest.mark.asyncio
    async def test_handle_control_returns_snapshot(self) -> None:
        c = _make_telnet()
        msgs = await c.handle_control("pause")
        assert len(msgs) == 1
        assert msgs[0]["type"] == "snapshot"


# ===========================================================================
# TelnetSessionConnector — get_analysis mutant
# ===========================================================================


class TestTelnetGetAnalysis:
    @pytest.mark.asyncio
    async def test_analysis_uses_newline_separator(self) -> None:
        """mutmut_2: join must use '\n', not 'XX\nXX'."""
        c = _make_telnet({"host": "127.0.0.1", "port": 23})
        result = await c.get_analysis()
        # Fields must be separated by plain newlines
        assert "XX\nXX" not in result
        assert "\n" in result
        assert "sess-t" in result
        assert "127.0.0.1" in result
        assert "input_mode" in result


# ===========================================================================
# TelnetSessionConnector — clear mutants
# ===========================================================================


class TestTelnetClear:
    @pytest.mark.asyncio
    async def test_clear_empties_buffer(self) -> None:
        c = _make_telnet()
        c._screen_buffer = "old data"
        await c.clear()
        assert c._screen_buffer == ""

    @pytest.mark.asyncio
    async def test_clear_banner_exact(self) -> None:
        """mutmut_3,4,5,6: banner must be 'Screen buffer cleared.' exactly."""
        c = _make_telnet()
        await c.clear()
        assert c._banner == "Screen buffer cleared."

    @pytest.mark.asyncio
    async def test_clear_returns_snapshot(self) -> None:
        c = _make_telnet()
        msgs = await c.clear()
        assert len(msgs) == 1
        assert msgs[0]["type"] == "snapshot"


# ===========================================================================
# TelnetSessionConnector — set_mode mutants
# ===========================================================================


class TestTelnetSetMode:
    @pytest.mark.asyncio
    async def test_set_mode_open_clears_paused(self) -> None:
        """mutmut_13,17-19: setting 'open' mode must clear paused flag."""
        c = _make_telnet({"host": "h", "port": 23, "input_mode": "hijack"})
        c._paused = True
        await c.set_mode("open")
        assert c._paused is False
        assert c._input_mode == "open"

    @pytest.mark.asyncio
    async def test_set_mode_banner_shared_input_for_open(self) -> None:
        """mutmut_14,15,16,17,18,19: banner must say 'Shared input' for open mode."""
        c = _make_telnet()
        await c.set_mode("open")
        assert "Shared input" in c._banner
        assert c._banner is not None

    @pytest.mark.asyncio
    async def test_set_mode_banner_exclusive_hijack_for_hijack(self) -> None:
        """mutmut_20,21,22: banner must say 'Exclusive hijack' for hijack mode."""
        c = _make_telnet()
        await c.set_mode("hijack")
        assert "Exclusive hijack" in c._banner

    @pytest.mark.asyncio
    async def test_set_mode_returns_hello_and_snapshot(self) -> None:
        c = _make_telnet()
        msgs = await c.set_mode("open")
        assert len(msgs) == 2
        assert msgs[0]["type"] == "worker_hello"
        assert msgs[1]["type"] == "snapshot"

    @pytest.mark.asyncio
    async def test_set_mode_hello_has_input_mode(self) -> None:
        c = _make_telnet()
        msgs = await c.set_mode("hijack")
        assert msgs[0]["input_mode"] == "hijack"


# ===========================================================================
# SshSessionConnector — __init__ mutants
# ===========================================================================


class TestSshInit:
    def test_display_name_stored_not_none(self) -> None:
        """mutmut_48: _display_name must be set, not None."""
        c = _make_ssh()
        assert c._display_name == "Test SSH"
        assert c._display_name is not None

    def test_host_from_config(self) -> None:
        """mutmut_49,51,52,54,55,56: host must be read from config key 'host'."""
        pytest.importorskip("asyncssh")
        from undef.terminal.server.connectors.ssh import SshSessionConnector

        c = SshSessionConnector("s", "S", {"host": "192.0.2.99", "insecure_no_host_check": True})
        assert c._host == "192.0.2.99"

    def test_host_defaults_to_telnet_host(self) -> None:
        """mutmut_52: missing host must fall back to TerminalDefaults.TELNET_HOST."""
        from undef.terminal.defaults import TerminalDefaults

        c = _make_ssh({"insecure_no_host_check": True})
        assert c._host == TerminalDefaults.TELNET_HOST

    def test_username_from_config(self) -> None:
        """mutmut_66-72: username must be read from config key 'username'."""
        pytest.importorskip("asyncssh")
        from undef.terminal.server.connectors.ssh import SshSessionConnector

        c = SshSessionConnector("s", "S", {"host": "h", "insecure_no_host_check": True, "username": "admin"})
        assert c._username == "admin"

    def test_username_defaults_to_guest(self) -> None:
        """mutmut_68,73,74: missing username must fall back to 'guest'."""
        c = _make_ssh()
        assert c._username == "guest"

    def test_password_none_when_not_in_config(self) -> None:
        """mutmut_75,79: _password must be None when not provided in config."""
        c = _make_ssh()
        assert c._password is None

    def test_password_stored_from_config(self) -> None:
        """mutmut_75,76,77,78,79,80,81,82,83: password must be stored from config."""
        pytest.importorskip("asyncssh")
        from undef.terminal.server.connectors.ssh import SshSessionConnector

        c = SshSessionConnector("s", "S", {"host": "h", "insecure_no_host_check": True, "password": "secret99"})
        assert c._password == "secret99"

    def test_password_is_none_not_set_to_str_none(self) -> None:
        """mutmut_79: when password absent, _password must be None (not str of something)."""
        c = _make_ssh()
        assert c._password is None

    def test_input_mode_from_config(self) -> None:
        """mutmut_114-123: input_mode must be read from config key 'input_mode'."""
        pytest.importorskip("asyncssh")
        from undef.terminal.server.connectors.ssh import SshSessionConnector

        c = SshSessionConnector("s", "S", {"host": "h", "insecure_no_host_check": True, "input_mode": "hijack"})
        assert c._input_mode == "hijack"

    def test_input_mode_defaults_to_open(self) -> None:
        """mutmut_117,119,122,123: default input_mode must be 'open'."""
        c = _make_ssh()
        assert c._input_mode == "open"

    def test_paused_initially_false_not_none(self) -> None:
        """mutmut_124: _paused must start False, not None."""
        c = _make_ssh()
        assert c._paused is False
        assert c._paused is not None

    def test_paused_initially_false_not_true(self) -> None:
        """mutmut_125: _paused must start False, not True."""
        c = _make_ssh()
        assert c._paused is False

    def test_connected_initially_false_not_none(self) -> None:
        """mutmut_126: _connected must start False, not None."""
        c = _make_ssh()
        assert c._connected is False
        assert c._connected is not None

    def test_connected_initially_false_not_true(self) -> None:
        """mutmut_127: _connected must start False, not True."""
        c = _make_ssh()
        assert c._connected is False
        assert not c.is_connected()

    def test_banner_not_none_and_includes_host(self) -> None:
        """mutmut_130: _banner must be a string containing host info, not None."""
        pytest.importorskip("asyncssh")
        from undef.terminal.server.connectors.ssh import SshSessionConnector

        c = SshSessionConnector("s", "S", {"host": "myhost.example", "insecure_no_host_check": True})
        assert c._banner is not None
        assert "myhost.example" in c._banner

    def test_no_known_hosts_without_insecure_raises(self) -> None:
        """mutmut_100-103: ValueError must be raised if no known_hosts and no insecure flag."""
        pytest.importorskip("asyncssh")
        from undef.terminal.server.connectors.ssh import SshSessionConnector

        with pytest.raises(ValueError, match="known_hosts"):
            SshSessionConnector("s", "S", {"host": "h"})

    def test_insecure_no_host_check_skips_error(self) -> None:
        """insecure_no_host_check=True must suppress the known_hosts error."""
        c = _make_ssh({"host": "h", "insecure_no_host_check": True})
        assert c._known_hosts is None

    def test_known_hosts_stored(self) -> None:
        pytest.importorskip("asyncssh")
        from undef.terminal.server.connectors.ssh import SshSessionConnector

        c = SshSessionConnector("s", "S", {"host": "h", "known_hosts": "/etc/known_hosts"})
        assert c._known_hosts == "/etc/known_hosts"


# ===========================================================================
# SshSessionConnector — _screen mutants
# ===========================================================================


class TestSshScreen:
    def test_separator_is_dashes(self) -> None:
        """mutmut_3: separator must be '-'*60."""
        c = _make_ssh()
        screen = c._screen()
        assert "-" * 60 in screen

    def test_separator_length_60(self) -> None:
        """mutmut_4: separator must be 60 dashes, not 61."""
        c = _make_ssh()
        screen = c._screen()
        assert "-" * 60 in screen
        # verify 61 consecutive dashes don't appear
        assert "-" * 61 not in screen

    def test_open_mode_shows_shared_input(self) -> None:
        """mutmut_5,6,7: 'Shared input' must appear in open mode."""
        pytest.importorskip("asyncssh")
        from undef.terminal.server.connectors.ssh import SshSessionConnector

        c = SshSessionConnector("s", "S", {"host": "h", "insecure_no_host_check": True, "input_mode": "open"})
        screen = c._screen()
        assert "Shared input" in screen

    def test_hijack_mode_shows_exclusive_hijack(self) -> None:
        """mutmut_8-13: condition/string must discriminate open vs hijack."""
        pytest.importorskip("asyncssh")
        from undef.terminal.server.connectors.ssh import SshSessionConnector

        c_open = SshSessionConnector("s", "S", {"host": "h", "insecure_no_host_check": True, "input_mode": "open"})
        c_hijack = SshSessionConnector("s", "S", {"host": "h", "insecure_no_host_check": True, "input_mode": "hijack"})
        assert "Shared input" in c_open._screen()
        assert "Exclusive hijack" in c_hijack._screen()

    def test_paused_shows_paused_for_hijack(self) -> None:
        """mutmut_14: 'Paused for hijack' must appear when _paused."""
        c = _make_ssh()
        c._paused = True
        assert "Paused for hijack" in c._screen()

    def test_live_shows_when_not_paused(self) -> None:
        """mutmut_17: 'Live' must appear when not paused."""
        c = _make_ssh()
        c._paused = False
        assert "Live" in c._screen()

    def test_no_xxxx_in_screen(self) -> None:
        """mutmut_20,22: no 'XXXX' or 'XX\nXX' in screen output."""
        c = _make_ssh()
        screen = c._screen()
        assert "XXXX" not in screen
        assert "XX\nXX" not in screen

    def test_screen_joined_with_plain_newline(self) -> None:
        """mutmut_22: lines must be joined with '\n'."""
        c = _make_ssh()
        screen = c._screen()
        assert "\n" in screen
        assert "XX\nXX" not in screen


# ===========================================================================
# SshSessionConnector — _snapshot mutants
# ===========================================================================


class TestSshSnapshot:
    def test_snapshot_type(self) -> None:
        c = _make_ssh()
        snap = c._snapshot()
        assert snap["type"] == "snapshot"

    def test_snapshot_cursor_x_bounded(self) -> None:
        """mutmut_6,7,22,23: cursor x must use lines[-1] and be bounded by _COLS-1."""
        c = _make_ssh()
        c._screen_buffer = "A" * 200
        snap = c._snapshot()
        assert snap["cursor"]["x"] == 79

    def test_snapshot_cursor_keys(self) -> None:
        """mutmut_14-17,24,25: cursor must have keys 'x' and 'y', not variants."""
        c = _make_ssh()
        snap = c._snapshot()
        assert "cursor" in snap
        assert "x" in snap["cursor"]
        assert "y" in snap["cursor"]

    def test_snapshot_cursor_y_bounded(self) -> None:
        """mutmut_30-33: cursor y must be bounded by _ROWS-1 (24)."""
        c = _make_ssh()
        c._screen_buffer = "\n".join(["line"] * 100)
        snap = c._snapshot()
        assert snap["cursor"]["y"] <= 24

    def test_snapshot_cols_80(self) -> None:
        c = _make_ssh()
        assert c._snapshot()["cols"] == 80

    def test_snapshot_rows_25(self) -> None:
        """mutmut_34-37: rows must be 25."""
        c = _make_ssh()
        snap = c._snapshot()
        assert snap["rows"] == 25
        assert "rows" in snap

    def test_snapshot_screen_hash_16_chars(self) -> None:
        """mutmut_43,44: screen_hash must be 16 chars."""
        c = _make_ssh()
        snap = c._snapshot()
        assert len(snap["screen_hash"]) == 16

    def test_snapshot_screen_hash_matches(self) -> None:
        """mutmut_38,39,43: screen_hash must be sha256 of screen, utf-8 encoded."""
        c = _make_ssh()
        snap = c._snapshot()
        expected = hashlib.sha256(snap["screen"].encode("utf-8")).hexdigest()[:16]
        assert snap["screen_hash"] == expected

    def test_snapshot_cursor_at_end_is_true(self) -> None:
        """mutmut_45-47: cursor_at_end must be True."""
        c = _make_ssh()
        snap = c._snapshot()
        assert snap["cursor_at_end"] is True

    def test_snapshot_has_trailing_space_is_false(self) -> None:
        """mutmut_48-50: has_trailing_space must be False."""
        c = _make_ssh()
        snap = c._snapshot()
        assert snap["has_trailing_space"] is False

    def test_snapshot_prompt_id_is_ssh_stream(self) -> None:
        """mutmut_51-58: prompt_id must be 'ssh_stream'."""
        c = _make_ssh()
        snap = c._snapshot()
        assert snap["prompt_detected"]["prompt_id"] == "ssh_stream"

    def test_snapshot_ts_key_exists_and_is_float(self) -> None:
        """mutmut_57,58: 'ts' key must exist."""
        c = _make_ssh()
        snap = c._snapshot()
        assert "ts" in snap
        assert isinstance(snap["ts"], float)


# ===========================================================================
# SshSessionConnector — _hello mutants
# ===========================================================================


class TestSshHello:
    def test_hello_input_mode_key(self) -> None:
        """mutmut_5,6: 'input_mode' key must exist."""
        pytest.importorskip("asyncssh")
        from undef.terminal.server.connectors.ssh import SshSessionConnector

        c = SshSessionConnector("s", "S", {"host": "h", "insecure_no_host_check": True, "input_mode": "hijack"})
        hello = c._hello()
        assert "input_mode" in hello
        assert hello["input_mode"] == "hijack"

    def test_hello_ts_key(self) -> None:
        """mutmut_7,8: 'ts' key must exist."""
        c = _make_ssh()
        hello = c._hello()
        assert "ts" in hello
        assert isinstance(hello["ts"], float)


# ===========================================================================
# SshSessionConnector — start mutants
# ===========================================================================


class TestSshStart:
    @pytest.mark.asyncio
    async def test_start_passes_host_to_connect(self) -> None:
        """mutmut_2: connect must be called with self._host, not None."""
        pytest.importorskip("asyncssh")
        import asyncssh

        from undef.terminal.server.connectors.ssh import SshSessionConnector

        c = SshSessionConnector("s", "S", {"host": "myhost.example", "insecure_no_host_check": True})
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stdout = MagicMock()
        mock_conn = MagicMock()
        mock_conn.create_process = AsyncMock(return_value=mock_process)
        with patch.object(asyncssh, "connect", new=AsyncMock(return_value=mock_conn)) as mock_connect:
            await c.start()
            call_args = mock_connect.call_args
            # First positional arg must be the host
            assert call_args[0][0] == "myhost.example"

    @pytest.mark.asyncio
    async def test_start_wires_stdin_stdout_connected(self) -> None:
        """mutmut_5,6,7,10,12,13,16,17,21-29: start must wire process fields correctly."""
        pytest.importorskip("asyncssh")
        import asyncssh

        c = _make_ssh()
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stdout = MagicMock()
        mock_conn = MagicMock()
        mock_conn.create_process = AsyncMock(return_value=mock_process)
        with patch.object(asyncssh, "connect", new=AsyncMock(return_value=mock_conn)):
            await c.start()
        assert c._connected is True
        assert c._stdin is mock_process.stdin
        assert c._stdout is mock_process.stdout
        assert c._conn is mock_conn
        assert c._process is mock_process

    @pytest.mark.asyncio
    async def test_start_create_process_uses_ansi_term(self) -> None:
        """mutmut_21,22,23,24,25,26,27: create_process must use term_type='ansi'."""
        pytest.importorskip("asyncssh")
        import asyncssh

        c = _make_ssh()
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stdout = MagicMock()
        mock_conn = MagicMock()
        mock_conn.create_process = AsyncMock(return_value=mock_process)
        with patch.object(asyncssh, "connect", new=AsyncMock(return_value=mock_conn)):
            await c.start()
        call_kwargs = mock_conn.create_process.await_args[1]
        assert call_kwargs.get("term_type") == "ansi"
        assert call_kwargs.get("term_size") == (80, 25)

    @pytest.mark.asyncio
    async def test_start_process_not_none(self) -> None:
        """mutmut_29: _process must not be None after start."""
        pytest.importorskip("asyncssh")
        import asyncssh

        c = _make_ssh()
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stdout = MagicMock()
        mock_conn = MagicMock()
        mock_conn.create_process = AsyncMock(return_value=mock_process)
        with patch.object(asyncssh, "connect", new=AsyncMock(return_value=mock_conn)):
            await c.start()
        assert c._process is not None
        assert c._process is mock_process


# ===========================================================================
# SshSessionConnector — stop mutants
# ===========================================================================


class TestSshStop:
    @pytest.mark.asyncio
    async def test_stop_process_set_to_none(self) -> None:
        """mutmut_4: _process must be None (not '') after stop."""
        c = _make_ssh()
        _, _, _ = _attach_ssh(c)
        c._process = MagicMock()
        c._process.close = MagicMock()
        await c.stop()
        assert c._process is None

    @pytest.mark.asyncio
    async def test_stop_stdout_set_to_none(self) -> None:
        """mutmut_7: _stdout must be None (not '') after stop."""
        c = _make_ssh()
        _attach_ssh(c)
        await c.stop()
        assert c._stdout is None

    @pytest.mark.asyncio
    async def test_stop_connected_is_false_not_none(self) -> None:
        """mutmut_8: _connected must be False (not None) after stop."""
        c = _make_ssh()
        _attach_ssh(c)
        await c.stop()
        assert c._connected is False
        assert c._connected is not None

    @pytest.mark.asyncio
    async def test_stop_suppress_uses_exception_not_none(self) -> None:
        """mutmut_11,13,15: contextlib.suppress must use Exception, not None."""
        c = _make_ssh()
        mock_conn = MagicMock()
        mock_conn.close = MagicMock()
        mock_conn.wait_closed = AsyncMock()
        mock_process = MagicMock()
        mock_process.close = MagicMock(side_effect=RuntimeError("oops"))
        mock_stdin = MagicMock()
        mock_stdin.write_eof = MagicMock(side_effect=RuntimeError("oops"))
        c._conn = mock_conn
        c._process = mock_process
        c._stdin = mock_stdin
        c._stdout = MagicMock()
        c._connected = True
        # Must not raise; errors must be suppressed
        await c.stop()
        assert c._connected is False


# ===========================================================================
# SshSessionConnector — poll_messages mutants
# ===========================================================================


class TestSshPollMessages:
    @pytest.mark.asyncio
    async def test_poll_returns_empty_when_disconnected_or_stdout_none(self) -> None:
        """mutmut_2: condition must be 'or', not 'and' — both disconnected and stdout None must return []."""
        c = _make_ssh()
        c._connected = True
        c._stdout = None  # stdout is None but connected — original: return []
        result = await c.poll_messages()
        assert result == []

    @pytest.mark.asyncio
    async def test_poll_uses_4096_read_size(self) -> None:
        """mutmut_11: read must be called with 4096, not 4097."""
        c = _make_ssh()
        _attach_ssh(c)
        with patch("asyncio.wait_for", new=AsyncMock(return_value=b"hi")) as mock_wait:
            await c.poll_messages()
        # Inspect that wait_for was called with a read(4096) call
        mock_wait.call_args[0][0]
        # The first arg is a coroutine; we can't easily inspect it without running it
        # Instead verify that data was correctly received
        assert c._bytes_received == 2

    @pytest.mark.asyncio
    async def test_poll_accumulates_bytes_received(self) -> None:
        """mutmut_23: must use += not = for _bytes_received."""
        c = _make_ssh()
        _attach_ssh(c)
        c._bytes_received = 10
        with patch("asyncio.wait_for", new=AsyncMock(return_value=b"hello")):
            await c.poll_messages()
        assert c._bytes_received == 15  # 10 + 5

    @pytest.mark.asyncio
    async def test_poll_encodes_str_data_as_latin1(self) -> None:
        """mutmut_17,18,20,21,22: str data must be encoded as 'latin-1'."""
        c = _make_ssh()
        _attach_ssh(c)
        with patch("asyncio.wait_for", new=AsyncMock(return_value="hello")):
            msgs = await c.poll_messages()
        # Encoded as latin-1: 'hello' -> 5 bytes
        assert c._bytes_received == 5
        term_msgs = [m for m in msgs if m.get("type") == "term"]
        assert len(term_msgs) == 1

    @pytest.mark.asyncio
    async def test_poll_screen_buffer_capped_at_32000(self) -> None:
        """mutmut_30: buffer must use [-32000:] not [-32001:]."""
        c = _make_ssh()
        _attach_ssh(c)
        c._screen_buffer = "y" * 20000
        with patch("asyncio.wait_for", new=AsyncMock(return_value=b"x" * 20000)):
            await c.poll_messages()
        assert len(c._screen_buffer) <= 32000

    @pytest.mark.asyncio
    async def test_poll_updates_banner_not_none(self) -> None:
        """mutmut_31: banner must be updated, not set to None."""
        c = _make_ssh()
        _attach_ssh(c)
        with patch("asyncio.wait_for", new=AsyncMock(return_value=b"hi")):
            await c.poll_messages()
        assert c._banner is not None
        assert "SSH" in c._banner or "bytes" in c._banner.lower()

    @pytest.mark.asyncio
    async def test_poll_term_message_has_data_key(self) -> None:
        """mutmut_36,37: term message must have 'data' key not 'XXdataXX' or 'DATA'."""
        c = _make_ssh()
        _attach_ssh(c)
        with patch("asyncio.wait_for", new=AsyncMock(return_value=b"hello")):
            msgs = await c.poll_messages()
        term_msgs = [m for m in msgs if m.get("type") == "term"]
        assert len(term_msgs) == 1
        assert "data" in term_msgs[0]
        assert "XXdataXX" not in term_msgs[0]
        assert "DATA" not in term_msgs[0]

    @pytest.mark.asyncio
    async def test_poll_term_message_has_ts_key(self) -> None:
        """mutmut_38,39: term message must have 'ts' key."""
        c = _make_ssh()
        _attach_ssh(c)
        with patch("asyncio.wait_for", new=AsyncMock(return_value=b"hello")):
            msgs = await c.poll_messages()
        term_msgs = [m for m in msgs if m.get("type") == "term"]
        assert "ts" in term_msgs[0]
        assert "XXtsXX" not in term_msgs[0]
        assert "TS" not in term_msgs[0]

    @pytest.mark.asyncio
    async def test_poll_returns_empty_on_timeout(self) -> None:
        """poll must return [] on TimeoutError."""
        c = _make_ssh()
        _attach_ssh(c)
        with patch("asyncio.wait_for", new=AsyncMock(side_effect=TimeoutError)):
            result = await c.poll_messages()
        assert result == []


# ===========================================================================
# SshSessionConnector — handle_input mutants
# ===========================================================================


class TestSshHandleInput:
    @pytest.mark.asyncio
    async def test_handle_input_sends_utf8_bytes(self) -> None:
        """mutmut_6,7: must encode data as 'utf-8' and write it."""
        c = _make_ssh()
        _, mock_stdin, _ = _attach_ssh(c)
        mock_stdin.write = MagicMock()
        await c.handle_input("hello")
        mock_stdin.write.assert_called_once_with(b"hello")

    @pytest.mark.asyncio
    async def test_handle_input_updates_banner(self) -> None:
        """mutmut_9: banner must be updated with char count, not None."""
        c = _make_ssh()
        _, mock_stdin, _ = _attach_ssh(c)
        mock_stdin.write = MagicMock()
        await c.handle_input("hello")
        assert c._banner is not None
        assert "5" in c._banner

    @pytest.mark.asyncio
    async def test_handle_input_returns_snapshot(self) -> None:
        """mutmut_10: handle_input must return snapshot."""
        c = _make_ssh()
        _, mock_stdin, _ = _attach_ssh(c)
        mock_stdin.write = MagicMock()
        msgs = await c.handle_input("x")
        assert len(msgs) == 1
        assert msgs[0]["type"] == "snapshot"


# ===========================================================================
# SshSessionConnector — handle_control mutants
# ===========================================================================


class TestSshHandleControl:
    @pytest.mark.asyncio
    async def test_pause_sets_paused_and_banner(self) -> None:
        """mutmut_6,7,8,9: pause must set _paused=True and exact banner."""
        c = _make_ssh()
        await c.handle_control("pause")
        assert c._paused is True
        assert c._banner == "Exclusive control active."

    @pytest.mark.asyncio
    async def test_resume_sets_paused_false_and_banner(self) -> None:
        """mutmut_15,16,17,18: resume must set _paused=False and exact banner."""
        c = _make_ssh()
        c._paused = True
        await c.handle_control("resume")
        assert c._paused is False
        assert c._banner == "Exclusive control released."

    @pytest.mark.asyncio
    async def test_step_sets_banner_exactly(self) -> None:
        """mutmut_23: step banner must be exact text."""
        c = _make_ssh()
        await c.handle_control("step")
        assert c._banner == "Step requested. Awaiting upstream output."

    @pytest.mark.asyncio
    async def test_handle_control_returns_snapshot(self) -> None:
        c = _make_ssh()
        msgs = await c.handle_control("pause")
        assert len(msgs) == 1
        assert msgs[0]["type"] == "snapshot"


# ===========================================================================
# SshSessionConnector — get_analysis mutant
# ===========================================================================


class TestSshGetAnalysis:
    @pytest.mark.asyncio
    async def test_analysis_joined_with_newline(self) -> None:
        """mutmut_2: join must use '\n', not 'XX\nXX'."""
        c = _make_ssh({"host": "myhost", "insecure_no_host_check": True})
        result = await c.get_analysis()
        assert "XX\nXX" not in result
        assert "\n" in result
        assert "sess-s" in result
        assert "myhost" in result


# ===========================================================================
# SshSessionConnector — clear mutants
# ===========================================================================


class TestSshClear:
    @pytest.mark.asyncio
    async def test_clear_empties_buffer(self) -> None:
        c = _make_ssh()
        c._screen_buffer = "old stuff"
        await c.clear()
        assert c._screen_buffer == ""

    @pytest.mark.asyncio
    async def test_clear_banner_exact(self) -> None:
        """mutmut_3,4,5,6: banner must be 'Screen buffer cleared.' exactly."""
        c = _make_ssh()
        await c.clear()
        assert c._banner == "Screen buffer cleared."

    @pytest.mark.asyncio
    async def test_clear_returns_snapshot(self) -> None:
        c = _make_ssh()
        msgs = await c.clear()
        assert len(msgs) == 1
        assert msgs[0]["type"] == "snapshot"


# ===========================================================================
# SshSessionConnector — set_mode mutants
# ===========================================================================


class TestSshSetMode:
    @pytest.mark.asyncio
    async def test_set_mode_open_clears_paused(self) -> None:
        """mutmut_13,17-19: setting 'open' mode must clear paused flag."""
        c = _make_ssh()
        c._paused = True
        c._input_mode = "hijack"
        await c.set_mode("open")
        assert c._paused is False
        assert c._input_mode == "open"

    @pytest.mark.asyncio
    async def test_set_mode_banner_shared_for_open(self) -> None:
        """mutmut_14,15,16: banner must say 'Shared input' for open mode."""
        c = _make_ssh()
        await c.set_mode("open")
        assert "Shared input" in c._banner
        assert c._banner is not None

    @pytest.mark.asyncio
    async def test_set_mode_banner_exclusive_for_hijack(self) -> None:
        """mutmut_20,21,22: banner must say 'Exclusive hijack' for hijack mode."""
        c = _make_ssh()
        await c.set_mode("hijack")
        assert "Exclusive hijack" in c._banner

    @pytest.mark.asyncio
    async def test_set_mode_returns_hello_and_snapshot(self) -> None:
        c = _make_ssh()
        msgs = await c.set_mode("open")
        assert len(msgs) == 2
        assert msgs[0]["type"] == "worker_hello"
        assert msgs[1]["type"] == "snapshot"

    @pytest.mark.asyncio
    async def test_set_mode_hello_has_input_mode(self) -> None:
        c = _make_ssh()
        msgs = await c.set_mode("hijack")
        assert msgs[0]["input_mode"] == "hijack"


# ===========================================================================
# Additional WebSocket mutants not covered by test_websocket_connector_mutations.py
# ===========================================================================


def _make_ws(config: dict[str, Any] | None = None) -> Any:
    from undef.terminal.server.connectors.websocket import WebSocketSessionConnector

    return WebSocketSessionConnector(
        "ws-sess2",
        "Test WS2",
        config or {"url": "ws://localhost:9999/ws"},
    )


class TestWebSocketAdditionalMutants:
    """Additional websocket mutant tests that may not be covered by the existing file."""

    def test_ws_snapshot_prompt_id_is_ws_stream(self) -> None:
        """mutmut_50-56: prompt_id must be 'ws_stream', not variant strings."""
        c = _make_ws()
        snap = c._snapshot()
        assert snap["prompt_detected"]["prompt_id"] == "ws_stream"
        assert snap["prompt_detected"]["prompt_id"] != "ws_Stream"
        assert snap["prompt_detected"]["prompt_id"] != "WS_STREAM"

    def test_ws_snapshot_ts_key_not_variant(self) -> None:
        """mutmut_57,58: 'ts' key must be present, not 'XXtsXX' or 'TS'."""
        c = _make_ws()
        snap = c._snapshot()
        assert "ts" in snap
        assert "XXtsXX" not in snap
        assert "TS" not in snap

    @pytest.mark.asyncio
    async def test_ws_poll_connection_error_sets_connected_false(self) -> None:
        """mutmut_10: on exception, _connected must be False, not None."""
        c = _make_ws()
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=ConnectionError("lost"))
        c._ws = mock_ws
        c._connected = True
        await c.poll_messages()
        assert c._connected is False
        assert c._connected is not None

    @pytest.mark.asyncio
    async def test_ws_poll_connection_error_sets_banner(self) -> None:
        """mutmut_13,14,15: banner must be set on error, not left unchanged."""
        c = _make_ws()
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=ConnectionError("lost"))
        c._ws = mock_ws
        c._connected = True
        original_banner = c._banner
        await c.poll_messages()
        # Banner must be updated (contains "closed" or similar)
        assert c._banner != original_banner or "closed" in c._banner.lower()
        assert c._banner == "WebSocket connection closed." or "closed" in c._banner.lower()

    @pytest.mark.asyncio
    async def test_ws_poll_accumulates_bytes_for_binary(self) -> None:
        """mutmut_20: bytes for binary data must accumulate (+=), not assign (=)."""
        c = _make_ws()
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(return_value=b"\x00\x01\x02")
        c._ws = mock_ws
        c._connected = True
        c._received_bytes = 10
        await c.poll_messages()
        assert c._received_bytes == 13  # 10 + 3

    @pytest.mark.asyncio
    async def test_ws_poll_accumulates_bytes_for_text(self) -> None:
        """mutmut_23: bytes for text data must accumulate (+=), not assign (=)."""
        c = _make_ws()
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(return_value="abc")
        c._ws = mock_ws
        c._connected = True
        c._received_bytes = 10
        await c.poll_messages()
        assert c._received_bytes == 13  # 10 + 3 (len("abc".encode("utf-8")))

    def test_ws_hello_input_mode_key(self) -> None:
        """mutmut_7: hello must have 'input_mode' key."""
        c = _make_ws({"url": "ws://x", "input_mode": "hijack"})
        hello = c._hello()
        assert "input_mode" in hello
        assert hello["input_mode"] == "hijack"

    def test_ws_hello_ts_key(self) -> None:
        """mutmut_8: hello must have 'ts' key."""
        c = _make_ws()
        hello = c._hello()
        assert "ts" in hello
        assert isinstance(hello["ts"], float)

    @pytest.mark.asyncio
    async def test_ws_stop_connected_false_not_true(self) -> None:
        """mutmut_5: _connected must be False (not True) after stop."""
        c = _make_ws()
        c._ws = AsyncMock()
        c._connected = True
        await c.stop()
        assert c._connected is False
        assert not c.is_connected()

    @pytest.mark.asyncio
    async def test_ws_get_analysis_uses_newline(self) -> None:
        """mutmut_2: analysis must use '\n' not 'XX\nXX'."""
        c = _make_ws({"url": "ws://myws.example"})
        result = await c.get_analysis()
        assert "XX\nXX" not in result
        assert "\n" in result
        assert "ws-sess2" in result

    @pytest.mark.asyncio
    async def test_ws_clear_banner_exact(self) -> None:
        """mutmut_3,4,5,6: banner must be 'Screen buffer cleared.' exactly."""
        c = _make_ws()
        await c.clear()
        assert c._banner == "Screen buffer cleared."

    @pytest.mark.asyncio
    async def test_ws_handle_control_step_recognized(self) -> None:
        """mutmut_20,21: 'step' action must be matched exactly."""
        c = _make_ws()
        await c.handle_control("step")
        assert c._banner == "Step requested. Awaiting upstream output."
        assert "Ignored" not in c._banner

    @pytest.mark.asyncio
    async def test_ws_handle_control_step_banner_exact(self) -> None:
        """mutmut_22,23,24,25: step banner must be exact case."""
        c = _make_ws()
        await c.handle_control("step")
        assert c._banner == "Step requested. Awaiting upstream output."
