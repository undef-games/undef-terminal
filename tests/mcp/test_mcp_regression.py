#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""MCP regression tests — multi-session, cross-session isolation, escape handling.

These exercise the MCP tool layer against a real server app (ASGI transport)
to catch regressions in session lifecycle, hijack isolation, mode switching,
and key escape processing.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastmcp import FastMCP
from httpx import ASGITransport

from undef.terminal.hijack.hub import TermHub
from undef.terminal.hijack.models import WorkerTermState
from undef.terminal.mcp.server import create_mcp_app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AUTH_HEADERS = {"X-Uterm-Principal": "tester", "X-Uterm-Role": "admin"}


def _make_hub_app() -> tuple[TermHub, FastAPI]:
    hub = TermHub(resolve_browser_role=lambda _ws, _wid: "admin")
    app = FastAPI()
    app.include_router(hub.create_router())
    return hub, app


def _add_worker(hub: TermHub, worker_id: str) -> AsyncMock:
    mock_ws = AsyncMock()
    mock_ws.send_text = AsyncMock()
    hub._workers[worker_id] = WorkerTermState(worker_ws=mock_ws)
    return mock_ws


def _add_worker_with_snapshot(
    hub: TermHub,
    worker_id: str,
    screen: str,
) -> AsyncMock:
    ws = _add_worker(hub, worker_id)
    hub._workers[worker_id].last_snapshot = {
        "screen": screen,
        "cursor": {"x": 0, "y": 0},
        "cols": 80,
        "rows": 25,
        "screen_hash": f"hash-{worker_id}",
        "ts": time.time() + 100,
    }
    return ws


def _mcp_for(app: FastAPI) -> FastMCP:
    return create_mcp_app("http://test", transport=ASGITransport(app=app))


def _server_app(
    sessions: list[dict[str, Any]] | None = None,
) -> FastAPI:
    from undef.terminal.server.app import create_server_app
    from undef.terminal.server.config import config_from_mapping

    if sessions is None:
        sessions = [
            {
                "session_id": "sh-1",
                "display_name": "Shell One",
                "connector_type": "shell",
                "auto_start": False,
            },
            {
                "session_id": "sh-2",
                "display_name": "Shell Two",
                "connector_type": "shell",
                "auto_start": False,
            },
        ]
    cfg = config_from_mapping(
        {
            "server": {"host": "127.0.0.1", "port": 0},
            "auth": {"mode": "dev"},
            "sessions": sessions,
        }
    )
    return create_server_app(cfg)


def _mcp_for_server(app: FastAPI) -> FastMCP:
    return create_mcp_app(
        "http://test",
        transport=ASGITransport(app=app),
        headers=_AUTH_HEADERS,
    )


