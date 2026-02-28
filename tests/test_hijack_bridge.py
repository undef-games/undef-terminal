#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Tests for TermBridge (worker-side WS client)."""

from __future__ import annotations

import asyncio
import contextlib
import json
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


# ---------------------------------------------------------------------------
# Mock WebSocket for _recv_loop / _send_loop / _send_snapshot tests
# ---------------------------------------------------------------------------


class MockWS:
    """Minimal async WebSocket mock for TermBridge internal loop tests."""

    def __init__(self, messages: list[str] | None = None) -> None:
        self.sent: list[str] = []
        self._messages = list(messages or [])
        self._idx = 0

    async def recv(self) -> str:
        if self._idx >= len(self._messages):
            raise Exception("WebSocket closed")
        msg = self._messages[self._idx]
        self._idx += 1
        return msg

    async def send(self, data: str) -> None:
        self.sent.append(data)


# ---------------------------------------------------------------------------
# attach_session — _watch callback
# ---------------------------------------------------------------------------


class TestAttachSessionWatch:
    def test_watch_queues_term_data(self) -> None:
        session = MockSession()
        bot = MockBot(session)
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        bridge.attach_session()

        watch_fn = session._watches[0]
        raw = b"Hello from TW2002"
        watch_fn({"screen": "test"}, raw)

        assert not bridge._send_q.empty()
        msg = bridge._send_q.get_nowait()
        assert msg["type"] == "term"
        assert "Hello from TW2002" in msg["data"]

    def test_watch_noop_empty_raw(self) -> None:
        session = MockSession()
        bot = MockBot(session)
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        bridge.attach_session()

        watch_fn = session._watches[0]
        watch_fn({"screen": "test"}, b"")  # empty raw → no queue entry

        assert bridge._send_q.empty()

    def test_watch_updates_latest_snapshot(self) -> None:
        session = MockSession()
        bot = MockBot(session)
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        bridge.attach_session()

        snapshot = {"screen": "sector 1", "cols": 80, "rows": 25}
        session._watches[0](snapshot, b"some data")

        assert bridge._latest_snapshot == snapshot


# ---------------------------------------------------------------------------
# start()
# ---------------------------------------------------------------------------


class TestStart:
    async def test_start_creates_running_task(self) -> None:
        bot = MockBot()
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        await bridge.start()
        assert bridge._running is True
        assert bridge._task is not None
        # Clean up
        await bridge.stop()

    async def test_start_idempotent(self) -> None:
        bot = MockBot()
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        await bridge.start()
        task1 = bridge._task
        await bridge.start()  # second call — should not create a new task
        assert bridge._task is task1
        await bridge.stop()


# ---------------------------------------------------------------------------
# _send_loop
# ---------------------------------------------------------------------------


class TestSendLoop:
    async def test_send_loop_sends_queued_message(self) -> None:
        bot = MockBot()
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        bridge._running = True

        ws = MockWS()
        # Override send to stop the loop after the first send
        original_send = ws.send

        async def _send_and_stop(data: str) -> None:
            await original_send(data)
            bridge._running = False

        ws.send = _send_and_stop  # type: ignore[method-assign]

        await bridge._send_q.put({"type": "status", "hijacked": False, "ts": 0.0})
        await bridge._send_loop(ws)

        assert len(ws.sent) == 1
        payload = json.loads(ws.sent[0])
        assert payload["type"] == "status"

    async def test_send_loop_exits_when_not_running(self) -> None:
        bot = MockBot()
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        bridge._running = False  # already stopped

        ws = MockWS()
        # Loop should exit immediately without blocking
        task = asyncio.create_task(bridge._send_loop(ws))
        await asyncio.sleep(0)
        # Queue is empty; loop condition is False so the task should complete quickly
        # Cancel it in case it blocked on get()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert len(ws.sent) == 0


# ---------------------------------------------------------------------------
# _recv_loop
# ---------------------------------------------------------------------------


