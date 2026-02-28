#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Tests for TermBridge (worker-side WS client)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

from undef.terminal.hijack.bridge import TermBridge, _to_ws_url


class TestToWsUrl:
    def test_http_to_ws(self) -> None:
        assert _to_ws_url("http://localhost:8000", "/ws/worker/bot1/term") == "ws://localhost:8000/ws/worker/bot1/term"

    def test_https_to_wss(self) -> None:
        assert _to_ws_url("https://manager.example.com", "/path") == "wss://manager.example.com/path"

    def test_trailing_slash_stripped(self) -> None:
        result = _to_ws_url("http://host:8000/", "/path")
        assert result == "ws://host:8000/path"


class MockSession:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.sizes: list[tuple[int, int]] = []
        self._watches: list[Any] = []
        self.emulator = MagicMock()
        self.emulator.get_snapshot.return_value = {"screen": "test", "cols": 80, "rows": 25}

    def add_watch(self, fn: Any, *, interval_s: float) -> None:
        self._watches.append(fn)

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def set_size(self, cols: int, rows: int) -> None:
        self.sizes.append((cols, rows))


class MockBot:
    def __init__(self, session: MockSession | None = None) -> None:
        self.session = session
        self.hijacked_calls: list[bool] = []
        self.step_calls: int = 0

    async def set_hijacked(self, enabled: bool) -> None:
        self.hijacked_calls.append(enabled)

    async def request_step(self) -> None:
        self.step_calls += 1


class TestTermBridgeAttachSession:
    def test_attach_registers_watch(self) -> None:
        session = MockSession()
        bot = MockBot(session)
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        bridge.attach_session()
        assert len(session._watches) == 1

    def test_attach_idempotent(self) -> None:
        session = MockSession()
        bot = MockBot(session)
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        bridge.attach_session()
        bridge.attach_session()
        assert len(session._watches) == 1

    def test_attach_noop_when_no_session(self) -> None:
        bot = MockBot(session=None)
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        bridge.attach_session()  # should not raise


class TestTermBridgeHelpers:
    async def test_send_keys_decodes_escapes(self) -> None:
        session = MockSession()
        bot = MockBot(session)
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        await bridge._send_keys("hello\\r")
        assert session.sent == ["hello\r"]

    async def test_set_hijacked_calls_bot(self) -> None:
        bot = MockBot()
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        await bridge._set_hijacked(True)
        assert bot.hijacked_calls == [True]

    async def test_request_step_calls_bot(self) -> None:
        bot = MockBot()
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        await bridge._request_step()
        assert bot.step_calls == 1

    async def test_set_size_calls_session(self) -> None:
        session = MockSession()
        bot = MockBot(session)
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        await bridge._set_size(132, 50)
        assert session.sizes == [(132, 50)]

    async def test_stop_cancels_task(self) -> None:
        bot = MockBot()
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        bridge._running = True
        # Start a dummy task that just sleeps
        bridge._task = asyncio.create_task(asyncio.sleep(100))
        await bridge.stop()
        assert bridge._task.done()
