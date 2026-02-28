#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""ANSI color code conversion for TW2002 terminal output.

The C server uses {+c} for bright cyan, {-x} for reset, etc.
This module converts those tags to standard ANSI escape sequences.
"""

from __future__ import annotations

# Mapping from TW2002 color tags to ANSI escape sequences
COLOR_MAP: dict[str, str] = {
    "{+c}": "\033[1;36m",  # Bright cyan
    "{-c}": "\033[0;36m",  # Normal cyan
    "{+r}": "\033[1;31m",  # Bright red
    "{-r}": "\033[0;31m",  # Normal red
    "{+g}": "\033[1;32m",  # Bright green
    "{-g}": "\033[0;32m",  # Normal green
    "{+y}": "\033[1;33m",  # Bright yellow
    "{-y}": "\033[0;33m",  # Normal yellow
    "{+b}": "\033[1;34m",  # Bright blue
    "{-b}": "\033[0;34m",  # Normal blue
    "{+m}": "\033[1;35m",  # Bright magenta
    "{-m}": "\033[0;35m",  # Normal magenta
    "{+w}": "\033[1;37m",  # Bright white
    "{+Bw}": "\033[1;37m",  # Bold white (TWGS header style)
    "{-w}": "\033[0;37m",  # Normal white
    "{+k}": "\033[1;30m",  # Bright black (gray)
    "{-k}": "\033[0;30m",  # Normal black
    "{-x}": "\033[0m",  # Reset
}

# Common ANSI sequences
CLEAR_SCREEN: str = "\033[2J\033[H"
BOLD: str = "\033[1m"
RESET: str = "\033[0m"


def colorize(text: str) -> str:
    """Convert TW2002 color tags to ANSI escape sequences.

    Replaces all occurrences of {+X} and {-X} tags with their corresponding
    ANSI escape codes. Unknown tags are left as-is.

    Args:
        text: String containing TW2002 color tags.

    Returns:
        String with ANSI escape sequences substituted.
    """
    result = text
    for tag, ansi in COLOR_MAP.items():
        result = result.replace(tag, ansi)
    return result


def strip_colors(text: str) -> str:
    """Remove all TW2002 color tags from text.

    Useful for logging or plain-text output where ANSI codes are unwanted.

    Args:
        text: String containing TW2002 color tags.

    Returns:
        String with all color tags removed.
    """
    result = text
    for tag in COLOR_MAP:
        result = result.replace(tag, "")
    return result
