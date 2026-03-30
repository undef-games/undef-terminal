#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Tests for undef.terminal.ansi_render module."""

from __future__ import annotations

from undef.terminal.ansi_render import (
    ANSI_RESET,
    BG_CODES,
    FG_CODES,
    AnsiBuffer,
    clear_screen,
    move_to,
    style_to_sgr,
)


class TestAnsiBuffer:
    """AnsiBuffer construction, feed, and render."""

    def test_construction(self) -> None:
        buf = AnsiBuffer(80, 25)
        assert buf._screen.columns == 80
        assert buf._screen.lines == 25

    def test_feed_empty_data(self) -> None:
        buf = AnsiBuffer(80, 25)
        buf.feed(b"")  # should not raise

    def test_feed_and_render_plain_text(self) -> None:
        buf = AnsiBuffer(40, 5)
        buf.feed(b"Hello")
        lines = buf.render_lines(40, 5)
        assert len(lines) == 5
        # First line should contain "Hello" somewhere
        assert "Hello" in lines[0]

    def test_render_lines_contain_ansi_codes(self) -> None:
        buf = AnsiBuffer(40, 5)
        # Feed bold red text via ANSI escape
        buf.feed(b"\x1b[1;31mRED\x1b[0m")
        lines = buf.render_lines(40, 5)
        first_line = lines[0]
        # Should contain SGR sequence for bold (1) + red fg (31)
        assert "\x1b[1;31m" in first_line
        assert "RED" in first_line

    def test_resize(self) -> None:
        buf = AnsiBuffer(80, 25)
        buf.resize(120, 40)
        # pyte.Screen.resize takes (lines, columns) internally;
        # AnsiBuffer.resize passes (cols, rows) so cols→columns, rows→lines
        assert buf._screen.columns == 120
        assert buf._screen.lines == 40

    def test_reset(self) -> None:
        buf = AnsiBuffer(40, 5)
        buf.feed(b"Some text")
        buf.reset()
        lines = buf.render_lines(40, 5)
        # After reset all lines should be blank (spaces + reset)
        for line in lines:
            stripped = line.replace(ANSI_RESET, "").replace("\x1b[0m", "").strip()
            assert stripped == ""


class TestStyleToSgr:
    """style_to_sgr for various attribute combinations."""

    def test_default_returns_reset(self) -> None:
        result = style_to_sgr("default", "default", False, False, False, False)
        assert result == ANSI_RESET

    def test_bold(self) -> None:
        result = style_to_sgr("default", "default", True, False, False, False)
        assert result == "\x1b[1m"

    def test_fg_color(self) -> None:
        result = style_to_sgr("green", "default", False, False, False, False)
        assert result == f"\x1b[{FG_CODES['green']}m"

    def test_bg_color(self) -> None:
        result = style_to_sgr("default", "blue", False, False, False, False)
        assert result == f"\x1b[{BG_CODES['blue']}m"

    def test_bold_and_color(self) -> None:
        result = style_to_sgr("red", "default", True, False, False, False)
        assert result == f"\x1b[1;{FG_CODES['red']}m"

    def test_reverse_swaps_fg_bg(self) -> None:
        # reverse=True should swap fg and bg before lookup
        result = style_to_sgr("red", "blue", False, False, True, False)
        # After swap: fg=blue, bg=red
        assert f"{FG_CODES['blue']}" in result
        assert f"{BG_CODES['red']}" in result

    def test_underscore(self) -> None:
        result = style_to_sgr("default", "default", False, True, False, False)
        assert result == "\x1b[4m"

    def test_blink(self) -> None:
        result = style_to_sgr("default", "default", False, False, False, True)
        assert result == "\x1b[5m"


class TestEscapeHelpers:
    """move_to and clear_screen return correct escape sequences."""

    def test_move_to(self) -> None:
        assert move_to(1, 1) == "\x1b[1;1H"
        assert move_to(10, 20) == "\x1b[10;20H"

    def test_clear_screen(self) -> None:
        assert clear_screen() == "\x1b[2J"
