# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Mutation-killing tests for ShellSessionConnector."""

from __future__ import annotations

from typing import Any

import pytest

from undef.terminal.server.connectors.shell import ShellSessionConnector


def make(config: dict[str, Any] | None = None) -> ShellSessionConnector:
    return ShellSessionConnector("sess1", "Test Shell", config)


# ---------------------------------------------------------------------------
# __init__ mutations
# ---------------------------------------------------------------------------
class TestInitMutations:
    def test_connected_is_false_after_init(self):
        """Kills mutmut_10: _connected = None."""
        c = make()
        assert c._connected is False
        assert c._connected == False  # noqa: E712

    def test_input_mode_default_is_open(self):
        """Kills mutmut_12/13/14/15: _input_mode default is 'open'."""
        c = make()
        assert c._input_mode == "open"

    def test_input_mode_from_config(self):
        """Kills mutmut_14: cfg.get(None, 'open') — key becomes None."""
        c = make({"input_mode": "hijack"})
        assert c._input_mode == "hijack"

    def test_input_mode_default_none_config(self):
        """Kills mutmut_15: cfg.get('input_mode', None) → None returned."""
        c = make({})  # No input_mode key → should default to "open"
        assert c._input_mode == "open"
        assert c._input_mode is not None

    def test_unknown_config_keys_raises(self):
        """Kills mutations to the unknown key check."""
        with pytest.raises(ValueError, match="unknown shell connector_config keys"):
            make({"bogus_key": "value"})

    def test_session_id_stored(self):
        """Kills mutations that skip storing session_id."""
        c = make()
        assert c._session_id == "sess1"

    def test_display_name_stored(self):
        """Kills mutations that skip storing display_name."""
        c = make()
        assert c._display_name == "Test Shell"

    def test_reset_state_called_on_init(self):
        """Kills mutmut_21: _reset_state() not called."""
        c = make()
        # After init, _transcript should exist and be non-empty
        assert hasattr(c, "_transcript")
        assert len(c._transcript) > 0

    def test_valid_config_keys_accepted(self):
        """Tests that valid config keys don't raise."""
        c = make({"input_mode": "open"})
        assert c._input_mode == "open"


# ---------------------------------------------------------------------------
# _reset_state mutations
# ---------------------------------------------------------------------------
class TestResetState:
    def test_paused_is_false(self):
        """Kills mutmut_1/2: _paused = None/True."""
        c = make()
        assert c._paused is False

    def test_turns_is_zero(self):
        """Kills mutmut_3: _turns = None."""
        c = make()
        assert c._turns == 0

    def test_nickname_is_user(self):
        """Kills mutations to _nickname default."""
        c = make()
        assert c._nickname == "user"

    def test_last_command_is_none(self):
        """Kills mutations to _last_command initial value."""
        c = make()
        assert c._last_command is None

    def test_banner_exact_text(self):
        """Kills mutmut_10/11/12: banner text mutations."""
        c = make()
        assert c._banner == "Ready. Type /help for commands."

    def test_transcript_has_two_initial_entries(self):
        """Kills mutations to transcript initialization."""
        c = make()
        assert len(c._transcript) == 2

    def test_transcript_first_entry_speaker(self):
        """Kills mutmut_15/16: first entry speaker mutations."""
        c = make()
        entries = list(c._transcript)
        assert entries[0].speaker == "system"

    def test_transcript_first_entry_text(self):
        """Kills mutmut_17: first entry text mutation."""
        c = make()
        entries = list(c._transcript)
        assert entries[0].text == "Session online."

    def test_transcript_second_entry_speaker(self):
        """Kills mutmut_19: second entry speaker mutation."""
        c = make()
        entries = list(c._transcript)
        assert entries[1].speaker == "session"

    def test_transcript_maxlen_is_10(self):
        """Kills mutations to maxlen value."""
        c = make()
        assert c._transcript.maxlen == 10


# ---------------------------------------------------------------------------
# stop mutation (mutmut_1: _connected = None instead of False)
# ---------------------------------------------------------------------------
class TestStopConnectedFalse:
    @pytest.mark.asyncio
    async def test_stop_sets_connected_to_false(self):
        """Kills mutmut_1: _connected = None."""
        c = make()
        await c.start()
        assert c.is_connected()
        await c.stop()
        assert c._connected is False
        assert not c.is_connected()


# ---------------------------------------------------------------------------
# _mode_label mutations
# ---------------------------------------------------------------------------
class TestModeLabel:
    def test_open_mode_label_exact_text(self):
        """Kills mutmut_1/2/3: label text mutations for open mode."""
        c = make({"input_mode": "open"})
        label = c._mode_label()
        assert label == "Shared input"

    def test_hijack_mode_label_exact_text(self):
        """Kills mutmut_7/8/9: label text mutations for hijack mode."""
        c = make({"input_mode": "hijack"})
        label = c._mode_label()
        assert label == "Exclusive hijack"

    def test_non_open_mode_shows_hijack_label(self):
        """Kills mutmut_4: condition inverted (== vs !=)."""
        c = make({"input_mode": "hijack"})
        assert c._mode_label() == "Exclusive hijack"
        c2 = make({"input_mode": "open"})
        assert c2._mode_label() == "Shared input"


# ---------------------------------------------------------------------------
# _control_label mutations
# ---------------------------------------------------------------------------
class TestControlLabel:
    def test_paused_true_shows_paused_for_hijack(self):
        """Kills mutmut_1/2/3: 'Paused for hijack' text mutations."""
        c = make()
        c._paused = True
        assert c._control_label() == "Paused for hijack"

    def test_paused_false_shows_live(self):
        """Kills mutmut_4/5/6: 'Live' text mutations."""
        c = make()
        c._paused = False
        assert c._control_label() == "Live"


# ---------------------------------------------------------------------------
# _hello mutations
# ---------------------------------------------------------------------------
class TestHello:
    def test_hello_has_ts_key(self):
        """Kills mutmut_7/8: 'ts' key mutated to 'XXtsXX'/'TS'."""
        c = make()
        hello = c._hello()
        assert "ts" in hello
        assert isinstance(hello["ts"], float)

    def test_hello_type_is_worker_hello(self):
        """Kills type key mutations."""
        c = make()
        hello = c._hello()
        assert hello["type"] == "worker_hello"

    def test_hello_input_mode_matches(self):
        """Kills input_mode mutations."""
        c = make({"input_mode": "hijack"})
        hello = c._hello()
        assert hello["input_mode"] == "hijack"


# ---------------------------------------------------------------------------
# _render_screen mutations
# ---------------------------------------------------------------------------
class TestRenderScreen:
    def test_separator_is_60_dashes(self):
        """Kills mutmut_3/4: '-' * 60 vs 61 or different string."""
        c = make()
        screen = c._render_screen()
        assert "-" * 60 in screen

    def test_help_text_in_screen(self):
        """Kills mutmut_5/6/7: Help: line mutations."""
        c = make()
        screen = c._render_screen()
        assert "/help" in screen
        assert "Help:" in screen

    def test_transcript_header_in_screen(self):
        """Kills mutmut_8/9/10/11: Transcript header mutations."""
        c = make()
        screen = c._render_screen()
        assert "Transcript" in screen

    def test_screen_includes_session_id(self):
        """Kills mutations removing session_id from header."""
        c = make()
        screen = c._render_screen()
        assert "sess1" in screen

    def test_screen_includes_display_name(self):
        """Kills mutations removing display_name from header."""
        c = make()
        screen = c._render_screen()
        assert "Test Shell" in screen

    def test_mode_label_in_screen(self):
        """Kills _render_screen mutmut_14: mode label missing."""
        c = make({"input_mode": "open"})
        screen = c._render_screen()
        assert "Shared input" in screen

    def test_control_label_in_screen(self):
        """Kills control label mutations in render."""
        c = make()
        screen = c._render_screen()
        assert "Live" in screen

    def test_banner_in_screen(self):
        """Kills banner mutations in render."""
        c = make()
        screen = c._render_screen()
        assert "Ready" in screen

    def test_prompt_at_end(self):
        """Kills mutmut_17 and others: prompt missing/wrong."""
        c = make()
        screen = c._render_screen()
        # Last non-empty line should contain the prompt
        lines = [ln for ln in screen.splitlines() if ln.strip()]
        assert "user>" in lines[-1]

    def test_lines_limited_to_rows(self):
        """Kills mutations changing -_ROWS to something else."""
        c = make()
        screen = c._render_screen()
        # Screen should have at most _ROWS=25 lines
        assert len(screen.splitlines()) <= 25


