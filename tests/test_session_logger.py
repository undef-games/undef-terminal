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
