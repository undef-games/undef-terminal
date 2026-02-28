#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""undef-terminal: shared terminal I/O primitives for the undef ecosystem."""

from __future__ import annotations

__version__ = "0.1.0"

from undef.terminal.ansi import BOLD, CLEAR_SCREEN, COLOR_MAP, RESET, colorize, strip_colors
from undef.terminal.screen import (
    clean_screen_for_display,
    decode_cp437,
    encode_cp437,
    extract_action_tags,
    extract_key_value_pairs,
    extract_menu_options,
    extract_numbered_list,
    normalize_terminal_text,
    strip_ansi,
)

__all__ = [
    "__version__",
    # ansi
    "COLOR_MAP",
    "CLEAR_SCREEN",
    "BOLD",
    "RESET",
    "colorize",
    "strip_colors",
    # screen
    "strip_ansi",
    "normalize_terminal_text",
    "decode_cp437",
    "encode_cp437",
    "extract_action_tags",
    "clean_screen_for_display",
    "extract_menu_options",
    "extract_numbered_list",
    "extract_key_value_pairs",
]