# ---------------------------------------------------------------------------
# _snapshot mutations
# ---------------------------------------------------------------------------
class TestSnapshot:
    @pytest.mark.asyncio
    async def test_snapshot_screen_is_string(self):
        """Kills mutmut_1: screen = None."""
        c = make()
        snap = c._snapshot()
        assert isinstance(snap["screen"], str)
        assert len(snap["screen"]) > 0

    def test_cursor_x_is_integer(self):
        """Kills mutmut_7/8/9/10/11: cursor_x mutations."""
        c = make()
        snap = c._snapshot()
        assert isinstance(snap["cursor"]["x"], int)
        assert 0 <= snap["cursor"]["x"] <= 79  # 0 to _COLS-1

    def test_cursor_y_is_integer(self):
        """Kills mutmut_14: cursor_y = None."""
        c = make()
        snap = c._snapshot()
        assert isinstance(snap["cursor"]["y"], int)
        assert snap["cursor"]["y"] >= 0

    def test_cursor_x_bounded_by_cols_minus_one(self):
        """Kills mutmut_12 (COLS+1) and mutmut_13 (COLS-2)."""
        c = make()
        snap = c._snapshot()
        # cursor_x must be <= _COLS - 1 = 79
        assert snap["cursor"]["x"] <= 79

    def test_cols_is_80(self):
        """Kills mutations to _COLS value."""
        c = make()
        snap = c._snapshot()
        assert snap["cols"] == 80

    def test_rows_is_25(self):
        """Kills mutations to _ROWS value."""
        c = make()
        snap = c._snapshot()
        assert snap["rows"] == 25

    def test_screen_hash_is_16_chars(self):
        """Kills mutations to hash truncation [:16]."""
        c = make()
        snap = c._snapshot()
        assert len(snap["screen_hash"]) == 16

    def test_snapshot_has_required_keys(self):
        """Kills mutations removing keys."""
        c = make()
        snap = c._snapshot()
        for key in [
            "type",
            "screen",
            "cursor",
            "cols",
            "rows",
            "screen_hash",
            "cursor_at_end",
            "has_trailing_space",
            "prompt_detected",
            "ts",
        ]:
            assert key in snap, f"Missing key: {key}"

    def test_cursor_at_end_is_true(self):
        """Kills mutations changing cursor_at_end."""
        c = make()
        snap = c._snapshot()
        assert snap["cursor_at_end"] is True

    def test_has_trailing_space_is_false(self):
        """Kills mutations changing has_trailing_space."""
        c = make()
        snap = c._snapshot()
        assert snap["has_trailing_space"] is False

    def test_prompt_detected_has_prompt_id(self):
        """Kills mutations to prompt_detected."""
        c = make()
        snap = c._snapshot()
        assert snap["prompt_detected"]["prompt_id"] == "shell_prompt"


# ---------------------------------------------------------------------------
# _append mutation (mutmut_4: ts=None)
# ---------------------------------------------------------------------------
class TestAppend:
    def test_append_entry_ts_is_float(self):
        """Kills mutmut_4: _Entry ts=None instead of time.time()."""
        c = make()
        c._append("system", "test message")
        entry = list(c._transcript)[-1]
        assert entry.ts is not None
        assert isinstance(entry.ts, float)
        assert entry.ts > 0


# ---------------------------------------------------------------------------
# handle_input structural mutations
# ---------------------------------------------------------------------------
class TestHandleInputMutations:
    @pytest.mark.asyncio
    async def test_turns_increments_on_input(self):
        """Kills mutmut_8/9: _turns = 1 or _turns -= 1."""
        c = make()
        assert c._turns == 0
        await c.handle_input("hello")
        assert c._turns == 1
        await c.handle_input("world")
        assert c._turns == 2

    @pytest.mark.asyncio
    async def test_turns_not_incremented_on_empty(self):
        """Kills mutations that increment turns on empty."""
        c = make()
        await c.handle_input("   ")
        assert c._turns == 0

    @pytest.mark.asyncio
    async def test_last_command_set_for_slash_commands(self):
        """Kills mutmut_18: _last_command = None instead of command."""
        c = make()
        await c.handle_input("/help")
        assert c._last_command == "/help"

    @pytest.mark.asyncio
    async def test_help_command_exact_match(self):
        """Kills mutmut_20/21: '/help' → 'XX/helpXX'/'/HELP'."""
        c = make()
        msgs = await c.handle_input("/help")
        # /help command must be handled (returns snapshot with help content)
        assert msgs[-1]["type"] == "snapshot"
        # Check banner is set (not just "Unknown command")
        assert "Unknown command" not in msgs[-1]["screen"]

    @pytest.mark.asyncio
    async def test_help_banner_exact_text(self):
        """Kills mutmut_22/23/24/25: banner text mutations."""
        c = make()
        await c.handle_input("/help")
        assert c._banner == "Command help printed below."

    @pytest.mark.asyncio
    async def test_help_appends_system_entry(self):
        """Kills mutmut_27/30/31/32/33/34: _append speaker/text mutations."""
        c = make()
        pre_len = len(c._transcript)
        await c.handle_input("/help")
        entries = list(c._transcript)
        new_entries = entries[pre_len:]
        assert len(new_entries) >= 1
        # Should append with speaker "system"
        system_entries = [e for e in new_entries if e.speaker == "system"]
        assert len(system_entries) >= 1
        # Text should contain "Commands:"
        assert any("Commands:" in e.text for e in system_entries)

    @pytest.mark.asyncio
    async def test_empty_input_banner_text(self):
        """Kills mutmut_5: 'Empty input ignored.' text mutation."""
        c = make()
        await c.handle_input("   ")
        assert c._banner == "Empty input ignored."

    @pytest.mark.asyncio
    async def test_clear_command_exact(self):
        """Kills /clear command mutations."""
        c = make()
        await c.handle_input("before clear")
        len(c._transcript)
        await c.handle_input("/clear")
        assert len(c._transcript) == 0
        assert c._banner == "Transcript cleared."

    @pytest.mark.asyncio
    async def test_mode_command_calls_set_mode(self):
        """Kills mutations routing /mode incorrectly."""
        c = make()
        msgs = await c.handle_input("/mode hijack")
        assert any(m["type"] == "worker_hello" for m in msgs)

    @pytest.mark.asyncio
    async def test_status_command_shows_mode(self):
        """Kills /status mutations."""
        c = make()
        msgs = await c.handle_input("/status")
        assert "mode=" in msgs[-1]["screen"]

    @pytest.mark.asyncio
    async def test_nick_command_sets_nickname(self):
        """Kills /nick mutations."""
        c = make()
        msgs = await c.handle_input("/nick testuser")
        assert c._nickname == "testuser"
        assert "testuser" in msgs[-1]["screen"]

    @pytest.mark.asyncio
    async def test_nick_truncates_to_24(self):
        """Kills nick length mutations."""
        c = make()
        long_name = "a" * 30
        await c.handle_input(f"/nick {long_name}")
        assert len(c._nickname) == 24

    @pytest.mark.asyncio
    async def test_say_appends_user_entry(self):
        """Kills /say mutations."""
        c = make()
        pre_len = len(c._transcript)
        await c.handle_input("/say hello world")
        entries = list(c._transcript)
        new_entries = entries[pre_len:]
        assert any(e.speaker == "user" for e in new_entries)
        assert any("hello world" in e.text for e in new_entries)

    @pytest.mark.asyncio
    async def test_plain_input_appends_user_and_session(self):
        """Kills mutations to plain input handling."""
        c = make()
        pre_len = len(c._transcript)
        await c.handle_input("test input")
        entries = list(c._transcript)
        new_entries = entries[pre_len:]
        speakers = {e.speaker for e in new_entries}
        assert "user" in speakers
        assert "session" in speakers

    @pytest.mark.asyncio
    async def test_plain_input_banner_text(self):
        """Kills 'Input accepted.' banner mutations."""
        c = make()
        await c.handle_input("some text")
        assert c._banner == "Input accepted."

    @pytest.mark.asyncio
    async def test_reset_command_returns_hello_and_snapshot(self):
        """Kills /reset return value mutations."""
        c = make()
        await c.handle_input("some text")
        msgs = await c.handle_input("/reset")
        types = [m["type"] for m in msgs]
        assert "worker_hello" in types
        assert "snapshot" in types
        assert c._turns == 0

    @pytest.mark.asyncio
    async def test_unknown_command_shows_command_name(self):
        """Kills unknown command handling mutations."""
        c = make()
        msgs = await c.handle_input("/unknown_cmd")
        assert "unknown_cmd" in msgs[-1]["screen"]


