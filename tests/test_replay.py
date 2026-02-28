#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Tests for replay utilities."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from undef.terminal.replay.raw import rebuild_raw_stream


def _make_log(tmp_path: Path, records: list[dict]) -> Path:
    log_path = tmp_path / "test.jsonl"
    with log_path.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return log_path


class TestRebuildRawStream:
    def test_combines_read_events(self, tmp_path: Path) -> None:
        chunk1 = b"Hello "
        chunk2 = b"World"
        records = [
            {"event": "read", "ts": 1.0, "data": {"raw_bytes_b64": base64.b64encode(chunk1).decode()}},
            {"event": "read", "ts": 2.0, "data": {"raw_bytes_b64": base64.b64encode(chunk2).decode()}},
        ]
        log_path = _make_log(tmp_path, records)
        out_path = tmp_path / "out.bin"
        rebuild_raw_stream(log_path, out_path)
        assert out_path.read_bytes() == b"Hello World"

    def test_skips_non_read_events(self, tmp_path: Path) -> None:
        records = [
            {"event": "send", "ts": 1.0, "data": {"keys": "x", "bytes_b64": base64.b64encode(b"x").decode()}},
            {"event": "read", "ts": 2.0, "data": {"raw_bytes_b64": base64.b64encode(b"response").decode()}},
        ]
        log_path = _make_log(tmp_path, records)
        out_path = tmp_path / "out.bin"
        rebuild_raw_stream(log_path, out_path)
        assert out_path.read_bytes() == b"response"

    def test_empty_log_produces_empty_file(self, tmp_path: Path) -> None:
        log_path = tmp_path / "empty.jsonl"
        log_path.write_text("")
        out_path = tmp_path / "out.bin"
        rebuild_raw_stream(log_path, out_path)
        assert out_path.read_bytes() == b""