async def _call(
    mcp: FastMCP,
    tool: str,
    args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = await mcp.call_tool(tool, args or {})
    return result.structured_content  # type: ignore[return-value]


async def _acquire(
    mcp: FastMCP,
    worker_id: str,
    **kw: Any,
) -> str:
    data = await _call(mcp, "hijack_begin", {"worker_id": worker_id, **kw})
    assert data["success"] is True
    return data["hijack_id"]


# ---------------------------------------------------------------------------
# Multi-session isolation — two workers, independent hijacks
# ---------------------------------------------------------------------------


class TestMultiSessionIsolation:
    """Two workers hijacked simultaneously must not interfere."""

    async def test_concurrent_hijacks_independent(self) -> None:
        hub, app = _make_hub_app()
        _add_worker_with_snapshot(hub, "w1", "Screen-W1")
        _add_worker_with_snapshot(hub, "w2", "Screen-W2")
        mcp = _mcp_for(app)

        hid1 = await _acquire(mcp, "w1", owner="owner-a")
        hid2 = await _acquire(mcp, "w2", owner="owner-b")

        # Both succeeded with distinct hijack IDs
        assert hid1 != hid2

        # Send to w1 only
        d = await _call(
            mcp,
            "hijack_send",
            {
                "worker_id": "w1",
                "hijack_id": hid1,
                "keys": "cmd1",
            },
        )
        assert d["success"] is True

        # Send to w2 only
        d = await _call(
            mcp,
            "hijack_send",
            {
                "worker_id": "w2",
                "hijack_id": hid2,
                "keys": "cmd2",
            },
        )
        assert d["success"] is True

        # Heartbeat both
        for wid, hid in [("w1", hid1), ("w2", hid2)]:
            d = await _call(
                mcp,
                "hijack_heartbeat",
                {
                    "worker_id": wid,
                    "hijack_id": hid,
                },
            )
            assert d["success"] is True

        # Release w1 — w2 should still be hijacked
        d = await _call(
            mcp,
            "hijack_release",
            {
                "worker_id": "w1",
                "hijack_id": hid1,
            },
        )
        assert d["success"] is True

        # w2 still works
        d = await _call(
            mcp,
            "hijack_send",
            {
                "worker_id": "w2",
                "hijack_id": hid2,
                "keys": "more",
            },
        )
        assert d["success"] is True

        # Cleanup
        await _call(
            mcp,
            "hijack_release",
            {
                "worker_id": "w2",
                "hijack_id": hid2,
            },
        )

    async def test_cross_worker_hijack_id_rejected(self) -> None:
        hub, app = _make_hub_app()
        _add_worker(hub, "w1")
        _add_worker(hub, "w2")
        mcp = _mcp_for(app)

        hid1 = await _acquire(mcp, "w1")

        # Try using w1's hijack_id on w2
        d = await _call(
            mcp,
            "hijack_send",
            {
                "worker_id": "w2",
                "hijack_id": hid1,
                "keys": "x",
            },
        )
        assert d["success"] is False

        d = await _call(
            mcp,
            "hijack_heartbeat",
            {
                "worker_id": "w2",
                "hijack_id": hid1,
            },
        )
        assert d["success"] is False

        d = await _call(
            mcp,
            "hijack_step",
            {
                "worker_id": "w2",
                "hijack_id": hid1,
            },
        )
        assert d["success"] is False

        d = await _call(
            mcp,
            "hijack_release",
            {
                "worker_id": "w2",
                "hijack_id": hid1,
            },
        )
        assert d["success"] is False

        await _call(
            mcp,
            "hijack_release",
            {
                "worker_id": "w1",
                "hijack_id": hid1,
            },
        )

    async def test_double_hijack_same_worker_rejected(self) -> None:
        hub, app = _make_hub_app()
        _add_worker(hub, "w1")
        mcp = _mcp_for(app)

        hid = await _acquire(mcp, "w1", owner="first")
        d = await _call(
            mcp,
            "hijack_begin",
            {
                "worker_id": "w1",
                "owner": "second",
            },
        )
        assert d["success"] is False

        await _call(
            mcp,
            "hijack_release",
            {
                "worker_id": "w1",
                "hijack_id": hid,
            },
        )

    async def test_re_hijack_after_release(self) -> None:
        hub, app = _make_hub_app()
        _add_worker(hub, "w1")
        mcp = _mcp_for(app)

        hid1 = await _acquire(mcp, "w1", owner="first")
        await _call(
            mcp,
            "hijack_release",
            {
                "worker_id": "w1",
                "hijack_id": hid1,
            },
        )

        hid2 = await _acquire(mcp, "w1", owner="second")
        assert hid2 != hid1
        d = await _call(
            mcp,
            "hijack_send",
            {
                "worker_id": "w1",
                "hijack_id": hid2,
                "keys": "x",
            },
        )
        assert d["success"] is True
        await _call(
            mcp,
            "hijack_release",
            {
                "worker_id": "w1",
                "hijack_id": hid2,
            },
        )

    async def test_stale_hijack_id_rejected_after_release(self) -> None:
        hub, app = _make_hub_app()
        _add_worker(hub, "w1")
        mcp = _mcp_for(app)

        hid = await _acquire(mcp, "w1")
        await _call(
            mcp,
            "hijack_release",
            {
                "worker_id": "w1",
                "hijack_id": hid,
            },
        )

        # Old hijack_id should fail
        d = await _call(
            mcp,
            "hijack_send",
            {
                "worker_id": "w1",
                "hijack_id": hid,
                "keys": "x",
            },
        )
        assert d["success"] is False


# ---------------------------------------------------------------------------
# Snapshot read across output modes
# ---------------------------------------------------------------------------


class TestSnapshotOutputModes:
    """Verify all output modes process snapshots correctly."""

    async def test_text_mode_strips_ansi_no_metadata(self) -> None:
        hub, app = _make_hub_app()
        _add_worker_with_snapshot(hub, "w1", "\x1b[32mgreen\x1b[0m text")
        mcp = _mcp_for(app)
        hid = await _acquire(mcp, "w1")

        d = await _call(
            mcp,
            "hijack_read",
            {
                "worker_id": "w1",
                "hijack_id": hid,
                "mode": "snapshot",
                "output": "text",
                "wait_ms": 50,
            },
        )
        assert d["success"] is True
        snap = d["snapshot"]
        assert "\x1b" not in snap["screen"]
        assert "green text" in snap["screen"]
        assert "cursor" not in snap
        assert "cols" not in snap

    async def test_rendered_mode_strips_ansi_keeps_metadata(self) -> None:
        hub, app = _make_hub_app()
        _add_worker_with_snapshot(hub, "w1", "\x1b[31mred\x1b[0m")
        mcp = _mcp_for(app)
        hid = await _acquire(mcp, "w1")

        d = await _call(
            mcp,
            "hijack_read",
            {
                "worker_id": "w1",
                "hijack_id": hid,
                "mode": "snapshot",
                "output": "rendered",
                "wait_ms": 50,
            },
        )
        assert d["success"] is True
        snap = d["snapshot"]
        assert "\x1b" not in snap["screen"]
        assert snap["cols"] == 80
        assert snap["rows"] == 25

    async def test_raw_mode_preserves_ansi(self) -> None:
        hub, app = _make_hub_app()
        _add_worker_with_snapshot(hub, "w1", "\x1b[33myellow\x1b[0m")
        mcp = _mcp_for(app)
        hid = await _acquire(mcp, "w1")

        d = await _call(
            mcp,
            "hijack_read",
            {
                "worker_id": "w1",
                "hijack_id": hid,
                "mode": "snapshot",
                "output": "raw",
                "wait_ms": 50,
            },
        )
        assert d["success"] is True
        assert "\x1b" in d["snapshot"]["screen"]


# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------


class TestEventLog:
    async def test_events_track_hijack_lifecycle(self) -> None:
        hub, app = _make_hub_app()
        _add_worker(hub, "w1")
        mcp = _mcp_for(app)

        hid = await _acquire(mcp, "w1")
        await _call(
            mcp,
            "hijack_send",
            {
                "worker_id": "w1",
                "hijack_id": hid,
                "keys": "test",
            },
        )
        await _call(
            mcp,
            "hijack_heartbeat",
            {
                "worker_id": "w1",
                "hijack_id": hid,
            },
        )

        d = await _call(
            mcp,
            "hijack_read",
            {
                "worker_id": "w1",
                "hijack_id": hid,
                "mode": "events",
            },
        )
        assert d["success"] is True
        events = d["events"]
        types = [e["type"] for e in events]
        assert "hijack_acquired" in types
        assert "hijack_send" in types
        assert "hijack_heartbeat" in types

        # Sequence numbers are monotonically increasing
        seqs = [e["seq"] for e in events]
        assert seqs == sorted(seqs)
        assert len(seqs) == len(set(seqs))

    async def test_events_after_seq_filters(self) -> None:
        hub, app = _make_hub_app()
        _add_worker(hub, "w1")
        mcp = _mcp_for(app)

        hid = await _acquire(mcp, "w1")
        await _call(
            mcp,
            "hijack_send",
            {
                "worker_id": "w1",
                "hijack_id": hid,
                "keys": "a",
            },
        )
        await _call(
            mcp,
            "hijack_send",
            {
                "worker_id": "w1",
                "hijack_id": hid,
                "keys": "b",
            },
        )

        # Get all events to find a midpoint seq
        d = await _call(
            mcp,
            "hijack_read",
            {
                "worker_id": "w1",
                "hijack_id": hid,
                "mode": "events",
            },
        )
        all_events = d["events"]
        mid_seq = all_events[len(all_events) // 2]["seq"]

        # Request only events after mid_seq
        d2 = await _call(
            mcp,
            "hijack_read",
            {
                "worker_id": "w1",
                "hijack_id": hid,
                "mode": "events",
                "after_seq": mid_seq,
            },
        )
        filtered = d2["events"]
        assert all(e["seq"] > mid_seq for e in filtered)
        assert len(filtered) < len(all_events)


# ---------------------------------------------------------------------------
# Key escape processing (_unescape_keys in hijack_send)
# ---------------------------------------------------------------------------


class TestKeyEscapeProcessing:
    """Verify that MCP-layer escape sequences in keys are unescaped."""

    async def test_backslash_r_unescaped_to_cr(self) -> None:
        hub, app = _make_hub_app()
        ws = _add_worker(hub, "w1")
        mcp = _mcp_for(app)
        hid = await _acquire(mcp, "w1")

        d = await _call(
            mcp,
            "hijack_send",
            {
                "worker_id": "w1",
                "hijack_id": hid,
                "keys": "hello\\r",
            },
        )
        assert d["success"] is True
        assert d["sent"] == "hello\r"

        # Verify the worker received the real CR
        sent_calls = ws.send_text.call_args_list
        import json

        for call in sent_calls:
            msg = json.loads(call[0][0])
            if msg.get("type") == "input":
                assert msg["data"] == "hello\r"
                break

    async def test_backslash_n_unescaped_to_lf(self) -> None:
        hub, app = _make_hub_app()
        _add_worker(hub, "w1")
        mcp = _mcp_for(app)
        hid = await _acquire(mcp, "w1")

        d = await _call(
            mcp,
            "hijack_send",
            {
                "worker_id": "w1",
                "hijack_id": hid,
                "keys": "line1\\nline2",
            },
        )
        assert d["success"] is True
        assert d["sent"] == "line1\nline2"

    async def test_backslash_t_unescaped_to_tab(self) -> None:
        hub, app = _make_hub_app()
        _add_worker(hub, "w1")
        mcp = _mcp_for(app)
        hid = await _acquire(mcp, "w1")

        d = await _call(
            mcp,
            "hijack_send",
            {
                "worker_id": "w1",
                "hijack_id": hid,
                "keys": "a\\tb",
            },
        )
        assert d["success"] is True
        assert d["sent"] == "a\tb"

    async def test_escape_sequence_x1b(self) -> None:
        hub, app = _make_hub_app()
        _add_worker(hub, "w1")
        mcp = _mcp_for(app)
        hid = await _acquire(mcp, "w1")

        d = await _call(
            mcp,
            "hijack_send",
            {
                "worker_id": "w1",
                "hijack_id": hid,
                "keys": "\\x1b[A",
            },
        )
        assert d["success"] is True
        assert d["sent"] == "\x1b[A"

    async def test_escape_sequence_backslash_e(self) -> None:
        hub, app = _make_hub_app()
        _add_worker(hub, "w1")
        mcp = _mcp_for(app)
        hid = await _acquire(mcp, "w1")

        d = await _call(
            mcp,
            "hijack_send",
            {
                "worker_id": "w1",
                "hijack_id": hid,
                "keys": "\\e[B",
            },
        )
        assert d["success"] is True
        assert d["sent"] == "\x1b[B"

    async def test_literal_backslash(self) -> None:
        hub, app = _make_hub_app()
        _add_worker(hub, "w1")
        mcp = _mcp_for(app)
        hid = await _acquire(mcp, "w1")

        d = await _call(
            mcp,
            "hijack_send",
            {
                "worker_id": "w1",
                "hijack_id": hid,
                "keys": "path\\\\file",
            },
        )
        assert d["success"] is True
        assert d["sent"] == "path\\file"

    async def test_multiple_escapes_in_one_string(self) -> None:
        hub, app = _make_hub_app()
        _add_worker(hub, "w1")
        mcp = _mcp_for(app)
        hid = await _acquire(mcp, "w1")

        d = await _call(
            mcp,
            "hijack_send",
            {
                "worker_id": "w1",
                "hijack_id": hid,
                "keys": "ls\\r\\necho hi\\r",
            },
        )
        assert d["success"] is True
        assert d["sent"] == "ls\r\necho hi\r"

    async def test_plain_text_no_escapes(self) -> None:
        hub, app = _make_hub_app()
        _add_worker(hub, "w1")
        mcp = _mcp_for(app)
        hid = await _acquire(mcp, "w1")

        d = await _call(
            mcp,
            "hijack_send",
            {
                "worker_id": "w1",
                "hijack_id": hid,
                "keys": "hello world",
            },
        )
        assert d["success"] is True
        assert d["sent"] == "hello world"


# ---------------------------------------------------------------------------
# Mode switching
# ---------------------------------------------------------------------------


class TestModeSwitching:
    """Session and worker mode switching through MCP tools."""

    async def test_session_mode_round_trip(self) -> None:
        app = _server_app()
        mcp = _mcp_for_server(app)

        d = await _call(
            mcp,
            "session_set_mode",
            {
                "session_id": "sh-1",
                "mode": "hijack",
            },
        )
        assert d["success"] is True
        assert d["input_mode"] == "hijack"

        d = await _call(
            mcp,
            "session_set_mode",
            {
                "session_id": "sh-1",
                "mode": "open",
            },
        )
        assert d["success"] is True
        assert d["input_mode"] == "open"

    async def test_worker_mode_round_trip(self) -> None:
        hub, app = _make_hub_app()
        _add_worker(hub, "w1")
        mcp = _mcp_for(app)

        d = await _call(
            mcp,
            "worker_input_mode",
            {
                "worker_id": "w1",
                "mode": "open",
            },
        )
        assert d["success"] is True
        assert d["input_mode"] == "open"

        d = await _call(
            mcp,
            "worker_input_mode",
            {
                "worker_id": "w1",
                "mode": "hijack",
            },
        )
        assert d["success"] is True
        assert d["input_mode"] == "hijack"

    async def test_mode_persists_across_reads(self) -> None:
        app = _server_app()
        mcp = _mcp_for_server(app)

        await _call(
            mcp,
            "session_set_mode",
            {
                "session_id": "sh-1",
                "mode": "hijack",
            },
        )
        d = await _call(mcp, "session_status", {"session_id": "sh-1"})
        assert d["input_mode"] == "hijack"

        await _call(
            mcp,
            "session_set_mode",
            {
                "session_id": "sh-1",
                "mode": "open",
            },
        )
        d = await _call(mcp, "session_status", {"session_id": "sh-1"})
        assert d["input_mode"] == "open"


# ---------------------------------------------------------------------------
# Multi-session server lifecycle
# ---------------------------------------------------------------------------


class TestMultiSessionServerLifecycle:
    """Multiple sessions through the full server app MCP layer."""

    async def test_list_shows_all_configured(self) -> None:
        app = _server_app()
        mcp = _mcp_for_server(app)

        d = await _call(mcp, "session_list")
        assert d["success"] is True
        ids = {s["session_id"] for s in d["data"]}
        assert {"sh-1", "sh-2"} <= ids

    async def test_connect_disconnect_independent(self) -> None:
        app = _server_app()
        mcp = _mcp_for_server(app)

        # Connect sh-1 only
        d = await _call(mcp, "session_connect", {"session_id": "sh-1"})
        assert d["success"] is True

        # sh-2 still stopped
        d2 = await _call(mcp, "session_status", {"session_id": "sh-2"})
        assert d2["lifecycle_state"] == "stopped"

        await _call(mcp, "session_disconnect", {"session_id": "sh-1"})

    async def test_ephemeral_session_appears_in_list(self) -> None:
        app = _server_app()
        mcp = _mcp_for_server(app)

        d = await _call(
            mcp,
            "session_create",
            {
                "connector_type": "shell",
                "display_name": "Ephemeral-Test",
            },
        )
        assert d["success"] is True
        eph_id = d["session_id"]

        listing = await _call(mcp, "session_list")
        ids = {s["session_id"] for s in listing["data"]}
        assert eph_id in ids

    async def test_ephemeral_session_properties(self) -> None:
        app = _server_app()
        mcp = _mcp_for_server(app)

        d = await _call(
            mcp,
            "session_create",
            {
                "connector_type": "shell",
                "display_name": "PropTest",
                "input_mode": "hijack",
            },
        )
        assert d["success"] is True
        assert d["visibility"] == "private"
        assert d["owner"] == "tester"

    async def test_session_status_unknown_returns_failure(self) -> None:
        app = _server_app()
        mcp = _mcp_for_server(app)

        d = await _call(mcp, "session_status", {"session_id": "no-such"})
        assert d["success"] is False

    async def test_connect_disconnect_unknown_returns_failure(self) -> None:
        app = _server_app()
        mcp = _mcp_for_server(app)

        for tool in ("session_connect", "session_disconnect"):
            d = await _call(mcp, tool, {"session_id": "no-such"})
            assert d["success"] is False


# ---------------------------------------------------------------------------
# Worker control on disconnected/missing worker
# ---------------------------------------------------------------------------


class TestWorkerControlErrors:
    async def test_input_mode_no_worker(self) -> None:
        _hub, app = _make_hub_app()
        mcp = _mcp_for(app)

        d = await _call(
            mcp,
            "worker_input_mode",
            {
                "worker_id": "ghost",
                "mode": "open",
            },
        )
        assert d["success"] is False

    async def test_disconnect_no_worker(self) -> None:
        _hub, app = _make_hub_app()
        mcp = _mcp_for(app)

        d = await _call(mcp, "worker_disconnect", {"worker_id": "ghost"})
        assert d["success"] is False

    async def test_hijack_begin_no_worker(self) -> None:
        _hub, app = _make_hub_app()
        mcp = _mcp_for(app)

        d = await _call(mcp, "hijack_begin", {"worker_id": "ghost"})
        assert d["success"] is False

    async def test_worker_disconnect_then_hijack_fails(self) -> None:
        hub, app = _make_hub_app()
        _add_worker(hub, "w1")
        mcp = _mcp_for(app)

        d = await _call(mcp, "worker_disconnect", {"worker_id": "w1"})
        assert d["success"] is True

        d = await _call(mcp, "hijack_begin", {"worker_id": "w1"})
        assert d["success"] is False


# ---------------------------------------------------------------------------
# Hijack with guard parameters
# ---------------------------------------------------------------------------


class TestHijackSendGuards:
    async def test_send_with_expect_prompt_id_timeout(self) -> None:
        """Guard waits for prompt, times out — send still succeeds (prompt not matched)."""
        hub, app = _make_hub_app()
        _add_worker(hub, "w1")
        mcp = _mcp_for(app)
        hid = await _acquire(mcp, "w1")

        d = await _call(
            mcp,
            "hijack_send",
            {
                "worker_id": "w1",
                "hijack_id": hid,
                "keys": "x",
                "expect_prompt_id": "nonexistent_prompt",
                "timeout_ms": 100,
            },
        )
        assert isinstance(d, dict)
        assert "success" in d

    async def test_send_with_expect_regex_timeout(self) -> None:
        hub, app = _make_hub_app()
        _add_worker(hub, "w1")
        mcp = _mcp_for(app)
        hid = await _acquire(mcp, "w1")

        d = await _call(
            mcp,
            "hijack_send",
            {
                "worker_id": "w1",
                "hijack_id": hid,
                "keys": "x",
                "expect_regex": r"impossible_pattern_xyz",
                "timeout_ms": 100,
            },
        )
        assert isinstance(d, dict)
        assert "success" in d


# ---------------------------------------------------------------------------
# Session read across multiple sessions
# ---------------------------------------------------------------------------


class TestSessionReadMultiple:
    async def test_read_two_sessions_independently(self) -> None:
        hub, app = _make_hub_app()
        _add_worker_with_snapshot(hub, "w1", "Screen-Alpha")
        _add_worker_with_snapshot(hub, "w2", "Screen-Beta")
        mcp = _mcp_for(app)

        # Read via hijack — each shows its own screen
        hid1 = await _acquire(mcp, "w1")
        hid2 = await _acquire(mcp, "w2")

        d1 = await _call(
            mcp,
            "hijack_read",
            {
                "worker_id": "w1",
                "hijack_id": hid1,
                "mode": "snapshot",
                "output": "text",
                "wait_ms": 50,
            },
        )
        d2 = await _call(
            mcp,
            "hijack_read",
            {
                "worker_id": "w2",
                "hijack_id": hid2,
                "mode": "snapshot",
                "output": "text",
                "wait_ms": 50,
            },
        )

        assert "Alpha" in d1["snapshot"]["screen"]
        assert "Beta" in d2["snapshot"]["screen"]
        assert "Beta" not in d1["snapshot"]["screen"]
        assert "Alpha" not in d2["snapshot"]["screen"]


# ---------------------------------------------------------------------------
# Lease expiry semantics
# ---------------------------------------------------------------------------


class TestLeaseExpiry:
    async def test_heartbeat_extends_lease(self) -> None:
        hub, app = _make_hub_app()
        _add_worker(hub, "w1")
        mcp = _mcp_for(app)
        hid = await _acquire(mcp, "w1")

        d1 = await _call(
            mcp,
            "hijack_heartbeat",
            {
                "worker_id": "w1",
                "hijack_id": hid,
                "lease_s": 60,
            },
        )
        exp1 = d1["lease_expires_at"]

        # Second heartbeat with longer lease
        d2 = await _call(
            mcp,
            "hijack_heartbeat",
            {
                "worker_id": "w1",
                "hijack_id": hid,
                "lease_s": 120,
            },
        )
        exp2 = d2["lease_expires_at"]
        assert exp2 > exp1

    async def test_custom_lease_on_acquire(self) -> None:
        hub, app = _make_hub_app()
        _add_worker(hub, "w1")
        mcp = _mcp_for(app)

        d = await _call(
            mcp,
            "hijack_begin",
            {
                "worker_id": "w1",
                "lease_s": 30,
            },
        )
        assert d["success"] is True
        # Lease should expire ~30s from now (allow 5s tolerance)
        assert d["lease_expires_at"] < time.time() + 35
        assert d["lease_expires_at"] > time.time() + 25