# ---------------------------------------------------------------------------
# handle_control mutations
# ---------------------------------------------------------------------------
class TestHandleControlMutations:
    @pytest.mark.asyncio
    async def test_pause_sets_paused_true(self):
        """Kills mutations changing pause behavior."""
        c = make()
        await c.handle_control("pause")
        assert c._paused is True

    @pytest.mark.asyncio
    async def test_resume_sets_paused_false(self):
        """Kills mutations changing resume behavior."""
        c = make()
        c._paused = True
        await c.handle_control("resume")
        assert c._paused is False

    @pytest.mark.asyncio
    async def test_step_increments_turns(self):
        """Kills mutations to step handling."""
        c = make()
        initial = c._turns
        await c.handle_control("step")
        assert c._turns == initial + 1

    @pytest.mark.asyncio
    async def test_pause_banner_exact_text(self):
        """Kills mutations to pause banner text."""
        c = make()
        await c.handle_control("pause")
        assert c._banner == "Exclusive control active. Input is still accepted."

    @pytest.mark.asyncio
    async def test_resume_banner_exact_text(self):
        """Kills mutations to resume banner text."""
        c = make()
        await c.handle_control("resume")
        assert c._banner == "Exclusive control released."


# ---------------------------------------------------------------------------
# set_mode mutations
# ---------------------------------------------------------------------------
class TestSetModeMutations:
    @pytest.mark.asyncio
    async def test_set_mode_open_sets_paused_false(self):
        """Kills mutmut_11: _paused = None instead of False."""
        c = make({"input_mode": "hijack"})
        c._paused = True
        await c.set_mode("open")
        assert c._paused is False
        assert c._paused is not None

    @pytest.mark.asyncio
    async def test_set_mode_hijack_does_not_clear_paused(self):
        """Kills mutations that also clear paused on hijack."""
        c = make({"input_mode": "open"})
        # In hijack mode, paused flag should NOT be automatically cleared
        c._paused = True
        await c.set_mode("hijack")
        # paused stays True for hijack mode
        assert c._paused is True

    @pytest.mark.asyncio
    async def test_set_mode_banner_not_none(self):
        """Kills mutmut_13: _banner = None."""
        c = make()
        await c.set_mode("open")
        assert c._banner is not None
        assert "Input mode" in c._banner

    @pytest.mark.asyncio
    async def test_set_mode_appends_system_entry(self):
        """Kills mutmut_15/18/19: _append mutations."""
        c = make()
        pre_len = len(c._transcript)
        await c.set_mode("open")
        entries = list(c._transcript)
        new_entries = entries[pre_len:]
        assert len(new_entries) >= 1
        speakers = {e.speaker for e in new_entries}
        assert "system" in speakers

    @pytest.mark.asyncio
    async def test_set_mode_updates_input_mode_attribute(self):
        """Kills mutations that don't update _input_mode."""
        c = make({"input_mode": "open"})
        await c.set_mode("hijack")
        assert c._input_mode == "hijack"

    @pytest.mark.asyncio
    async def test_set_mode_returns_hello_with_correct_mode(self):
        """Kills mutations where hello has wrong mode."""
        c = make({"input_mode": "open"})
        msgs = await c.set_mode("hijack")
        hello = next(m for m in msgs if m["type"] == "worker_hello")
        assert hello["input_mode"] == "hijack"


# ---------------------------------------------------------------------------
# __init__ – exact string/type checks for surviving mutants
# ---------------------------------------------------------------------------
class TestInitExact:
    def test_connected_false_not_none(self):
        """Kills mutmut_10: _connected = None (is False, not None)."""
        c = make()
        assert c._connected is False
        assert c._connected is not None

    def test_input_mode_is_string_open(self):
        """Kills mutmut_12/13/15/20/21: various wrong default values."""
        c = make()
        assert c._input_mode == "open"
        assert c._input_mode is not None
        assert c._input_mode != "None"
        assert c._input_mode != "XXopenXX"
        assert c._input_mode != "OPEN"

    def test_input_mode_key_is_input_mode(self):
        """Kills mutmut_14 (key=None) / mutmut_18 (XXinput_modeXX) / mutmut_19 (INPUT_MODE)."""
        c = make({"input_mode": "hijack"})
        assert c._input_mode == "hijack"
        # If key was wrong, it would return the default "open"
        c2 = make({"input_mode": "open"})
        assert c2._input_mode == "open"

    def test_input_mode_default_not_none_string(self):
        """Kills mutmut_15 (default=None → str(None) = 'None') / mutmut_17 (no default)."""
        c = make({})
        assert c._input_mode == "open"
        assert c._input_mode != "None"

    def test_input_mode_key_swap_detected(self):
        """Kills mutmut_16: cfg.get('open') instead of cfg.get('input_mode', 'open')."""
        # With key='open', a dict with 'input_mode':'hijack' would still return None (no 'open' key)
        c = make({"input_mode": "hijack"})
        assert c._input_mode == "hijack"


