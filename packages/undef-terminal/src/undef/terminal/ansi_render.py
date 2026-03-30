#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""ANSI rendering — re-exports from undef.terminal.render.buffer.

This module is kept for backwards compatibility. New code should import
directly from ``undef.terminal.render``.
"""

from __future__ import annotations

# Re-export everything from the render package for backwards compat
from undef.terminal.render.buffer import (  # noqa: F401
    ANSI_ALT_SCREEN,
    ANSI_EXIT_ALT,
    ANSI_HIDE_CURSOR,
    ANSI_RESET,
    ANSI_SHOW_CURSOR,
    BG_CODES,
    FG_CODES,
    AnsiBuffer,
    _attr_codes,
    _color_sgr,
    _hex_to_rgb,
    _is_hex_color,
    clear_screen,
    move_to,
    style_to_sgr,
)
from undef.terminal.render.palette import (  # noqa: F401
    ANSI16_PALETTE,
    nearest_16,
    nearest_256,
)
from undef.terminal.render.sgr import (  # noqa: F401
    SGR_FUNCTIONS,
    ColorMode,
    sgr_16,
    sgr_256,
    sgr_truecolor,
)
