#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""undef-terminal: shared terminal I/O primitives for the undef ecosystem."""

from __future__ import annotations

__version__ = "0.1.0"

from undef.terminal.ansi import (
    BOLD,
    CLEAR_SCREEN,
    COLOR_MAP,
    DEFAULT_PALETTE,
    DEFAULT_RGB,
    RESET,
    colorize,
    preview_ansi,
    strip_colors,
    upgrade_to_256,
    upgrade_to_truecolor,
)
from undef.terminal.file_io import load_ans, load_palette, load_txt
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
    "DEFAULT_PALETTE",
    "DEFAULT_RGB",
    "colorize",
    "strip_colors",
    "preview_ansi",
    "upgrade_to_256",
    "upgrade_to_truecolor",
    # file_io
    "load_ans",
    "load_txt",
    "load_palette",
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
    # fastapi (optional — requires [websocket] extra)
    "mount_terminal_ui",
]


def __getattr__(name: str) -> object:
    if name == "mount_terminal_ui":
        from undef.terminal.fastapi import mount_terminal_ui  # noqa: PLC0415

        return mount_terminal_ui
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
