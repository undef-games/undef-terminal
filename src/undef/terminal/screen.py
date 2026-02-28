#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Generic screen parsing utilities for BBS terminals.

Provides reusable screen parsing functions that can be used across different
games and BBS systems.
"""

from __future__ import annotations

import re

_ANSI_ESCAPE_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|[@-_])")
# Some TWGS/telnet bursts occasionally leak bare SGR fragments like `1;31m` at line
# starts without the ESC prefix. Strip only when they look isolated.
_BARE_SGR_RE = re.compile(r"(?:(?<=^)|(?<=\n)|(?<=\r)|(?<=\s))(?:\d{1,3}(?:;\d{1,3})*)m(?=\x1b|\s|$)")
_BARE_SGR_LINE_PREFIX_RE = re.compile(r"(?m)^(?:\d{1,3}(?:;\d{1,3})*)m(?=[A-Z<])")


def normalize_terminal_text(text: str) -> str:
    """Normalize terminal text for robust prompt/context parsing.

    - Removes ANSI escape/control sequences.
    - Removes isolated bare SGR fragments (e.g. ``1;31m``) seen in some TWGS output.
    - Normalizes line endings.
    """
    if not text:
        return ""
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _ANSI_ESCAPE_RE.sub("", cleaned)
    cleaned = _BARE_SGR_LINE_PREFIX_RE.sub("", cleaned)
    cleaned = _BARE_SGR_RE.sub("", cleaned)
    return cleaned  # noqa: RET504


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text.

    Args:
        text: Text potentially containing ANSI escape codes.

    Returns:
        Text with all ANSI escape codes removed.
    """
    return normalize_terminal_text(text)


def decode_cp437(data: bytes) -> str:
    """Decode bytes from CP437 (DOS OEM) encoding to a Unicode string.

    CP437 is the character encoding used by most BBS systems and DOS-era
    software. It maps bytes 0x80–0xFF to box-drawing and special characters.

    Args:
        data: Raw bytes in CP437 encoding.

    Returns:
        Unicode string.
    """
    return data.decode("cp437")


def encode_cp437(text: str) -> bytes:
    """Encode a Unicode string to CP437 (DOS OEM) bytes.

    Characters that have no CP437 representation are replaced with ``?``.

    Args:
        text: Unicode string to encode.

    Returns:
        Bytes in CP437 encoding.
    """
    return text.encode("cp437", errors="replace")
