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
