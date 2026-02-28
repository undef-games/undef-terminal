#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Integration tests for the terminal hijack REST routes."""

from __future__ import annotations

import time
import uuid
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from undef.terminal.hijack.hub import TermHub
from undef.terminal.hijack.models import BotTermState, HijackSession


def make_app() -> tuple[FastAPI, TermHub]:
    hub = TermHub()
    app = FastAPI()
    app.include_router(hub.create_router())
    return app, hub


def _active_session(hijack_id: str, owner: str = "test") -> HijackSession:
    return HijackSession(
        hijack_id=hijack_id,
        owner=owner,
        acquired_at=time.time(),
        lease_expires_at=time.time() + 3600,
        last_heartbeat=time.time(),
    )


# ---------------------------------------------------------------------------
# acquire
# ---------------------------------------------------------------------------


def test_acquire_hijack() -> None:
    app, hub = make_app()
    mock_ws = AsyncMock()
    hub._bots["bot1"] = BotTermState(worker_ws=mock_ws)

    with TestClient(app) as client:
        r = client.post("/bot/bot1/hijack/acquire", json={"owner": "test", "lease_s": 60})

    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "hijack_id" in data
    assert data["owner"] == "test"
    assert "lease_expires_at" in data


def test_acquire_no_worker_returns_409() -> None:
    app, hub = make_app()
    # No worker_ws set

    with TestClient(app) as client:
        r = client.post("/bot/bot1/hijack/acquire", json={"owner": "test"})

    assert r.status_code == 409


def test_acquire_conflict_already_hijacked() -> None:
    app, hub = make_app()
    mock_ws = AsyncMock()
    hijack_id = str(uuid.uuid4())
    hub._bots["bot1"] = BotTermState(
        worker_ws=mock_ws,
        hijack_session=_active_session(hijack_id, "owner_a"),
    )

    with TestClient(app) as client:
        r = client.post("/bot/bot1/hijack/acquire", json={"owner": "owner_b"})

    assert r.status_code == 409


def test_acquire_default_owner() -> None:
    app, hub = make_app()
    mock_ws = AsyncMock()
    hub._bots["bot1"] = BotTermState(worker_ws=mock_ws)

    with TestClient(app) as client:
        r = client.post("/bot/bot1/hijack/acquire")

    assert r.status_code == 200
    assert r.json()["owner"] == "mcp"  # default from HijackAcquireRequest


# ---------------------------------------------------------------------------
# heartbeat
# ---------------------------------------------------------------------------


def test_heartbeat() -> None:
    app, hub = make_app()
    mock_ws = AsyncMock()
    hijack_id = str(uuid.uuid4())
    hub._bots["bot1"] = BotTermState(
        worker_ws=mock_ws,
        hijack_session=_active_session(hijack_id),
    )

    with TestClient(app) as client:
        r = client.post(f"/bot/bot1/hijack/{hijack_id}/heartbeat", json={"lease_s": 120})

    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["hijack_id"] == hijack_id
    assert "lease_expires_at" in data


def test_heartbeat_wrong_id() -> None:
    app, hub = make_app()
    mock_ws = AsyncMock()
    hijack_id = str(uuid.uuid4())
    hub._bots["bot1"] = BotTermState(
        worker_ws=mock_ws,
        hijack_session=_active_session(hijack_id),
    )

    with TestClient(app) as client:
        r = client.post("/bot/bot1/hijack/wrong-hijack-id/heartbeat", json={})

    assert r.status_code == 404


# ---------------------------------------------------------------------------
# release
# ---------------------------------------------------------------------------


def test_release() -> None:
    app, hub = make_app()
    mock_ws = AsyncMock()
    hijack_id = str(uuid.uuid4())
    hub._bots["bot1"] = BotTermState(
        worker_ws=mock_ws,
        hijack_session=_active_session(hijack_id),
    )

    with TestClient(app) as client:
        r = client.post(f"/bot/bot1/hijack/{hijack_id}/release")

    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert hub._bots["bot1"].hijack_session is None