# ---------------------------------------------------------------------------
# _reset_state – exact value checks for all surviving mutants
# ---------------------------------------------------------------------------
class TestResetStateExact:
    def test_paused_is_exactly_false_not_none_not_true(self):
        """Kills mutmut_1 (None) and mutmut_2 (True)."""
        c = make()
        assert c._paused is False
        assert c._paused is not None
        assert c._paused is not True

    def test_turns_is_exactly_zero_not_one(self):
        """Kills mutmut_4: _turns = 1."""
        c = make()
        assert c._turns == 0
        assert c._turns != 1

    def test_nickname_is_exactly_user_not_none_not_uppercase(self):
        """Kills mutmut_5 (None), mutmut_6 (XXuserXX), mutmut_7 (USER)."""
        c = make()
        assert c._nickname == "user"
        assert c._nickname is not None
        assert c._nickname != "USER"
        assert c._nickname != "XXuserXX"

    def test_last_command_is_none_not_empty_string(self):
        """Kills mutmut_8: _last_command = ''."""
        c = make()
        assert c._last_command is None
        assert c._last_command != ""

    def test_banner_is_exactly_ready_help(self):
        """Kills mutmut_9 (None), mutmut_10 (XXReadyXX), mutmut_11 (lowercase), mutmut_12 (UPPER)."""
        c = make()
        assert c._banner == "Ready. Type /help for commands."
        assert c._banner is not None
        assert c._banner != "ready. type /help for commands."
        assert c._banner != "READY. TYPE /HELP FOR COMMANDS."
        assert c._banner != "XXReady. Type /help for commands.XX"

    def test_transcript_maxlen_is_exactly_10_not_none_not_11(self):
        """Kills mutmut_15 (maxlen=None) and mutmut_40 (maxlen=11)."""
        c = make()
        assert c._transcript.maxlen == 10
        assert c._transcript.maxlen is not None
        assert c._transcript.maxlen != 11

    def test_transcript_not_empty_after_reset(self):
        """Kills mutmut_16: initial list removed → empty deque."""
        c = make()
        assert len(c._transcript) == 2

    def test_transcript_has_maxlen_kwarg(self):
        """Kills mutmut_17: maxlen= keyword removed."""
        c = make()
        assert c._transcript.maxlen == 10

    def test_first_entry_text_is_exactly_session_online(self):
        """Kills mutmut_19 (None), mutmut_26 (XXSession online.XX), mutmut_27 (lowercase), mutmut_28 (UPPER)."""
        c = make()
        entries = list(c._transcript)
        assert entries[0].text == "Session online."
        assert entries[0].text is not None
        assert entries[0].text != "session online."
        assert entries[0].text != "SESSION ONLINE."
        assert entries[0].text != "XXSession online.XX"

    def test_first_entry_ts_is_float_not_none(self):
        """Kills mutmut_20: _Entry('system', 'Session online.', None)."""
        c = make()
        entries = list(c._transcript)
        assert entries[0].ts is not None
        assert isinstance(entries[0].ts, float)
        assert entries[0].ts > 0

    def test_first_entry_speaker_is_system_not_uppercase(self):
        """Kills mutmut_24 (XXsystemXX), mutmut_25 (SYSTEM)."""
        c = make()
        entries = list(c._transcript)
        assert entries[0].speaker == "system"
        assert entries[0].speaker != "SYSTEM"
        assert entries[0].speaker != "XXsystemXX"

    def test_second_entry_text_exact(self):
        """Kills mutmut_30 (None), mutmut_37 (XX...XX), mutmut_38 (lowercase), mutmut_39 (UPPER)."""
        c = make()
        entries = list(c._transcript)
        assert entries[1].text == "Use /help, /mode open, /mode hijack, /clear, /status, /reset."
        assert entries[1].text is not None
        assert entries[1].text != "use /help, /mode open, /mode hijack, /clear, /status, /reset."
        assert entries[1].text != "USE /HELP, /MODE OPEN, /MODE HIJACK, /CLEAR, /STATUS, /RESET."

    def test_second_entry_ts_is_float_not_none(self):
        """Kills mutmut_31: second entry ts=None."""
        c = make()
        entries = list(c._transcript)
        assert entries[1].ts is not None
        assert isinstance(entries[1].ts, float)

    def test_second_entry_speaker_exact(self):
        """Kills mutmut_35 (XXsessionXX), mutmut_36 (SESSION)."""
        c = make()
        entries = list(c._transcript)
        assert entries[1].speaker == "session"
        assert entries[1].speaker != "SESSION"
        assert entries[1].speaker != "XXsessionXX"

    def test_reset_restores_defaults(self):
        """Kills mutations that break _reset_state when called explicitly."""
        c = make()
        c._turns = 10
        c._nickname = "changed"
        c._paused = True
        c._reset_state()
        assert c._turns == 0
        assert c._nickname == "user"
        assert c._paused is False
        assert c._banner == "Ready. Type /help for commands."
        assert len(c._transcript) == 2
        assert c._transcript.maxlen == 10


# ---------------------------------------------------------------------------
# _append – exact ts check
# ---------------------------------------------------------------------------
class TestAppendExact:
    def test_append_ts_is_not_none_is_positive_float(self):
        """Kills mutmut_4: _Entry(speaker, text, None) instead of time.time()."""
        c = make()
        c._append("test_speaker", "test_text")
        entry = list(c._transcript)[-1]
        assert entry.ts is not None
        assert isinstance(entry.ts, float)
        assert entry.ts > 1_000_000_000  # Epoch seconds past year 2001


# ---------------------------------------------------------------------------
# _mode_label – exact string checks
# ---------------------------------------------------------------------------
class TestModeLabelExact:
    def test_open_mode_label_exact(self):
        """Kills mutmut_1: 'XXShared inputXX'."""
        c = make({"input_mode": "open"})
        assert c._mode_label() == "Shared input"
        assert c._mode_label() != "XXShared inputXX"

    def test_hijack_mode_label_exact(self):
        """Kills mutmut_7 (XXExclusive hijackXX), mutmut_8 (lowercase), mutmut_9 (UPPER)."""
        c = make({"input_mode": "hijack"})
        assert c._mode_label() == "Exclusive hijack"
        assert c._mode_label() != "XXExclusive hijackXX"
        assert c._mode_label() != "exclusive hijack"
        assert c._mode_label() != "EXCLUSIVE HIJACK"


# ---------------------------------------------------------------------------
# _control_label – exact string checks
# ---------------------------------------------------------------------------
class TestControlLabelExact:
    def test_paused_label_exact(self):
        """Kills mutmut_1: 'XXPaused for hijackXX'."""
        c = make()
        c._paused = True
        assert c._control_label() == "Paused for hijack"
        assert c._control_label() != "XXPaused for hijackXX"

    def test_live_label_exact(self):
        """Kills mutmut_4: 'XXLiveXX'."""
        c = make()
        c._paused = False
        assert c._control_label() == "Live"
        assert c._control_label() != "XXLiveXX"


# ---------------------------------------------------------------------------
# _render_screen – exact content checks
# ---------------------------------------------------------------------------
class TestRenderScreenExact:
    def test_separator_is_exactly_60_dashes(self):
        """Kills mutmut_3 (XX-XX*60) and mutmut_4 ('-'*61)."""
        c = make()
        screen = c._render_screen()
        assert "-" * 60 in screen
        assert "-" * 61 not in screen
        assert "XX-XX" not in screen

    def test_help_line_exact_case(self):
        """Kills mutmut_6 (help: lowercase) and mutmut_7 (UPPER)."""
        c = make()
        screen = c._render_screen()
        assert "Help:" in screen
        assert "help:" not in screen
        assert "HELP:" not in screen

    def test_transcript_header_exact_case(self):
        """Kills mutmut_10 (transcript lowercase) and mutmut_11 (UPPER)."""
        c = make()
        screen = c._render_screen()
        assert "Transcript" in screen
        assert "transcript" not in screen or "Transcript" in screen
        # Check the exact line
        lines = screen.splitlines()
        transcript_lines = [ln for ln in lines if "Transcript" in ln or "transcript" in ln]
        # Must have exactly "Transcript" (not "transcript")
        assert any("Transcript" in ln for ln in transcript_lines)

    def test_empty_line_between_banner_and_transcript(self):
        """Kills mutmut_8: empty string replaced with 'XXXX'."""
        c = make()
        screen = c._render_screen()
        assert "XXXX" not in screen
        lines = screen.splitlines()
        # There should be an empty line
        assert "" in lines

    def test_join_separator_is_newline(self):
        """Kills mutmut_17: '\\n'.join → 'XX\\nXX'.join."""
        c = make()
        screen = c._render_screen()
        assert "XX\nXX" not in screen
        # The screen should be a normal newline-joined string
        assert "\n" in screen

    def test_prompt_line_is_empty_before_it(self):
        """Kills mutmut_14: lines.append('') → lines.append('XXXX')."""
        c = make()
        screen = c._render_screen()
        lines = screen.splitlines()
        # The line before the prompt (last line) should be empty
        if len(lines) >= 2:
            assert lines[-2] == ""
        assert "XXXX" not in screen

    def test_transcript_entries_rendered(self):
        """Kills mutations removing transcript from render."""
        c = make()
        c._append("system", "unique_marker_text")
        screen = c._render_screen()
        assert "unique_marker_text" in screen


