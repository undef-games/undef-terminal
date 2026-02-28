#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Tests for PromptWaiter and InputSender."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from undef.terminal.io import InputSender, PromptWaiter


class MockSession:
    """Minimal session stub for I/O tests."""

    def __init__(
        self,
        snapshots: list[dict[str, Any]] | None = None,
        connected: bool = True,
    ) -> None:
        self._snapshots = snapshots or [{}]
        self._snap_index = 0
        self._connected = connected
        self.sent: list[str] = []

    async def wait_for_update(self, *, timeout_ms: int, since: int | None = None) -> bool:
        await asyncio.sleep(0)
        return True

    def snapshot(self) -> dict[str, Any]:
        if self._snap_index < len(self._snapshots):
            snap = self._snapshots[self._snap_index]
            self._snap_index += 1
            return snap
        return self._snapshots[-1]

    async def send(self, data: str) -> None:
        self.sent.append(data)

    def is_connected(self) -> bool:
        return self._connected


class TestPromptWaiter:
    async def test_returns_when_prompt_detected(self) -> None:
        snap = {
            "screen": "Enter command:",
            "prompt_detected": {"prompt_id": "cmd.prompt", "input_type": "multi_key", "is_idle": True},
        }
        session = MockSession(snapshots=[snap])
        waiter = PromptWaiter(session)
        result = await waiter.wait_for_prompt(timeout_ms=500)
        assert result["prompt_id"] == "cmd.prompt"
        assert result["screen"] == "Enter command:"

    async def test_timeout_raises(self) -> None:
        session = MockSession(snapshots=[{"screen": "nothing"}])
        waiter = PromptWaiter(session)
        with pytest.raises(TimeoutError):
            await waiter.wait_for_prompt(timeout_ms=50)

    async def test_none_session_raises(self) -> None:
        waiter = PromptWaiter(None)
        with pytest.raises(ConnectionError, match="Session is None"):
            await waiter.wait_for_prompt(timeout_ms=50)

    async def test_disconnected_session_raises(self) -> None:
        session = MockSession(connected=False)
        waiter = PromptWaiter(session)
        with pytest.raises(ConnectionError, match="disconnected"):
            await waiter.wait_for_prompt(timeout_ms=50)

    async def test_expected_prompt_id_filter(self) -> None:
        wrong = {
            "screen": "wrong screen",
            "prompt_detected": {"prompt_id": "other.prompt", "input_type": "multi_key", "is_idle": True},
        }
        right = {
            "screen": "right screen",
            "prompt_detected": {"prompt_id": "cmd.prompt", "input_type": "multi_key", "is_idle": True},
        }
        session = MockSession(snapshots=[wrong, right])
        waiter = PromptWaiter(session)
        result = await waiter.wait_for_prompt(expected_prompt_id="cmd.prompt", timeout_ms=1000)
        assert result["prompt_id"] == "cmd.prompt"


class TestInputSender:
    async def test_multi_key_appends_cr(self) -> None:
        session = MockSession()
        sender = InputSender(session)
        await sender.send_input("hello", input_type="multi_key", wait_after_sec=0)
        assert session.sent == ["hello\r"]

    async def test_single_key_no_cr(self) -> None:
        session = MockSession()
        sender = InputSender(session)
        await sender.send_input("x", input_type="single_key", wait_after_sec=0)
        assert session.sent == ["x"]

    async def test_any_key_sends_space(self) -> None:
        session = MockSession()
        sender = InputSender(session)
        await sender.send_input("ignored", input_type="any_key", wait_after_sec=0)
        assert session.sent == [" "]

    async def test_none_session_raises(self) -> None:
        sender = InputSender(None)
        with pytest.raises(ConnectionError):
            await sender.send_input("x", wait_after_sec=0)

    async def test_disconnected_raises(self) -> None:
        session = MockSession(connected=False)
        sender = InputSender(session)
        with pytest.raises(ConnectionError):
            await sender.send_input("x", wait_after_sec=0)