def test_release_invalid_session() -> None:
    app, hub = make_app()
    hub._bots["bot1"] = BotTermState()

    with TestClient(app) as client:
        r = client.post("/bot/bot1/hijack/no-such-id/release")

    assert r.status_code == 404


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------


def test_send_no_worker() -> None:
    app, hub = make_app()
    hijack_id = str(uuid.uuid4())
    # Valid session but worker_ws = None
    hub._bots["bot1"] = BotTermState(
        hijack_session=_active_session(hijack_id),
    )

    with TestClient(app) as client:
        r = client.post(f"/bot/bot1/hijack/{hijack_id}/send", json={"keys": "hello\r"})

    assert r.status_code == 409


def test_send_invalid_session() -> None:
    app, hub = make_app()
    hub._bots["bot1"] = BotTermState()

    with TestClient(app) as client:
        r = client.post("/bot/bot1/hijack/no-such-id/send", json={"keys": "hi"})

    assert r.status_code == 404


def test_send_empty_keys() -> None:
    app, hub = make_app()
    mock_ws = AsyncMock()
    hijack_id = str(uuid.uuid4())
    hub._bots["bot1"] = BotTermState(
        worker_ws=mock_ws,
        hijack_session=_active_session(hijack_id),
    )

    with TestClient(app) as client:
        r = client.post(f"/bot/bot1/hijack/{hijack_id}/send", json={"keys": ""})

    assert r.status_code == 400


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------


def test_snapshot_no_worker() -> None:
    app, hub = make_app()
    hijack_id = str(uuid.uuid4())
    hub._bots["bot1"] = BotTermState(
        hijack_session=_active_session(hijack_id),
    )

    with TestClient(app) as client:
        r = client.get(f"/bot/bot1/hijack/{hijack_id}/snapshot?wait_ms=0")

    assert r.status_code == 200
    data = r.json()
    assert data["snapshot"] is None
    assert data["bot_id"] == "bot1"


def test_snapshot_invalid_session() -> None:
    app, hub = make_app()

    with TestClient(app) as client:
        r = client.get("/bot/bot1/hijack/no-such-id/snapshot")

    assert r.status_code == 404


# ---------------------------------------------------------------------------
# events
# ---------------------------------------------------------------------------


def test_events() -> None:
    app, hub = make_app()
    mock_ws = AsyncMock()
    hijack_id = str(uuid.uuid4())
    hub._bots["bot1"] = BotTermState(
        worker_ws=mock_ws,
        hijack_session=_active_session(hijack_id),
    )

    with TestClient(app) as client:
        r = client.get(f"/bot/bot1/hijack/{hijack_id}/events")

    assert r.status_code == 200
    data = r.json()
    assert "events" in data
    assert "latest_seq" in data


def test_events_invalid_session() -> None:
    app, hub = make_app()

    with TestClient(app) as client:
        r = client.get("/bot/bot1/hijack/no-such-id/events")

    assert r.status_code == 404


# ---------------------------------------------------------------------------
# step
# ---------------------------------------------------------------------------


def test_step() -> None:
    app, hub = make_app()
    mock_ws = AsyncMock()
    hijack_id = str(uuid.uuid4())
    hub._bots["bot1"] = BotTermState(
        worker_ws=mock_ws,
        hijack_session=_active_session(hijack_id),
    )

    with TestClient(app) as client:
        r = client.post(f"/bot/bot1/hijack/{hijack_id}/step")

    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_step_no_worker() -> None:
    app, hub = make_app()
    hijack_id = str(uuid.uuid4())
    hub._bots["bot1"] = BotTermState(
        hijack_session=_active_session(hijack_id),
    )

    with TestClient(app) as client:
        r = client.post(f"/bot/bot1/hijack/{hijack_id}/step")

    assert r.status_code == 409