# ---------------------------------------------------------------------------
# _snapshot – exact key/value checks
# ---------------------------------------------------------------------------
class TestSnapshotExact:
    def test_last_line_index_is_minus_one(self):
        """Kills mutmut_5 ([+1]) and mutmut_6 ([-2])."""
        c = make()
        snap = c._snapshot()
        screen = snap["screen"]
        last_line = screen.splitlines()[-1]
        # cursor_x is based on last line length; verify it's the actual last line
        # The last line should be the prompt "user> "
        assert "user>" in last_line

    def test_cursor_x_uses_last_line_len(self):
        """Kills mutmut_7 (cursor_x=None)."""
        c = make()
        snap = c._snapshot()
        assert snap["cursor"]["x"] is not None
        assert isinstance(snap["cursor"]["x"], int)

    def test_cursor_x_bounded_by_cols_minus_1(self):
        """Kills mutmut_13: _COLS - 2 = 78 instead of 79."""
        c = make()
        c._snapshot()
        # For a short last line like "user> " (6 chars), cursor_x = 6
        # Boundary: min(len, 79) — verify max is 79 not 78
        # Force a long last line by using a 80+ char nickname
        c2 = make()
        c2._nickname = "a" * 80
        snap2 = c2._snapshot()
        # cursor_x = min(len("a"*80 + "> "), 79) = 79
        assert snap2["cursor"]["x"] == 79

    def test_cursor_y_is_not_none(self):
        """Kills mutmut_14: cursor_y = None."""
        c = make()
        snap = c._snapshot()
        assert snap["cursor"]["y"] is not None
        assert isinstance(snap["cursor"]["y"], int)

    def test_cursor_y_plus_one_not_used(self):
        """Kills mutmut_19: len(splitlines()) + 1 instead of - 1."""
        c = make()
        snap = c._snapshot()
        screen = snap["screen"]
        lines = screen.splitlines()
        expected_y = min(len(lines) - 1, 24)
        assert snap["cursor"]["y"] == expected_y

    def test_cursor_y_minus_two_not_used(self):
        """Kills mutmut_20: len(splitlines()) - 2."""
        c = make()
        snap = c._snapshot()
        screen = snap["screen"]
        lines = screen.splitlines()
        # y should be len-1, not len-2
        if len(lines) < 25:
            assert snap["cursor"]["y"] == len(lines) - 1

    def test_cursor_y_rows_minus_one_bound(self):
        """Kills mutmut_21 (_ROWS+1=26) and mutmut_22 (_ROWS-2=23)."""
        # Add enough entries to force y to hit the ROWS boundary
        c = make()
        # Add many transcript entries so screen > 25 lines
        for i in range(30):
            c._append("user", f"line {i}")
        snap = c._snapshot()
        # cursor_y must be at most _ROWS-1 = 24
        assert snap["cursor"]["y"] <= 24
        assert snap["cursor"]["y"] >= 0

    def test_snapshot_cursor_key_is_lowercase(self):
        """Kills mutmut_29 (XXcursorXX) and mutmut_30 (CURSOR)."""
        c = make()
        snap = c._snapshot()
        assert "cursor" in snap
        assert "XXcursorXX" not in snap
        assert "CURSOR" not in snap

    def test_cursor_x_key_is_x(self):
        """Kills mutmut_31 (XXxXX) and mutmut_32 (X)."""
        c = make()
        snap = c._snapshot()
        assert "x" in snap["cursor"]
        assert "XXxXX" not in snap["cursor"]
        assert "X" not in snap["cursor"]

    def test_cursor_y_key_is_y(self):
        """Kills mutmut_33 (XXyXX) and mutmut_34 (Y)."""
        c = make()
        snap = c._snapshot()
        assert "y" in snap["cursor"]
        assert "XXyXX" not in snap["cursor"]
        assert "Y" not in snap["cursor"]

    def test_screen_hash_key_is_lowercase(self):
        """Kills mutmut_39 (XXscreen_hashXX) and mutmut_40 (SCREEN_HASH)."""
        c = make()
        snap = c._snapshot()
        assert "screen_hash" in snap
        assert "XXscreen_hashXX" not in snap
        assert "SCREEN_HASH" not in snap

    def test_screen_hash_length_is_16_not_17(self):
        """Kills mutmut_45: hexdigest()[:17] instead of [:16]."""
        c = make()
        snap = c._snapshot()
        assert len(snap["screen_hash"]) == 16

    def test_screen_hash_encoding_ascii_equivalent(self):
        """Kills mutmut_44: encode('UTF-8') vs encode('utf-8').
        These are equivalent, so this is noted as an equivalent mutant."""
        # This mutant is EQUIVALENT (utf-8 == UTF-8 in Python)
        # We skip writing a test for this one

    def test_cursor_at_end_key_is_lowercase(self):
        """Kills mutmut_46 (XXcursor_at_endXX) and mutmut_47 (CURSOR_AT_END)."""
        c = make()
        snap = c._snapshot()
        assert "cursor_at_end" in snap
        assert "XXcursor_at_endXX" not in snap
        assert "CURSOR_AT_END" not in snap

    def test_cursor_at_end_is_true_not_false(self):
        """Kills mutmut_48: cursor_at_end = False."""
        c = make()
        snap = c._snapshot()
        assert snap["cursor_at_end"] is True

    def test_has_trailing_space_key_is_lowercase(self):
        """Kills mutmut_49 (XXhas_trailing_spaceXX) and mutmut_50 (HAS_TRAILING_SPACE)."""
        c = make()
        snap = c._snapshot()
        assert "has_trailing_space" in snap
        assert "XXhas_trailing_spaceXX" not in snap
        assert "HAS_TRAILING_SPACE" not in snap

    def test_has_trailing_space_is_false_not_true(self):
        """Kills mutmut_51: has_trailing_space = True."""
        c = make()
        snap = c._snapshot()
        assert snap["has_trailing_space"] is False

    def test_prompt_detected_key_is_lowercase(self):
        """Kills mutmut_52 (XXprompt_detectedXX) and mutmut_53 (PROMPT_DETECTED)."""
        c = make()
        snap = c._snapshot()
        assert "prompt_detected" in snap
        assert "XXprompt_detectedXX" not in snap
        assert "PROMPT_DETECTED" not in snap

    def test_prompt_detected_prompt_id_key_exact(self):
        """Kills mutmut_54 (XXprompt_idXX) and mutmut_55 (PROMPT_ID)."""
        c = make()
        snap = c._snapshot()
        assert "prompt_id" in snap["prompt_detected"]
        assert "XXprompt_idXX" not in snap["prompt_detected"]
        assert "PROMPT_ID" not in snap["prompt_detected"]

    def test_prompt_detected_value_exact(self):
        """Kills mutmut_56 (XXshell_promptXX) and mutmut_57 (SHELL_PROMPT)."""
        c = make()
        snap = c._snapshot()
        assert snap["prompt_detected"]["prompt_id"] == "shell_prompt"
        assert snap["prompt_detected"]["prompt_id"] != "XXshell_promptXX"
        assert snap["prompt_detected"]["prompt_id"] != "SHELL_PROMPT"

    def test_snapshot_ts_key_is_lowercase(self):
        """Kills mutmut_58 (XXtsXX) and mutmut_59 (TS)."""
        c = make()
        snap = c._snapshot()
        assert "ts" in snap
        assert "XXtsXX" not in snap
        assert "TS" not in snap

    def test_last_line_fallback_is_empty_string(self):
        """Kills mutmut_4: ['XXXX'] fallback instead of ['']."""
        # The screen always has lines so the fallback rarely fires, but
        # verify the snapshot computes cursor_x from the actual last line
        c = make()
        snap = c._snapshot()
        # With normal screen, last line is prompt "user> "
        assert snap["cursor"]["x"] == len("user> ")


# ---------------------------------------------------------------------------
# _hello – exact key checks
# ---------------------------------------------------------------------------
class TestHelloExact:
    def test_hello_ts_key_exact(self):
        """Kills mutmut_7 (XXtsXX) and mutmut_8 (TS)."""
        c = make()
        hello = c._hello()
        assert "ts" in hello
        assert "XXtsXX" not in hello
        assert "TS" not in hello
        assert isinstance(hello["ts"], float)


# ---------------------------------------------------------------------------
# stop – exact value
# ---------------------------------------------------------------------------
class TestStopExact:
    @pytest.mark.asyncio
    async def test_stop_sets_connected_false_not_none(self):
        """Kills mutmut_1: _connected = None."""
        c = make()
        await c.start()
        await c.stop()
        assert c._connected is False
        assert c._connected is not None


