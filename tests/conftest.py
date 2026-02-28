#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Shared pytest fixtures for undef-terminal tests."""

from __future__ import annotations

import asyncio
import socket

import pytest


@pytest.fixture()
def free_port() -> int:
    """Return a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def event_loop():
    """Provide a new event loop for each test."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
