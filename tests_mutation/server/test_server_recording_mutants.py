#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Mutation-killing tests for server/registry.py — SessionRegistry recording_meta/recording_entries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from undef.terminal.server.models import RecordingConfig, SessionDefinition
from undef.terminal.server.registry import SessionRegistry

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_session(
    session_id: str = "test-session",
    connector_type: str = "shell",
    auto_start: bool = False,
    ephemeral: bool = False,
    owner: str | None = None,
    input_mode: str = "open",
    visibility: str = "public",
) -> SessionDefinition:
    return SessionDefinition(
        session_id=session_id,
        display_name="Test Session",
        connector_type=connector_type,
        auto_start=auto_start,
        ephemeral=ephemeral,
        owner=owner,
        input_mode=input_mode,  # type: ignore[arg-type]
        visibility=visibility,  # type: ignore[arg-type]
    )


def _make_hub() -> MagicMock:
    hub = MagicMock()
    hub.force_release_hijack = AsyncMock(return_value=True)
    hub.get_last_snapshot = AsyncMock(return_value=None)
    hub.get_recent_events = AsyncMock(return_value=[])
    hub.browser_count = AsyncMock(return_value=0)
    hub.on_worker_empty = None
    return hub


def _make_registry(
    sessions: list[SessionDefinition] | None = None,
    *,
    hub: MagicMock | None = None,
    recording: RecordingConfig | None = None,
    max_sessions: int | None = None,
) -> SessionRegistry:
    h = hub or _make_hub()
    return SessionRegistry(
        sessions or [],
        hub=h,
        public_base_url="http://localhost:9999",
        recording=recording or RecordingConfig(),
        max_sessions=max_sessions,
    )


# ===========================================================================
# registry.py — SessionRegistry.recording_meta()
# ===========================================================================


class TestRecordingMeta:
    async def test_recording_meta_has_session_id_key(self, tmp_path: Path) -> None:
        """mutmut_6/7: key changed to XXsession_idXX or SESSION_ID."""
        reg = _make_registry([_make_session("s1")])
        meta = await reg.recording_meta("s1")
        assert "session_id" in meta
        assert meta["session_id"] == "s1"

    async def test_recording_meta_has_path_key(self, tmp_path: Path) -> None:
        """mutmut_10/11: key changed to XXpathXX or PATH."""
        reg = _make_registry([_make_session("s1")])
        meta = await reg.recording_meta("s1")
        assert "path" in meta

    async def test_recording_meta_has_exists_key(self) -> None:
        """mutmut_14/15: key changed to XXexistsXX or EXISTS."""
        reg = _make_registry([_make_session("s1")])
        meta = await reg.recording_meta("s1")
        assert "exists" in meta

    async def test_recording_meta_path_is_none_when_not_recording(self) -> None:
        """mutmut_5: path = None hardcoded."""
        reg = _make_registry([_make_session("s1")])
        meta = await reg.recording_meta("s1")
        assert meta["path"] is None  # no recording active

    async def test_recording_meta_path_is_string_when_set(self, tmp_path: Path) -> None:
        """mutmut_12: str(None) instead of str(path)."""
        recording = RecordingConfig(directory=tmp_path, enabled_by_default=False)
        reg = _make_registry([_make_session("s1")], recording=recording)
        rt = reg._runtime_for(reg._sessions["s1"])
        rt._recording_path = tmp_path / "s1.jsonl"
        meta = await reg.recording_meta("s1")
        assert meta["path"] == str(tmp_path / "s1.jsonl")

    async def test_recording_meta_path_none_when_path_is_none(self) -> None:
        """mutmut_13: condition inverted (path is None => shows str instead of None)."""
        reg = _make_registry([_make_session("s1")])
        meta = await reg.recording_meta("s1")
        assert meta["path"] is None

    async def test_recording_meta_exists_false_when_no_path(self) -> None:
        """mutmut_16: bool(None) instead of bool(path and path.exists())."""
        reg = _make_registry([_make_session("s1")])
        meta = await reg.recording_meta("s1")
        assert meta["exists"] is False

    async def test_recording_meta_exists_false_when_file_missing(self, tmp_path: Path) -> None:
        recording = RecordingConfig(directory=tmp_path, enabled_by_default=False)
        reg = _make_registry([_make_session("s1")], recording=recording)
        rt = reg._runtime_for(reg._sessions["s1"])
        rt._recording_path = tmp_path / "nonexistent.jsonl"
        meta = await reg.recording_meta("s1")
        assert meta["exists"] is False

    async def test_recording_meta_exists_true_when_file_exists(self, tmp_path: Path) -> None:
        path = tmp_path / "s1.jsonl"
        path.write_text("")
        recording = RecordingConfig(directory=tmp_path, enabled_by_default=False)
        reg = _make_registry([_make_session("s1")], recording=recording)
        rt = reg._runtime_for(reg._sessions["s1"])
        rt._recording_path = path
        meta = await reg.recording_meta("s1")
        assert meta["exists"] is True