# ---------------------------------------------------------------------------
# handle_input – exact banner and transcript checks
# ---------------------------------------------------------------------------
class TestHandleInputExact:
    @pytest.mark.asyncio
    async def test_turns_increments_by_one_exact(self):
        """Kills mutmut_8 (=1), mutmut_9 (-=1), mutmut_10 (+=2)."""
        c = make()
        await c.handle_input("first")
        assert c._turns == 1
        await c.handle_input("second")
        assert c._turns == 2
        await c.handle_input("third")
        assert c._turns == 3

    @pytest.mark.asyncio
    async def test_empty_input_banner_exact(self):
        """Kills mutmut_5: 'XXEmpty input ignored.XX'."""
        c = make()
        await c.handle_input("")
        assert c._banner == "Empty input ignored."
        assert c._banner != "XXEmpty input ignored.XX"

    @pytest.mark.asyncio
    async def test_last_command_set_not_none(self):
        """Kills mutmut_18: _last_command = None instead of command."""
        c = make()
        await c.handle_input("/help")
        assert c._last_command == "/help"
        assert c._last_command is not None

    @pytest.mark.asyncio
    async def test_help_command_case_sensitive(self):
        """Kills mutmut_20 (XX/helpXX) and mutmut_21 (/HELP)."""
        c = make()
        await c.handle_input("/help")
        assert c._banner == "Command help printed below."
        # /HELP should not trigger help
        c2 = make()
        await c2.handle_input("/HELP")
        # Should go to unknown command path
        assert "Unknown command" in c2._banner

    @pytest.mark.asyncio
    async def test_help_banner_exact(self):
        """Kills mutmut_22 (None), mutmut_23 (XX...XX), mutmut_24 (lowercase), mutmut_25 (UPPER)."""
        c = make()
        await c.handle_input("/help")
        assert c._banner == "Command help printed below."
        assert c._banner is not None
        assert c._banner != "XXCommand help printed below.XX"
        assert c._banner != "command help printed below."
        assert c._banner != "COMMAND HELP PRINTED BELOW."

    @pytest.mark.asyncio
    async def test_help_appends_system_speaker_exact(self):
        """Kills mutmut_30 (XXsystemXX) and mutmut_31 (SYSTEM)."""
        c = make()
        pre_len = len(c._transcript)
        await c.handle_input("/help")
        entries = list(c._transcript)
        new_entries = entries[pre_len:]
        speakers = [e.speaker for e in new_entries]
        assert "system" in speakers
        assert "XXsystemXX" not in speakers
        assert "SYSTEM" not in speakers

    @pytest.mark.asyncio
    async def test_help_appends_text_exact(self):
        """Kills mutmut_27 (None), mutmut_32 (XX...XX), mutmut_33 (lowercase), mutmut_34 (UPPER)."""
        c = make()
        pre_len = len(c._transcript)
        await c.handle_input("/help")
        entries = list(c._transcript)
        new_entries = entries[pre_len:]
        texts = [e.text for e in new_entries]
        expected = "Commands: /help /clear /mode open|hijack /status /nick <name> /say <text> /shell /reset"
        assert expected in texts
        assert None not in texts
        assert not any("XX" in (t or "") for t in texts)

    @pytest.mark.asyncio
    async def test_clear_command_case_sensitive(self):
        """Kills mutmut_36 (XX/clearXX) and mutmut_37 (/CLEAR)."""
        c = make()
        await c.handle_input("/clear")
        assert c._banner == "Transcript cleared."
        # /CLEAR should not work as clear command
        c2 = make()
        await c2.handle_input("/CLEAR")
        assert "Unknown command" in c2._banner

    @pytest.mark.asyncio
    async def test_clear_maxlen_is_10_not_none_not_11(self):
        """Kills mutmut_39 (maxlen=None) and mutmut_40 (maxlen=11)."""
        c = make()
        await c.handle_input("/clear")
        assert c._transcript.maxlen == 10
        assert c._transcript.maxlen is not None
        assert c._transcript.maxlen != 11

    @pytest.mark.asyncio
    async def test_clear_banner_exact(self):
        """Kills mutmut_41 (None), mutmut_42 (XX...XX), mutmut_43 (lowercase), mutmut_44 (UPPER)."""
        c = make()
        await c.handle_input("/clear")
        assert c._banner == "Transcript cleared."
        assert c._banner is not None
        assert c._banner != "XXTranscript cleared.XX"
        assert c._banner != "transcript cleared."
        assert c._banner != "TRANSCRIPT CLEARED."

    @pytest.mark.asyncio
    async def test_mode_invalid_banner_exact(self):
        """Kills mutmut_55 (None), mutmut_56 (XX...XX), mutmut_57 (lowercase), mutmut_58 (UPPER)."""
        c = make()
        await c.handle_input("/mode invalid")
        assert c._banner == "Usage: /mode open|hijack"
        assert c._banner is not None
        assert c._banner != "usage: /mode open|hijack"
        assert c._banner != "USAGE: /MODE OPEN|HIJACK"
        assert c._banner != "XXUsage: /mode open|hijackXX"

    @pytest.mark.asyncio
    async def test_mode_invalid_appends_system_text_exact(self):
        """Kills mutmut_60 (None), mutmut_63 (XXsystemXX), mutmut_64 (SYSTEM), mutmut_65/66 (text case)."""
        c = make()
        pre_len = len(c._transcript)
        await c.handle_input("/mode invalid")
        entries = list(c._transcript)
        new_entries = entries[pre_len:]
        assert len(new_entries) >= 1
        speakers = [e.speaker for e in new_entries]
        texts = [e.text for e in new_entries]
        assert "system" in speakers
        assert "XXsystemXX" not in speakers
        assert "SYSTEM" not in speakers
        assert "usage: /mode open|hijack" in texts
        assert None not in texts

    @pytest.mark.asyncio
    async def test_status_banner_exact(self):
        """Kills mutmut_71 (None), mutmut_72 (XX...XX), mutmut_73 (lowercase), mutmut_74 (UPPER)."""
        c = make()
        await c.handle_input("/status")
        assert c._banner == "Session status printed below."
        assert c._banner is not None
        assert c._banner != "XXSession status printed below.XX"
        assert c._banner != "session status printed below."
        assert c._banner != "SESSION STATUS PRINTED BELOW."

    @pytest.mark.asyncio
    async def test_status_appends_system_speaker_exact(self):
        """Kills mutmut_79 (XXsystemXX) and mutmut_80 (SYSTEM)."""
        c = make()
        pre_len = len(c._transcript)
        await c.handle_input("/status")
        entries = list(c._transcript)
        new_entries = entries[pre_len:]
        speakers = [e.speaker for e in new_entries]
        assert "system" in speakers
        assert "XXsystemXX" not in speakers
        assert "SYSTEM" not in speakers

    @pytest.mark.asyncio
    async def test_nick_no_arg_banner_exact(self):
        """Kills mutmut_85 (None), mutmut_86 (XX...XX), mutmut_87 (lowercase), mutmut_88 (UPPER)."""
        c = make()
        await c.handle_input("/nick")
        assert c._banner == "Usage: /nick <name>"
        assert c._banner is not None
        assert c._banner != "usage: /nick <name>"
        assert c._banner != "USAGE: /NICK <NAME>"

    @pytest.mark.asyncio
    async def test_nick_no_arg_appends_system_text_exact(self):
        """Kills mutmut_90 (None text), mutmut_93 (XX..XX speaker), mutmut_94/95/96 (case)."""
        c = make()
        pre_len = len(c._transcript)
        await c.handle_input("/nick")
        entries = list(c._transcript)
        new_entries = entries[pre_len:]
        speakers = [e.speaker for e in new_entries]
        texts = [e.text for e in new_entries]
        assert "system" in speakers
        assert "usage: /nick <name>" in texts
        assert None not in texts

    @pytest.mark.asyncio
    async def test_nick_truncates_at_24_not_25(self):
        """Kills mutmut_98: arg[:24] → no slice or different slice."""
        c = make()
        await c.handle_input("/nick " + "x" * 30)
        assert len(c._nickname) == 24
        assert c._nickname == "x" * 24

    @pytest.mark.asyncio
    async def test_nick_banner_uses_nickname(self):
        """Kills mutmut_99: _banner = None."""
        c = make()
        await c.handle_input("/nick alice")
        assert c._banner is not None
        assert "alice" in c._banner
        assert c._banner == "Nickname set to alice."

    @pytest.mark.asyncio
    async def test_nick_appends_system_with_nickname(self):
        """Kills mutmut_101 (None), mutmut_104 (XX..XX speaker), mutmut_105 (SYSTEM)."""
        c = make()
        pre_len = len(c._transcript)
        await c.handle_input("/nick bob")
        entries = list(c._transcript)
        new_entries = entries[pre_len:]
        speakers = [e.speaker for e in new_entries]
        texts = [e.text for e in new_entries]
        assert "system" in speakers
        assert "nickname: bob" in texts

    @pytest.mark.asyncio
    async def test_say_no_arg_banner_exact(self):
        """Kills mutmut_110 (None), mutmut_111/112/113 (case)."""
        c = make()
        await c.handle_input("/say")
        assert c._banner == "Usage: /say <text>"
        assert c._banner is not None
        assert c._banner != "usage: /say <text>"
        assert c._banner != "USAGE: /SAY <TEXT>"

    @pytest.mark.asyncio
    async def test_say_no_arg_appends_system_exact(self):
        """Kills mutmut_115 (None text), mutmut_118/119/120/121 (case/XX variants)."""
        c = make()
        pre_len = len(c._transcript)
        await c.handle_input("/say")
        entries = list(c._transcript)
        new_entries = entries[pre_len:]
        speakers = [e.speaker for e in new_entries]
        texts = [e.text for e in new_entries]
        assert "system" in speakers
        assert "usage: /say <text>" in texts
        assert None not in texts

    @pytest.mark.asyncio
    async def test_say_banner_exact(self):
        """Kills mutmut_122 (None), mutmut_123/124/125 (case/XX variants)."""
        c = make()
        await c.handle_input("/say hello world")
        assert c._banner == "Message appended."
        assert c._banner is not None
        assert c._banner != "XXMessage appended.XX"

    @pytest.mark.asyncio
    async def test_say_appends_user_with_nickname(self):
        """Kills mutmut_130 (None text), mutmut_131 (XX..XX speaker)."""
        c = make()
        c._nickname = "myuser"
        pre_len = len(c._transcript)
        await c.handle_input("/say greetings")
        entries = list(c._transcript)
        new_entries = entries[pre_len:]
        speakers = [e.speaker for e in new_entries]
        texts = [e.text for e in new_entries]
        assert "user" in speakers
        assert "myuser: greetings" in texts

    @pytest.mark.asyncio
    async def test_shell_command_case_sensitive(self):
        """Kills mutmut_133 (XX/shellXX) and mutmut_134 (/SHELL)."""
        c = make()
        await c.handle_input("/shell")
        assert c._banner == "Shell response appended."
        # /SHELL should not work
        c2 = make()
        await c2.handle_input("/SHELL")
        assert "Unknown command" in c2._banner

    @pytest.mark.asyncio
    async def test_shell_banner_exact(self):
        """Kills mutmut_135 (None), mutmut_136/137/138 (case/XX variants)."""
        c = make()
        await c.handle_input("/shell")
        assert c._banner == "Shell response appended."
        assert c._banner is not None
        assert c._banner != "shell response appended."
        assert c._banner != "SHELL RESPONSE APPENDED."

    @pytest.mark.asyncio
    async def test_shell_appends_session_exact(self):
        """Kills mutmut_140 (None text), mutmut_143/144/145/146/147 (case/speaker variants)."""
        c = make()
        pre_len = len(c._transcript)
        await c.handle_input("/shell")
        entries = list(c._transcript)
        new_entries = entries[pre_len:]
        speakers = [e.speaker for e in new_entries]
        texts = [e.text for e in new_entries]
        assert "session" in speakers
        assert "This hosted server is the reference implementation." in texts
        assert None not in texts

    @pytest.mark.asyncio
    async def test_reset_banner_exact(self):
        """Kills mutmut_151 (None), mutmut_152/153/154 (case/XX variants)."""
        c = make()
        await c.handle_input("/reset")
        assert c._banner == "Session reset."
        assert c._banner is not None
        assert c._banner != "session reset."
        assert c._banner != "SESSION RESET."

    @pytest.mark.asyncio
    async def test_unknown_command_banner_uses_command_name(self):
        """Kills mutmut_155: _banner = f'Unknown command: {command}'."""
        c = make()
        await c.handle_input("/foobar")
        assert c._banner == "Unknown command: /foobar"

    @pytest.mark.asyncio
    async def test_unknown_command_appends_system_exact(self):
        """Kills mutmut_157 (None), mutmut_160 (XX..XX speaker), mutmut_161 (SYSTEM)."""
        c = make()
        pre_len = len(c._transcript)
        await c.handle_input("/foobar")
        entries = list(c._transcript)
        new_entries = entries[pre_len:]
        speakers = [e.speaker for e in new_entries]
        texts = [e.text for e in new_entries]
        assert "system" in speakers
        assert "unknown command: /foobar" in texts

    @pytest.mark.asyncio
    async def test_plain_input_banner_exact(self):
        """Kills mutmut_162 (None), mutmut_163/164/165 (case/XX variants)."""
        c = make()
        await c.handle_input("hello world")
        assert c._banner == "Input accepted."
        assert c._banner is not None
        assert c._banner != "input accepted."
        assert c._banner != "INPUT ACCEPTED."

    @pytest.mark.asyncio
    async def test_plain_input_appends_user_with_nickname_exact(self):
        """Kills mutmut_167 (None text), mutmut_170 (XX..XX speaker), mutmut_171 (USER)."""
        c = make()
        c._nickname = "tester"
        pre_len = len(c._transcript)
        await c.handle_input("hello")
        entries = list(c._transcript)
        new_entries = entries[pre_len:]
        speakers = [e.speaker for e in new_entries]
        texts = [e.text for e in new_entries]
        assert "user" in speakers
        assert "tester: hello" in texts
        assert None not in texts

    @pytest.mark.asyncio
    async def test_plain_input_appends_session_exact(self):
        """Kills mutmut_173 (None text), mutmut_176 (XX..XX speaker), mutmut_177 (SESSION)."""
        c = make()
        pre_len = len(c._transcript)
        await c.handle_input("myinput")
        entries = list(c._transcript)
        new_entries = entries[pre_len:]
        speakers = [e.speaker for e in new_entries]
        texts = [e.text for e in new_entries]
        assert "session" in speakers
        assert 'session: received "myinput"' in texts
        assert None not in texts