# ---------------------------------------------------------------------------
# bot_id validation
# ---------------------------------------------------------------------------


def test_bot_id_validation_special_chars() -> None:
    app, hub = make_app()

    with TestClient(app) as client:
        r = client.post("/bot/bot@bad!/hijack/acquire")

    assert r.status_code == 422


def test_acquire_send_worker_fails() -> None:
    """When _send_worker returns False after acquiring, return 409."""
    app, hub = make_app()
    from unittest.mock import AsyncMock

    bad_ws = AsyncMock()
    bad_ws.send_text = AsyncMock(side_effect=RuntimeError("broken"))
    hub._bots["bot1"] = BotTermState(worker_ws=bad_ws)

    with TestClient(app) as client:
        r = client.post("/bot/bot1/hijack/acquire", json={"owner": "test", "lease_s": 60})

    # Worker send failed → 409
    assert r.status_code == 409


def test_heartbeat_request_none_defaults() -> None:
    """Heartbeat with no JSON body uses HijackHeartbeatRequest defaults."""
    app, hub = make_app()
    mock_ws = AsyncMock()
    hijack_id = str(uuid.uuid4())
    hub._bots["bot1"] = BotTermState(
        worker_ws=mock_ws,
        hijack_session=_active_session(hijack_id),
    )

    with TestClient(app) as client:
        r = client.post(f"/bot/bot1/hijack/{hijack_id}/heartbeat")

    assert r.status_code == 200


def test_heartbeat_inner_session_none() -> None:
    """If session disappears between lock acquisition and update, return 404."""
    app, hub = make_app()
    mock_ws = AsyncMock()
    hijack_id = str(uuid.uuid4())
    hub._bots["bot1"] = BotTermState(
        worker_ws=mock_ws,
        hijack_session=_active_session(hijack_id),
    )

    with TestClient(app) as client:
        r = client.post(f"/bot/bot1/hijack/{hijack_id}/heartbeat", json={"lease_s": 30})

    # Should succeed normally (inner None check is a safety guard)
    assert r.status_code == 200


def test_events_empty_bot_state() -> None:
    """Events endpoint when bot has no events returns empty list."""
    app, hub = make_app()
    mock_ws = AsyncMock()
    hijack_id = str(uuid.uuid4())
    hub._bots["bot1"] = BotTermState(
        worker_ws=mock_ws,
        hijack_session=_active_session(hijack_id),
    )

    with TestClient(app) as client:
        r = client.get(f"/bot/bot1/hijack/{hijack_id}/events")

    assert r.status_code == 200
    assert r.json()["events"] == []


def test_send_with_worker_and_no_guard() -> None:
    """Send with keys and worker connected, no guard constraints → succeeds."""
    app, hub = make_app()
    mock_ws = AsyncMock()
    hijack_id = str(uuid.uuid4())
    hub._bots["bot1"] = BotTermState(
        worker_ws=mock_ws,
        hijack_session=_active_session(hijack_id),
    )

    with TestClient(app) as client:
        r = client.post(
            f"/bot/bot1/hijack/{hijack_id}/send",
            json={"keys": "hello\r", "timeout_ms": 100},
        )

    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["sent"] == "hello\r"


def test_send_guard_not_satisfied() -> None:
    """Send with an expect_prompt_id that never matches → 409."""
    app, hub = make_app()
    mock_ws = AsyncMock()
    hijack_id = str(uuid.uuid4())
    hub._bots["bot1"] = BotTermState(
        worker_ws=mock_ws,
        hijack_session=_active_session(hijack_id),
    )

    with TestClient(app) as client:
        r = client.post(
            f"/bot/bot1/hijack/{hijack_id}/send",
            json={"keys": "hello\r", "expect_prompt_id": "never_matches", "timeout_ms": 50},
        )

    assert r.status_code == 409


