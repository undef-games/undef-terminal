#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Tests for SessionLogger."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from undef.terminal.session_logger import SessionLogger


class TestSessionLogger:
    async def test_start_stop_writes_header_and_footer(self, tmp_path: Path) -> None:
        log_path = tmp_path / "session.jsonl"
        logger = SessionLogger(log_path)
        await logger.start(session_id=1)
        await logger.stop()

        lines = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
        assert lines[0]["event"] == "log_start"
        assert lines[-1]["event"] == "log_stop"

    async def test_log_send(self, tmp_path: Path) -> None:
        log_path = tmp_path / "session.jsonl"
        logger = SessionLogger(log_path)
        await logger.start(session_id=2)
        await logger.log_send("hello")
        await logger.stop()

        lines = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
        send_records = [rec for rec in lines if rec["event"] == "send"]
        assert len(send_records) == 1
        assert send_records[0]["data"]["keys"] == "hello"

    async def test_log_send_masked(self, tmp_path: Path) -> None:
        log_path = tmp_path / "session.jsonl"
        logger = SessionLogger(log_path)
        await logger.start(session_id=3)
        await logger.log_send_masked(byte_count=8)
        await logger.stop()

        lines = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
        send_records = [rec for rec in lines if rec["event"] == "send"]
        assert send_records[0]["data"]["masked"] is True
        assert send_records[0]["data"]["keys"] == "***"

    async def test_log_screen_round_trip(self, tmp_path: Path) -> None:
        log_path = tmp_path / "session.jsonl"
        logger = SessionLogger(log_path)
        await logger.start(session_id=4)
        raw = b"raw screen bytes"
        await logger.log_screen({"screen": "text"}, raw)
        await logger.stop()

        lines = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
        read_records = [rec for rec in lines if rec["event"] == "read"]
        assert len(read_records) == 1
        decoded = base64.b64decode(read_records[0]["data"]["raw_bytes_b64"])
        assert decoded == raw

    async def test_log_event(self, tmp_path: Path) -> None:
        log_path = tmp_path / "session.jsonl"
        logger = SessionLogger(log_path)
        await logger.start(session_id=5)
        await logger.log_event("custom", {"key": "value"})
        await logger.stop()

        lines = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
        custom = [rec for rec in lines if rec["event"] == "custom"]
        assert custom[0]["data"]["key"] == "value"

    async def test_context_included_in_records(self, tmp_path: Path) -> None:
        log_path = tmp_path / "session.jsonl"
        logger = SessionLogger(log_path)
        await logger.start(session_id=6)
        logger.set_context({"menu": "main", "action": "move"})
        await logger.log_event("nav", {})
        await logger.stop()

        lines = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
        nav = [rec for rec in lines if rec["event"] == "nav"][0]
        assert nav["menu"] == "main"
        assert nav["action"] == "move"


class TestSessionLoggerExtra:
    async def test_clear_context(self, tmp_path) -> None:
        from undef.terminal.session_logger import SessionLogger

        logger = SessionLogger(tmp_path / "test.jsonl")
        logger.set_context({"key": "val"})
        logger.clear_context()
        assert logger._context == {}

    async def test_write_event_unlocked_no_file(self, tmp_path) -> None:
        """_write_event_unlocked is a no-op when _file is None."""
        from undef.terminal.session_logger import SessionLogger

        logger = SessionLogger(tmp_path / "test.jsonl")
        # Should not raise even with no file open
        await logger._write_event("test_event", {"data": "value"})


class TestSessionLoggerFlushRegression:
    """Regression tests for fix 1: flush() called after write; close() OSError suppressed."""

    async def test_flush_called_after_every_write(self, tmp_path: Path) -> None:
        """Regression fix 1: file.flush() must be called after each write to prevent data loss on crash."""
        from unittest.mock import MagicMock

        log = SessionLogger(tmp_path / "flush_test.jsonl")
        await log.start(session_id=99)

        mock_file = MagicMock()
        log._file = mock_file

        await log.log_event("ping", {"x": 1})

        # Each write must be followed by a flush
        assert mock_file.flush.called, "flush() was not called after write()"
        write_calls = mock_file.write.call_count
        flush_calls = mock_file.flush.call_count
        assert flush_calls >= write_calls, "flush() must be called at least once per write()"

        log._file = None  # prevent stop() from closing the mock

    async def test_stop_suppresses_oserror_on_close(self, tmp_path: Path) -> None:
        """Regression fix 1: stop() must not propagate OSError from file.close()."""
        from unittest.mock import MagicMock

        log = SessionLogger(tmp_path / "close_err.jsonl")
        await log.start(session_id=100)

        mock_file = MagicMock()
        mock_file.close = MagicMock(side_effect=OSError("disk full"))
        log._file = mock_file

        # Must not raise despite OSError from close()
        await log.stop()
        assert log._file is None


class TestSessionLoggerNonBlockingFlush:
    """Regression tests for fix B: flush() must not block the asyncio event loop."""

    async def test_flush_runs_in_executor_not_inline(self, tmp_path: Path) -> None:
        """Regression fix B: file.flush() must be dispatched via run_in_executor, not called inline."""
        import asyncio
        from unittest.mock import MagicMock, patch

        log = SessionLogger(tmp_path / "exec_flush.jsonl")
        await log.start(session_id=101)

        mock_file = MagicMock()
        log._file = mock_file

        executor_calls: list[object] = []

        original_run = asyncio.get_event_loop().run_in_executor

        async def _spy_executor(executor: object, fn: object, *args: object) -> None:
            executor_calls.append(fn)
            return original_run(executor, fn, *args)

        with patch.object(asyncio.get_event_loop(), "run_in_executor", side_effect=_spy_executor):
            await log.log_event("exec_test", {})

        assert executor_calls, "flush was not dispatched via run_in_executor"
        assert mock_file.flush in executor_calls, "expected file.flush to be the executor callable"

        log._file = None

    async def test_flush_does_not_block_concurrent_coroutine(self, tmp_path: Path) -> None:
        """Regression fix B: a slow flush must not starve a concurrent coroutine.

        We simulate a slow flush with a blocking sleep inside the executor and
        verify that an independent coroutine still runs during that time.
        """
        import asyncio
        import time as _time

        log = SessionLogger(tmp_path / "concurrent_flush.jsonl")
        await log.start(session_id=102)

        ran: list[bool] = []

        async def _other_coro() -> None:
            ran.append(True)

        # Patch flush to take 50 ms in the executor (simulates a slow syscall)
        original_flush = log._file.flush  # type: ignore[union-attr]

        def _slow_flush() -> None:
            _time.sleep(0.05)
            original_flush()

        log._file.flush = _slow_flush  # type: ignore[union-attr]

        # Run the slow write and the independent coroutine concurrently
        await asyncio.gather(
            log.log_event("slow", {}),
            _other_coro(),
        )

        assert ran, "concurrent coroutine was starved — flush is blocking the event loop"
        await log.stop()