# ===========================================================================
# registry.py — SessionRegistry.recording_entries()
# ===========================================================================


def _write_jsonl(path: Path, entries: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


class TestRecordingEntries:
    async def test_default_limit_is_200(self, tmp_path: Path) -> None:
        """mutmut_1: default limit=201 instead of 200."""
        reg = _make_registry([_make_session("s1")])
        rt = reg._runtime_for(reg._sessions["s1"])
        path = tmp_path / "s1.jsonl"
        entries = [{"event": "screen", "i": i} for i in range(250)]
        _write_jsonl(path, entries)
        rt._recording_path = path

        # Call with no explicit limit
        result = await reg.recording_entries("s1")
        # With default limit=200, should get at most 200 entries (tail)
        assert len(result) <= 200

    async def test_max_limit_capped_at_500(self, tmp_path: Path) -> None:
        """mutmut_17: max capped at 501 instead of 500."""
        reg = _make_registry([_make_session("s1")])
        rt = reg._runtime_for(reg._sessions["s1"])
        path = tmp_path / "s1.jsonl"
        entries = [{"event": "screen", "i": i} for i in range(600)]
        _write_jsonl(path, entries)
        rt._recording_path = path

        result = await reg.recording_entries("s1", limit=999)
        # With max cap at 500, must not exceed 500
        assert len(result) <= 500

    async def test_file_opened_with_utf8_encoding_offset(self, tmp_path: Path) -> None:
        """mutmut_31: encoding=None breaks non-ASCII files in _read_with_offset."""
        reg = _make_registry([_make_session("s1")])
        rt = reg._runtime_for(reg._sessions["s1"])
        path = tmp_path / "s1.jsonl"
        entries = [{"event": "screen", "text": "héllo"}, {"event": "screen", "text": "wörld"}]
        path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
        rt._recording_path = path

        result = await reg.recording_entries("s1", offset=0)
        assert len(result) == 2
        assert result[0]["text"] == "héllo"

    async def test_file_opened_with_utf8_encoding_tail(self, tmp_path: Path) -> None:
        """mutmut_60: encoding=None breaks non-ASCII in _read_tail."""
        reg = _make_registry([_make_session("s1")])
        rt = reg._runtime_for(reg._sessions["s1"])
        path = tmp_path / "s1.jsonl"
        entries = [{"event": "screen", "text": "héllo"}, {"event": "screen", "text": "wörld"}]
        path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
        rt._recording_path = path

        result = await reg.recording_entries("s1")
        assert len(result) == 2

    async def test_event_filter_uses_event_key(self, tmp_path: Path) -> None:
        """mutmut_42/44/47: entry.get('event', ...) default mutated in _read_with_offset."""
        reg = _make_registry([_make_session("s1")])
        rt = reg._runtime_for(reg._sessions["s1"])
        path = tmp_path / "s1.jsonl"
        entries = [
            {"event": "screen", "i": 0},
            {"event": "send", "i": 1},
            {"event": "screen", "i": 2},
        ]
        _write_jsonl(path, entries)
        rt._recording_path = path

        result = await reg.recording_entries("s1", offset=0, event="screen")
        assert len(result) == 2
        assert all(e["event"] == "screen" for e in result)

    async def test_event_filter_tail_uses_event_key(self, tmp_path: Path) -> None:
        """mutmut_71/73/76: entry.get('event', ...) default mutated in _read_tail."""
        reg = _make_registry([_make_session("s1")])
        rt = reg._runtime_for(reg._sessions["s1"])
        path = tmp_path / "s1.jsonl"
        entries = [
            {"event": "screen", "i": 0},
            {"event": "send", "i": 1},
            {"event": "screen", "i": 2},
        ]
        _write_jsonl(path, entries)
        rt._recording_path = path

        result = await reg.recording_entries("s1", event="screen")
        assert len(result) == 2
        assert all(e["event"] == "screen" for e in result)

    async def test_encoding_must_be_utf8_not_uppercase(self, tmp_path: Path) -> None:
        """mutmut_33/62: encoding='UTF-8' — Python accepts this, so these are equivalent.
        Instead verify the data round-trips correctly (content test)."""
        reg = _make_registry([_make_session("s1")])
        rt = reg._runtime_for(reg._sessions["s1"])
        path = tmp_path / "s1.jsonl"
        entries = [{"event": "screen", "data": "αβγ"}]
        path.write_text(json.dumps(entries[0]) + "\n", encoding="utf-8")
        rt._recording_path = path

        result = await reg.recording_entries("s1")
        assert result[0]["data"] == "αβγ"


# ===========================================================================
# auth.py — extract_bearer_token()
# ===========================================================================
