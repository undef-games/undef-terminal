#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Security and regression tests for hosted server hardening fixes."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from undef.terminal.server import create_server_app, default_server_config
from undef.terminal.server.auth import Principal
from undef.terminal.server.models import AuthConfig, SessionDefinition
from undef.terminal.server.policy import SessionPolicyResolver
from undef.terminal.server.runtime import _cancel_and_wait


def test_policy_ignores_requested_role_in_header_mode() -> None:
    policy = SessionPolicyResolver(AuthConfig(mode="header"))
    session = SessionDefinition(session_id="s1", display_name="Session", connector_type="demo")

    role = policy.role_for(Principal(name="anonymous", requested_role="admin", surface="user"), session)

    assert role == "viewer"


def test_header_mode_requires_auth_for_api_and_ws_routes() -> None:
    config = default_server_config()
    config.auth.mode = "header"
    app = create_server_app(config)

    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 401

        with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws/browser/demo-session/term"):
            pass


def test_replay_page_honors_custom_app_path() -> None:
    config = default_server_config()
    config.ui.app_path = "/ops"
    app = create_server_app(config)

    with TestClient(app) as client:
        replay = client.get("/ops/replay/demo-session")

    assert replay.status_code == 200
    assert '"app_path": "/ops"' in replay.text


def test_compiled_frontend_views_escape_dynamic_values() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "undef" / "terminal" / "frontend" / "app" / "views"
    dashboard_js = (root / "dashboard-view.js").read_text(encoding="utf-8")
    operator_js = (root / "operator-view.js").read_text(encoding="utf-8")

    assert "function escapeHtml(value)" in dashboard_js
    assert "function escapeHtml(value)" in operator_js
    assert "const safeAppPath = escapeHtml(appPath);" in dashboard_js
    assert "const safeAppPath = escapeHtml(bootstrap.app_path);" in operator_js
    assert "${bootstrap.app_path}/replay/" not in operator_js


@pytest.mark.asyncio
async def test_cancel_and_wait_cancels_and_drains_pending_tasks() -> None:
    task = asyncio.create_task(asyncio.sleep(60.0))

    await _cancel_and_wait({task})

    assert task.done()
    assert task.cancelled()