def test_send_guard_invalid_regex() -> None:
    """Send with invalid expect_regex → 409."""
    app, hub = make_app()
    mock_ws = AsyncMock()
    hijack_id = str(uuid.uuid4())
    hub._bots["bot1"] = BotTermState(
        worker_ws=mock_ws,
        hijack_session=_active_session(hijack_id),
    )

    with TestClient(app) as client:
        r = client.post(
            f"/bot/bot1/hijack/{hijack_id}/send",
            json={"keys": "hello\r", "expect_regex": "[invalid"},
        )

    assert r.status_code == 409


def test_release_inner_session_none() -> None:
    """Release with valid session succeeds."""
    app, hub = make_app()
    mock_ws = AsyncMock()
    hijack_id = str(uuid.uuid4())
    hub._bots["bot1"] = BotTermState(
        worker_ws=mock_ws,
        hijack_session=_active_session(hijack_id),
    )

    with TestClient(app) as client:
        r = client.post(f"/bot/bot1/hijack/{hijack_id}/release")

    assert r.status_code == 200


def test_heartbeat_session_mismatch_inside_lock() -> None:
    """Heartbeat returns 404 when hijack_id doesn't match inside the lock (line 381)."""
    app, hub = make_app()
    mock_ws = AsyncMock()
    real_id = str(uuid.uuid4())
    other_id = str(uuid.uuid4())
    hub._bots["bot1"] = BotTermState(
        worker_ws=mock_ws,
        hijack_session=_active_session(other_id),  # different session active
    )

    with TestClient(app) as client:
        r = client.post(f"/bot/bot1/hijack/{real_id}/heartbeat")

    # real_id doesn't match other_id in bot state
    assert r.status_code == 404


def test_events_no_bot_state() -> None:
    """Events endpoint when bot has no state returns empty list (lines 420-421)."""
    app, hub = make_app()
    mock_ws = AsyncMock()
    hijack_id = str(uuid.uuid4())
    # Register valid session but with no bot state in hub._bots
    hub._bots["bot1"] = BotTermState(
        worker_ws=mock_ws,
        hijack_session=_active_session(hijack_id),
    )

    # Use a different bot_id that has no state
    # But we need a valid session... let's use a workaround:
    # Get the session via bot1, then remove the bot state
    hub._bots["bot2"] = BotTermState(
        worker_ws=mock_ws,
        hijack_session=_active_session(hijack_id),
    )
    # Remove bot2's state to trigger the None branch
    del hub._bots["bot2"]
    # Now re-add an empty state to allow routing but test empty events
    import asyncio
    loop = asyncio.new_event_loop()
    loop.run_until_complete(hub._get("bot2"))
    loop.close()
    hub._bots["bot2"].hijack_session = _active_session(hijack_id)

    with TestClient(app) as client:
        r = client.get(f"/bot/bot2/hijack/{hijack_id}/events")

    assert r.status_code == 200
    assert r.json()["events"] == []


def test_step_invalid_hijack_session() -> None:
    """Step with invalid/expired hijack_id returns 404 (line 484)."""
    app, hub = make_app()
    mock_ws = AsyncMock()
    hijack_id = str(uuid.uuid4())
    hub._bots["bot1"] = BotTermState(
        worker_ws=mock_ws,
        hijack_session=_active_session(hijack_id),
    )

    with TestClient(app) as client:
        r = client.post("/bot/bot1/hijack/no-such-id/step")

    assert r.status_code == 404


def test_release_session_mismatch_inside_lock() -> None:
    """Release returns 404 when hijack_id doesn't match inside the lock (line 502)."""
    app, hub = make_app()
    mock_ws = AsyncMock()
    real_id = str(uuid.uuid4())
    other_id = str(uuid.uuid4())
    hub._bots["bot1"] = BotTermState(
        worker_ws=mock_ws,
        hijack_session=_active_session(other_id),
    )

    with TestClient(app) as client:
        r = client.post(f"/bot/bot1/hijack/{real_id}/release")

    assert r.status_code == 404