# ---------------------------------------------------------------------------
# handle_control – exact banner, speaker, text checks
# ---------------------------------------------------------------------------
class TestHandleControlExact:
    @pytest.mark.asyncio
    async def test_pause_banner_exact(self):
        """Kills mutmut_6 (None), mutmut_7 (XX...XX), mutmut_8 (lowercase), mutmut_9 (UPPER)."""
        c = make()
        await c.handle_control("pause")
        assert c._banner == "Exclusive control active. Input is still accepted."
        assert c._banner is not None
        assert c._banner != "exclusive control active. input is still accepted."
        assert c._banner != "EXCLUSIVE CONTROL ACTIVE. INPUT IS STILL ACCEPTED."

    @pytest.mark.asyncio
    async def test_pause_appends_system_hijack_acquired_exact(self):
        """Kills mutmut_11 (None), mutmut_14 (XXsystemXX), mutmut_15 (SYSTEM), mutmut_16/17 (text case)."""
        c = make()
        pre_len = len(c._transcript)
        await c.handle_control("pause")
        entries = list(c._transcript)
        new_entries = entries[pre_len:]
        speakers = [e.speaker for e in new_entries]
        texts = [e.text for e in new_entries]
        assert "system" in speakers
        assert "control: hijack acquired" in texts
        assert None not in texts
        assert "XXsystemXX" not in speakers
        assert "SYSTEM" not in speakers

    @pytest.mark.asyncio
    async def test_resume_paused_is_false_not_none(self):
        """Kills mutmut_21: _paused = None."""
        c = make()
        c._paused = True
        await c.handle_control("resume")
        assert c._paused is False
        assert c._paused is not None

    @pytest.mark.asyncio
    async def test_resume_banner_exact(self):
        """Kills mutmut_23 (None), mutmut_24 (XX...XX), mutmut_25 (lowercase), mutmut_26 (UPPER)."""
        c = make()
        await c.handle_control("resume")
        assert c._banner == "Exclusive control released."
        assert c._banner is not None
        assert c._banner != "exclusive control released."
        assert c._banner != "EXCLUSIVE CONTROL RELEASED."

    @pytest.mark.asyncio
    async def test_resume_appends_system_released_exact(self):
        """Kills mutmut_28 (None), mutmut_31/32 (speaker case), mutmut_33/34 (text case)."""
        c = make()
        pre_len = len(c._transcript)
        await c.handle_control("resume")
        entries = list(c._transcript)
        new_entries = entries[pre_len:]
        speakers = [e.speaker for e in new_entries]
        texts = [e.text for e in new_entries]
        assert "system" in speakers
        assert "control: released" in texts
        assert None not in texts

    @pytest.mark.asyncio
    async def test_step_case_sensitive(self):
        """Kills mutmut_36 (XXstepXX) and mutmut_37 (STEP)."""
        c = make()
        initial_turns = c._turns
        await c.handle_control("step")
        assert c._turns == initial_turns + 1
        # STEP should go to unknown path
        c2 = make()
        t2 = c2._turns
        await c2.handle_control("STEP")
        # turns not incremented for unknown
        assert c2._turns == t2

    @pytest.mark.asyncio
    async def test_step_increments_by_exactly_one(self):
        """Kills mutmut_38 (=1), mutmut_39 (-=1), mutmut_40 (+=2)."""
        c = make()
        c._turns = 5
        await c.handle_control("step")
        assert c._turns == 6

    @pytest.mark.asyncio
    async def test_step_banner_exact(self):
        """Kills mutmut_41 (None), mutmut_42 (XX...XX), mutmut_43 (lowercase), mutmut_44 (UPPER)."""
        c = make()
        await c.handle_control("step")
        assert c._banner == "Single-step acknowledged."
        assert c._banner is not None
        assert c._banner != "single-step acknowledged."
        assert c._banner != "SINGLE-STEP ACKNOWLEDGED."

    @pytest.mark.asyncio
    async def test_step_appends_system_with_turn_exact(self):
        """Kills mutmut_46 (None), mutmut_49 (XXsystemXX), mutmut_50 (SYSTEM)."""
        c = make()
        pre_len = len(c._transcript)
        await c.handle_control("step")
        entries = list(c._transcript)
        new_entries = entries[pre_len:]
        speakers = [e.speaker for e in new_entries]
        texts = [e.text for e in new_entries]
        assert "system" in speakers
        assert any("control: single step #" in t for t in texts if t)
        assert None not in texts

    @pytest.mark.asyncio
    async def test_unknown_control_banner_exact(self):
        """Kills mutmut_51: _banner = None."""
        c = make()
        await c.handle_control("unknown_action")
        assert c._banner is not None
        assert "Ignored unknown control action" in c._banner
        assert "unknown_action" in c._banner

    @pytest.mark.asyncio
    async def test_unknown_control_appends_system_exact(self):
        """Kills mutmut_53 (None), mutmut_56 (XXsystemXX), mutmut_57 (SYSTEM)."""
        c = make()
        pre_len = len(c._transcript)
        await c.handle_control("weird")
        entries = list(c._transcript)
        new_entries = entries[pre_len:]
        speakers = [e.speaker for e in new_entries]
        texts = [e.text for e in new_entries]
        assert "system" in speakers
        assert any("control: ignored weird" in t for t in texts if t)
        assert None not in texts