class TestRecvLoop:
    async def test_recv_loop_snapshot_req_calls_send_snapshot(self) -> None:
        session = MockSession()
        bot = MockBot(session)
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        bridge._running = True

        ws = MockWS([json.dumps({"type": "snapshot_req"})])
        await bridge._recv_loop(ws)

        # _send_snapshot should have sent a snapshot via ws.send
        assert len(ws.sent) == 1
        payload = json.loads(ws.sent[0])
        assert payload["type"] == "snapshot"

    async def test_recv_loop_control_pause(self) -> None:
        bot = MockBot()
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        bridge._running = True

        ws = MockWS([json.dumps({"type": "control", "action": "pause"})])
        await bridge._recv_loop(ws)

        assert bot.hijacked_calls == [True]

    async def test_recv_loop_control_resume(self) -> None:
        bot = MockBot()
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        bridge._running = True

        ws = MockWS([json.dumps({"type": "control", "action": "resume"})])
        await bridge._recv_loop(ws)

        assert bot.hijacked_calls == [False]

    async def test_recv_loop_control_step(self) -> None:
        bot = MockBot()
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        bridge._running = True

        ws = MockWS([json.dumps({"type": "control", "action": "step"})])
        await bridge._recv_loop(ws)

        assert bot.step_calls == 1

    async def test_recv_loop_input(self) -> None:
        session = MockSession()
        bot = MockBot(session)
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        bridge._running = True

        ws = MockWS([json.dumps({"type": "input", "data": "hello\\r"})])
        await bridge._recv_loop(ws)

        assert session.sent == ["hello\r"]

    async def test_recv_loop_resize(self) -> None:
        session = MockSession()
        bot = MockBot(session)
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        bridge._running = True

        ws = MockWS([json.dumps({"type": "resize", "cols": 132, "rows": 50})])
        await bridge._recv_loop(ws)

        assert session.sizes == [(132, 50)]

    async def test_recv_loop_recv_error_exits(self) -> None:
        bot = MockBot()
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        bridge._running = True

        ws = MockWS()  # no messages → recv raises immediately
        await bridge._recv_loop(ws)  # should return cleanly

    async def test_recv_loop_invalid_json_continues(self) -> None:
        bot = MockBot()
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        bridge._running = True

        # First message is invalid JSON; second is valid control/step
        ws = MockWS(["not json {{", json.dumps({"type": "control", "action": "step"})])
        await bridge._recv_loop(ws)

        assert bot.step_calls == 1

    async def test_recv_loop_multiple_messages(self) -> None:
        bot = MockBot()
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        bridge._running = True

        ws = MockWS(
            [
                json.dumps({"type": "control", "action": "pause"}),
                json.dumps({"type": "control", "action": "resume"}),
                json.dumps({"type": "control", "action": "step"}),
            ]
        )
        await bridge._recv_loop(ws)

        assert bot.hijacked_calls == [True, False]
        assert bot.step_calls == 1


# ---------------------------------------------------------------------------
# _send_snapshot
# ---------------------------------------------------------------------------


class TestSendSnapshot:
    async def test_send_snapshot_uses_emulator(self) -> None:
        session = MockSession()
        bot = MockBot(session)
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")

        ws = MockWS()
        await bridge._send_snapshot(ws)

        assert len(ws.sent) == 1
        payload = json.loads(ws.sent[0])
        assert payload["type"] == "snapshot"
        assert payload["screen"] == "test"

    async def test_send_snapshot_no_session_noop(self) -> None:
        bot = MockBot(session=None)
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")

        ws = MockWS()
        await bridge._send_snapshot(ws)

        assert len(ws.sent) == 0

    async def test_send_snapshot_uses_latest_snapshot(self) -> None:
        session = MockSession()
        bot = MockBot(session)
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        bridge._latest_snapshot = {"screen": "cached screen", "cols": 80, "rows": 25}

        ws = MockWS()
        await bridge._send_snapshot(ws)

        payload = json.loads(ws.sent[0])
        assert payload["screen"] == "cached screen"


# ---------------------------------------------------------------------------
# _send_keys / _set_size / _set_hijacked — missing early-return branches
# ---------------------------------------------------------------------------


class TestHelperEdgeCases:
    async def test_send_keys_no_session_noop(self) -> None:
        bot = MockBot(session=None)
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        # Should not raise
        await bridge._send_keys("hello")

    async def test_set_size_no_session_noop(self) -> None:
        bot = MockBot(session=None)
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        await bridge._set_size(80, 25)  # should not raise

    async def test_set_hijacked_queues_status_message(self) -> None:
        bot = MockBot()
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        await bridge._set_hijacked(True)

        assert not bridge._send_q.empty()
        msg = bridge._send_q.get_nowait()
        assert msg["type"] == "status"
        assert msg["hijacked"] is True

    async def test_set_hijacked_false_queues_status(self) -> None:
        bot = MockBot()
        bridge = TermBridge(bot, "bot1", "http://localhost:8000")
        await bridge._set_hijacked(False)

        msg = bridge._send_q.get_nowait()
        assert msg["hijacked"] is False


class TestRunLoop:
    async def test_run_connects_to_ws_server(self) -> None:
        """_run opens a WebSocket to the manager URL and pumps messages."""
        import websockets.server as _ws_srv

        received_from_bridge: list[dict] = []

        async def _ws_handler(websocket) -> None:
            try:
                while True:
                    msg = await websocket.recv()
                    received_from_bridge.append(json.loads(msg))
                    if len(received_from_bridge) >= 1:
                        break
            except Exception:
                pass

        async with _ws_srv.serve(_ws_handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]

            class _FakeBot:
                session = None

                async def set_hijacked(self, enabled: bool) -> None:
                    pass

                async def request_step(self) -> None:
                    pass

            bot = _FakeBot()
            bridge = TermBridge(bot, "bot1", f"http://127.0.0.1:{port}")
            bridge._send_q.put_nowait({"type": "term", "data": "hello", "ts": 0.0})
            await bridge.start()
            await asyncio.sleep(0.2)
            await bridge.stop()

        assert len(received_from_bridge) >= 1

    async def test_send_snapshot_exception_suppressed(self) -> None:
        """_send_snapshot catches exceptions from ws.send() silently."""
        class _FakeSession:
            emulator = None

        class _FakeBot:
            session = _FakeSession()

        bot = _FakeBot()
        bridge = TermBridge(bot, "bot1", "http://localhost")

        class _BrokenWs:
            async def send(self, data: object) -> None:
                raise RuntimeError("broken")

        # Should not raise
        await bridge._send_snapshot(_BrokenWs())
