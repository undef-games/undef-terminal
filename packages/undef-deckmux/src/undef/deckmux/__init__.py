#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""DeckMux — collaborative terminal presence and control transfer."""

from __future__ import annotations

from undef.deckmux._edge import viewport_to_edge_range
from undef.deckmux._names import generate_color, generate_name
from undef.deckmux._presence import PresenceStore, UserPresence
from undef.deckmux._protocol import (
    MSG_CONTROL_TRANSFER,
    MSG_PRESENCE_LEAVE,
    MSG_PRESENCE_SYNC,
    MSG_PRESENCE_UPDATE,
    MSG_QUEUED_INPUT,
)
from undef.deckmux._transfer import TransferManager

__all__ = [
    "MSG_CONTROL_TRANSFER",
    "MSG_PRESENCE_LEAVE",
    "MSG_PRESENCE_SYNC",
    "MSG_PRESENCE_UPDATE",
    "MSG_QUEUED_INPUT",
    "PresenceStore",
    "TransferManager",
    "UserPresence",
    "generate_color",
    "generate_name",
    "viewport_to_edge_range",
]