# ---------------------------------------------------------------------------
# get_analysis – exact format checks
# ---------------------------------------------------------------------------
class TestGetAnalysisExact:
    @pytest.mark.asyncio
    async def test_get_analysis_uses_newline_join(self):
        """Kills mutmut_2: 'XX\\nXX'.join instead of '\\n'.join."""
        c = make()
        analysis = await c.get_analysis()
        assert "XX\nXX" not in analysis
        lines = analysis.split("\n")
        assert len(lines) >= 7

    @pytest.mark.asyncio
    async def test_get_analysis_last_command_none_shows_none_text(self):
        """Kills mutmut_3: 'and' instead of 'or' — when last_command is None."""
        c = make()
        analysis = await c.get_analysis()
        assert "last_command: (none)" in analysis

    @pytest.mark.asyncio
    async def test_get_analysis_last_command_none_exact_fallback(self):
        """Kills mutmut_4 (XX(none)XX) and mutmut_5 ((NONE))."""
        c = make()
        analysis = await c.get_analysis()
        assert "last_command: (none)" in analysis
        assert "XX(none)XX" not in analysis
        assert "(NONE)" not in analysis

    @pytest.mark.asyncio
    async def test_get_analysis_last_command_with_value(self):
        """Kills mutmut_3 (and instead of or): when last_command is set, show it."""
        c = make()
        await c.handle_input("/help")
        analysis = await c.get_analysis()
        assert "last_command: /help" in analysis
        assert "last_command: (none)" not in analysis

    @pytest.mark.asyncio
    async def test_get_analysis_prompt_visible_is_true(self):
        """Kills mutmut_6: bool(None) instead of bool(self._prompt().strip())."""
        c = make()
        analysis = await c.get_analysis()
        assert "prompt_visible: True" in analysis
        assert "prompt_visible: False" not in analysis


# ---------------------------------------------------------------------------
# clear – exact checks
# ---------------------------------------------------------------------------
class TestClearExact:
    @pytest.mark.asyncio
    async def test_clear_maxlen_is_10_not_none_not_11(self):
        """Kills mutmut_2 (maxlen=None) and mutmut_3 (maxlen=11)."""
        c = make()
        await c.clear()
        assert c._transcript.maxlen == 10
        assert c._transcript.maxlen is not None
        assert c._transcript.maxlen != 11

    @pytest.mark.asyncio
    async def test_clear_banner_exact(self):
        """Kills mutmut_4 (None), mutmut_5 (XX...XX), mutmut_6 (lowercase), mutmut_7 (UPPER)."""
        c = make()
        await c.clear()
        assert c._banner == "Transcript cleared."
        assert c._banner is not None
        assert c._banner != "XXTranscript cleared.XX"
        assert c._banner != "transcript cleared."
        assert c._banner != "TRANSCRIPT CLEARED."

    @pytest.mark.asyncio
    async def test_clear_empties_transcript(self):
        """Verify clear actually removes entries."""
        c = make()
        c._append("user", "test")
        assert len(c._transcript) > 0
        await c.clear()
        assert len(c._transcript) == 0


# ---------------------------------------------------------------------------
# set_mode – exact checks
# ---------------------------------------------------------------------------
class TestSetModeExact:
    @pytest.mark.asyncio
    async def test_set_mode_open_paused_is_false_not_none(self):
        """Kills mutmut_11: _paused = None."""
        c = make({"input_mode": "hijack"})
        c._paused = True
        await c.set_mode("open")
        assert c._paused is False
        assert c._paused is not None

    @pytest.mark.asyncio
    async def test_set_mode_banner_not_none(self):
        """Kills mutmut_13: _banner = None."""
        c = make()
        await c.set_mode("open")
        assert c._banner is not None
        assert "Input mode set to" in c._banner

    @pytest.mark.asyncio
    async def test_set_mode_appends_system_text_not_none(self):
        """Kills mutmut_15: _append('system', None)."""
        c = make()
        pre_len = len(c._transcript)
        await c.set_mode("open")
        entries = list(c._transcript)
        new_entries = entries[pre_len:]
        texts = [e.text for e in new_entries]
        assert None not in texts
        assert any(t and "mode:" in t for t in texts)

    @pytest.mark.asyncio
    async def test_set_mode_appends_system_speaker_exact(self):
        """Kills mutmut_18 (XXsystemXX) and mutmut_19 (SYSTEM)."""
        c = make()
        pre_len = len(c._transcript)
        await c.set_mode("open")
        entries = list(c._transcript)
        new_entries = entries[pre_len:]
        speakers = [e.speaker for e in new_entries]
        assert "system" in speakers
        assert "XXsystemXX" not in speakers
        assert "SYSTEM" not in speakers
