#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Security and regression tests for hosted server hardening fixes."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from undef.terminal.server import config_from_mapping, create_server_app, default_server_config
from undef.terminal.server.auth import Principal
from undef.terminal.server.models import AuthConfig, SessionDefinition
from undef.terminal.server.policy import SessionPolicyResolver
from undef.terminal.server.routes.api import create_api_router
from undef.terminal.server.runtime import _cancel_and_wait

_TEST_SIGNING_KEY = "uterm-test-secret-32-byte-minimum-key"


def _jwt_headers(
    *, sub: str, roles: list[str], issuer: str = "undef-terminal", audience: str = "undef-terminal-server"
) -> dict[str, str]:
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": sub,
            "roles": roles,
            "iss": issuer,
            "aud": audience,
            "iat": now,
            "nbf": now,
            "exp": now + 600,
        },
        key=_TEST_SIGNING_KEY,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def _jwt_config() -> AuthConfig:
    now = int(time.time())
    worker_token = jwt.encode(
        {
            "sub": "runtime-worker",
            "roles": ["admin"],
            "iss": "undef-terminal",
            "aud": "undef-terminal-server",
            "iat": now,
            "nbf": now,
            "exp": now + 600,
        },
        key=_TEST_SIGNING_KEY,
        algorithm="HS256",
    )
    return AuthConfig(
        mode="jwt",
        jwt_public_key_pem=_TEST_SIGNING_KEY,
        jwt_algorithms=["HS256"],
        worker_bearer_token=worker_token,
    )


def test_policy_uses_trusted_roles_only() -> None:
    policy = SessionPolicyResolver(_jwt_config())
    session = SessionDefinition(session_id="s1", display_name="Session", connector_type="demo")

    role = policy.role_for(Principal(subject_id="user-1", roles=frozenset({"viewer"})), session)

    assert role == "viewer"


def test_jwt_mode_requires_auth_for_api_and_ws_routes() -> None:
    config = default_server_config()
    config.auth = _jwt_config()
    app = create_server_app(config)

    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 401

        with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws/browser/demo-session/term"):
            pass


def test_jwt_mode_rejects_invalid_issuer() -> None:
    config = default_server_config()
    config.auth = _jwt_config()
    app = create_server_app(config)

    with TestClient(app) as client:
        health = client.get("/api/health", headers=_jwt_headers(sub="alice", roles=["admin"], issuer="wrong-issuer"))
        assert health.status_code == 401


def test_jwt_mode_ignores_cookie_and_role_header_escalation_for_ws() -> None:
    config = default_server_config()
    config.auth = _jwt_config()
    app = create_server_app(config)

    with (
        TestClient(app) as client,
        client.websocket_connect(
            "/ws/worker/demo-session/term",
            headers={"Authorization": f"Bearer {config.auth.worker_bearer_token}"},
        ) as worker,
    ):
        msg = worker.receive_json()
        assert msg["type"] == "snapshot_req"

        with client.websocket_connect(
            "/ws/browser/demo-session/term",
            headers={
                **_jwt_headers(sub="viewer-a", roles=["viewer"]),
                config.auth.role_header: "admin",
                "Cookie": f"{config.auth.surface_cookie}=operator",
            },
        ) as browser:
            hello = browser.receive_json()
            assert hello["type"] == "hello"
            assert hello["role"] == "viewer"
            assert hello["can_hijack"] is False
            assert hello["hijack_control"] == "ws"
            assert hello["hijack_step_supported"] is True


def test_jwt_api_enforces_role_and_ownership() -> None:
    config = default_server_config()
    config.auth = _jwt_config()
    app = create_server_app(config)

    with TestClient(app) as client:
        # viewer may read but cannot mutate
        sessions = client.get("/api/sessions", headers=_jwt_headers(sub="viewer-1", roles=["viewer"]))
        assert sessions.status_code == 200
        assert sessions.json()

        create_forbidden = client.post(
            "/api/sessions",
            headers=_jwt_headers(sub="viewer-1", roles=["viewer"]),
            json={"session_id": "v1", "display_name": "viewer-created", "connector_type": "demo"},
        )
        assert create_forbidden.status_code == 403

        # operator can create but owner is forced to self when not admin
        created = client.post(
            "/api/sessions",
            headers=_jwt_headers(sub="op-1", roles=["operator"]),
            json={"session_id": "owned-op", "display_name": "Owned", "connector_type": "demo", "owner": "someone-else"},
        )
        assert created.status_code == 403

        created_ok = client.post(
            "/api/sessions",
            headers=_jwt_headers(sub="op-1", roles=["operator"]),
            json={"session_id": "owned-op", "display_name": "Owned", "connector_type": "demo"},
        )
        assert created_ok.status_code == 200

        mode_ok = client.post(
            "/api/sessions/owned-op/mode",
            headers=_jwt_headers(sub="op-1", roles=["operator"]),
            json={"input_mode": "hijack"},
        )
        assert mode_ok.status_code == 200

        mode_forbidden = client.post(
            "/api/sessions/owned-op/mode",
            headers=_jwt_headers(sub="op-2", roles=["operator"]),
            json={"input_mode": "open"},
        )
        assert mode_forbidden.status_code == 403

        mode_admin = client.post(
            "/api/sessions/owned-op/mode",
            headers=_jwt_headers(sub="admin-1", roles=["admin"]),
            json={"input_mode": "open"},
        )
        assert mode_admin.status_code == 200


def test_replay_page_honors_custom_app_path() -> None:
    config = default_server_config()
    config.ui.app_path = "/ops"
    app = create_server_app(config)

    with TestClient(app) as client:
        replay = client.get("/ops/replay/demo-session")

    assert replay.status_code == 200
    assert '"app_path": "/ops"' in replay.text


def test_page_routes_set_explicit_cookie_security_flags() -> None:
    config = default_server_config()
    app = create_server_app(config)

    with TestClient(app) as client:
        response = client.get("/app/", headers={"X-Forwarded-Proto": "https"})

    assert response.status_code == 200
    set_cookie = ",".join(response.headers.get_list("set-cookie")).lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "secure" in set_cookie


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


# ---------------------------------------------------------------------------
# Third-review regression tests
# ---------------------------------------------------------------------------


def test_session_id_path_pattern_rejects_invalid_characters() -> None:
    r"""FastAPI path pattern ^[\w\-]+$ should reject dots, slashes, and other chars."""
    config = default_server_config()
    app = create_server_app(config)
    with TestClient(app) as client:
        r = client.get("/api/sessions/bad.session.id")
        assert r.status_code == 422

        r = client.get("/api/sessions/contains space")
        assert r.status_code == 422


def test_events_limit_query_rejects_out_of_range() -> None:
    """Query(ge=1, le=500) on limit means 0 and 501 must return 422."""
    config = default_server_config()
    app = create_server_app(config)
    with TestClient(app) as client:
        r = client.get("/api/sessions/demo-session/events?limit=0")
        assert r.status_code == 422

        r = client.get("/api/sessions/demo-session/events?limit=501")
        assert r.status_code == 422

        r = client.get("/api/sessions/demo-session/recording/entries?limit=0")
        assert r.status_code == 422


def test_health_returns_503_when_registry_not_initialized() -> None:
    """GET /api/health must return 503 when the registry is absent from app state."""
    bare = FastAPI()
    bare.include_router(create_api_router())
    with TestClient(bare) as client:
        r = client.get("/api/health")
        assert r.status_code == 503
        data = r.json()
        assert data["ok"] is False
        assert data["ready"] is False


def test_patch_session_rejects_invalid_input_mode() -> None:
    """PATCH /api/sessions/{id} with an unrecognised input_mode must return 422."""
    config = default_server_config()
    app = create_server_app(config)
    with TestClient(app) as client:
        r = client.patch("/api/sessions/demo-session", json={"input_mode": "garbage"})
        assert r.status_code == 422


def test_delete_session_idempotent_returns_404_on_second_call() -> None:
    """A second DELETE for a removed session returns 404, not 500."""
    config = default_server_config()
    app = create_server_app(config)
    with TestClient(app) as client:
        r1 = client.delete("/api/sessions/demo-session")
        assert r1.status_code == 200

        r2 = client.delete("/api/sessions/demo-session")
        assert r2.status_code == 404


def test_create_server_app_rejects_none_jwt_algorithm() -> None:
    """'none' in jwt_algorithms must be rejected at app construction time."""
    config = default_server_config()
    config.auth.mode = "jwt"
    config.auth.jwt_algorithms = ["none"]
    config.auth.jwt_public_key_pem = "dummy-key"
    config.auth.worker_bearer_token = "dummy-token"  # noqa: S105
    with pytest.raises(ValueError, match="'none' is not permitted"):
        create_server_app(config)


def test_page_route_returns_403_for_private_session_viewer() -> None:
    """A viewer-role principal must receive 403 on a private-visibility session page."""
    config = default_server_config()
    config.sessions[0].visibility = "private"
    app = create_server_app(config)
    with TestClient(app) as client:
        r = client.get(
            f"{config.ui.app_path}/session/demo-session",
            headers={"x-uterm-role": "viewer"},
        )
        assert r.status_code == 403


def test_config_from_mapping_rejects_negative_max_bytes() -> None:
    """recording.max_bytes < 0 must raise ValueError at config load time."""
    with pytest.raises(ValueError, match="max_bytes"):
        config_from_mapping({"recording": {"max_bytes": -1}})


def test_jwt_without_optional_claims_authenticates_successfully() -> None:
    """Tokens without iat/nbf must be accepted (only sub+exp are required)."""
    config = default_server_config()
    config.auth = _jwt_config()
    app = create_server_app(config)

    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "alice",
            "roles": ["admin"],
            "iss": "undef-terminal",
            "aud": "undef-terminal-server",
            "exp": now + 600,
            # No "iat", no "nbf"
        },
        key=_TEST_SIGNING_KEY,
        algorithm="HS256",
    )

    with TestClient(app) as client:
        r = client.get("/api/sessions", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200


def test_recording_download_rejects_path_outside_recording_dir(tmp_path: Path) -> None:
    """Recording download must return 404 if the resolved path escapes the recordings dir."""
    config = default_server_config()
    config.recording.directory = tmp_path / "recordings"
    config.recording.directory.mkdir()
    app = create_server_app(config)

    # Create a file that exists but lives outside the configured recordings directory.
    outside_file = tmp_path / "evil.jsonl"
    outside_file.write_text("{}\n", encoding="utf-8")

    async def _fake_recording_path(session_id: str) -> Path:
        return outside_file

    with TestClient(app) as client:
        app.state.uterm_registry.recording_path = _fake_recording_path
        r = client.get("/api/sessions/demo-session/recording/download")
        assert r.status_code == 404


def test_ssh_connector_raises_without_known_hosts() -> None:
    """SshSessionConnector must reject a config with no known_hosts and no explicit opt-out."""
    pytest.importorskip("asyncssh", reason="asyncssh not installed")
    from undef.terminal.server.connectors.ssh import SshSessionConnector

    with pytest.raises(ValueError, match="known_hosts"):
        SshSessionConnector("sess1", "Session 1", {"host": "localhost"})


# ---------------------------------------------------------------------------
# Fourth-review regression tests
# ---------------------------------------------------------------------------


def test_create_session_rejects_unknown_connector_type() -> None:
    """POST /api/sessions with an unsupported connector_type must return 422."""
    config = default_server_config()
    app = create_server_app(config)
    with TestClient(app) as client:
        r = client.post(
            "/api/sessions",
            json={"session_id": "bad-type", "display_name": "Bad", "connector_type": "bogus"},
        )
        assert r.status_code == 422


def test_telnet_client_connect_timeout_parameter() -> None:
    """TelnetClient must accept a connect_timeout parameter."""
    from undef.terminal.transports.telnet import TelnetClient

    client = TelnetClient("127.0.0.1", 9, connect_timeout=5.0)
    assert client._connect_timeout == 5.0


def test_set_mode_invalid_value_returns_422() -> None:
    """POST /api/sessions/{id}/mode with invalid input_mode must return 422, not 400."""
    config = default_server_config()
    app = create_server_app(config)
    with TestClient(app) as client:
        r = client.post("/api/sessions/demo-session/mode", json={"input_mode": "garbage"})
        assert r.status_code == 422


def test_recording_download_denied_when_config_absent() -> None:
    """Recording download must return 404 when uterm_config is not set on app state."""
    from pathlib import Path

    config = default_server_config()
    config.recording.directory = Path(".uterm-recordings")
    app = create_server_app(config)

    async def _fake_path(session_id: str) -> Path:
        return config.recording.directory / f"{session_id}.jsonl"

    # Remove uterm_config from state so the containment guard has no reference dir.
    with TestClient(app) as client:
        del app.state.uterm_config
        app.state.uterm_registry.recording_path = _fake_path
        r = client.get("/api/sessions/demo-session/recording/download")
        assert r.status_code == 404


def test_replay_log_speed_clamps_to_maximum(tmp_path: Path) -> None:
    """replay_log speed is clamped to 100.0; absurdly large values don't loop infinitely."""
    import io
    import time

    from undef.terminal.replay.viewer import replay_log

    log = tmp_path / "session.jsonl"
    now = time.time()
    log.write_text(
        f'{{"event": "read", "ts": {now}, "data": {{"screen": "A"}}}}\n'
        f'{{"event": "read", "ts": {now + 60.0}, "data": {{"screen": "B"}}}}\n',
        encoding="utf-8",
    )
    buf = io.StringIO()
    start = time.monotonic()
    replay_log(log, speed=1_000_000.0, output=buf)
    elapsed = time.monotonic() - start
    # At 100× max clamp, a 60 s gap becomes 0.6 s — well under 5 s.
    assert elapsed < 5.0
    assert "B" in buf.getvalue()


def test_session_definition_has_no_last_active_at_field() -> None:
    """SessionDefinition must not expose last_active_at (field removed in fourth review)."""
    from undef.terminal.server.models import SessionDefinition

    sd = SessionDefinition(session_id="s1", display_name="S1", connector_type="demo")
    assert not hasattr(sd, "last_active_at")


def test_ssh_connector_allows_insecure_no_host_check_flag() -> None:
    """insecure_no_host_check=True must bypass the known_hosts requirement with a warning."""
    pytest.importorskip("asyncssh", reason="asyncssh not installed")
    from undef.terminal.server.connectors.ssh import SshSessionConnector

    connector = SshSessionConnector("sess1", "Session 1", {"host": "localhost", "insecure_no_host_check": True})
    assert connector._known_hosts is None


# --- Fifth-review regression tests ---


async def test_ssh_connector_start_passes_connect_timeout() -> None:
    """SshSessionConnector.start() must pass connect_timeout=30 to asyncssh.connect."""
    from unittest.mock import AsyncMock, MagicMock, patch

    pytest.importorskip("asyncssh", reason="asyncssh not installed")
    from undef.terminal.server.connectors.ssh import SshSessionConnector

    connector = SshSessionConnector("sess1", "Session 1", {"host": "localhost", "insecure_no_host_check": True})
    mock_process = MagicMock()
    mock_process.stdin = MagicMock()
    mock_process.stdout = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.create_process = AsyncMock(return_value=mock_process)

    with patch("asyncssh.connect", new_callable=AsyncMock, return_value=mock_conn) as mock_connect:
        await connector.start()
        _, kwargs = mock_connect.call_args
        assert kwargs.get("connect_timeout") == 30


async def test_ssh_connector_handle_input_uses_utf8() -> None:
    """SshSessionConnector.handle_input must encode input as UTF-8, not latin-1."""
    from unittest.mock import AsyncMock, MagicMock

    pytest.importorskip("asyncssh", reason="asyncssh not installed")
    from undef.terminal.server.connectors.ssh import SshSessionConnector

    connector = SshSessionConnector("sess1", "Session 1", {"host": "localhost", "insecure_no_host_check": True})
    mock_stdin = MagicMock()
    mock_stdin.drain = AsyncMock()
    connector._stdin = mock_stdin
    connector._connected = True

    await connector.handle_input("€test")
    written: bytes = mock_stdin.write.call_args[0][0]
    assert written == "€test".encode("utf-8", errors="replace")
    # latin-1 would mangle the euro sign; verify we're not using it
    assert written != "€test".encode("latin-1", errors="replace")


def test_config_from_mapping_rejects_unknown_connector_type() -> None:
    """config_from_mapping must raise ValueError for an unknown connector_type in [[sessions]]."""
    with pytest.raises(ValueError, match="invalid connector_type"):
        config_from_mapping(
            {
                "sessions": [
                    {"session_id": "sess1", "display_name": "S1", "connector_type": "bogus_connector"},
                ]
            }
        )


async def test_bridge_stops_on_permanent_http_error() -> None:
    """TermBridge._run must stop reconnecting on 401/403/404, not back off and retry."""
    from unittest.mock import MagicMock

    from undef.terminal.hijack.bridge import TermBridge

    class FakeStatusError(Exception):
        status_code = 403

    class _FakeCtx:
        async def __aenter__(self) -> None:
            raise FakeStatusError("Forbidden")

        async def __aexit__(self, *_: object) -> None:
            return None

    fake_ws = MagicMock()
    fake_ws.connect = MagicMock(return_value=_FakeCtx())

    bot = MagicMock()
    bot.session = None
    bridge = TermBridge(bot, "worker1", "http://localhost:9999")

    import sys

    real_websockets = sys.modules.pop("websockets", None)
    sys.modules["websockets"] = fake_ws
    try:
        await bridge.start()
        # Poll until the bridge self-stops or we time out.
        for _ in range(50):
            await asyncio.sleep(0.02)
            if not bridge._running:
                break
    finally:
        if real_websockets is not None:
            sys.modules["websockets"] = real_websockets
        else:
            sys.modules.pop("websockets", None)

    assert not bridge._running, "bridge should have stopped after a permanent HTTP error"


def test_hijack_acquire_error_message_says_session_not_worker() -> None:
    """hijack_acquire must return 'for this session', not the previous 'for this worker', in error text."""
    from fastapi import APIRouter

    from undef.terminal.hijack.hub import TermHub
    from undef.terminal.hijack.routes import register_rest_routes

    hub = TermHub()
    router = APIRouter()
    register_rest_routes(hub, router)
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        r = client.post("/worker/no-such-worker/hijack/acquire", json={"owner": "test"})
        assert r.status_code == 409
        body = r.json()
        assert "session" in body["error"].lower()
        assert "this worker" not in body["error"].lower()


# --- Sixth-review regression tests ---


def test_browser_handlers_error_message_says_session_not_worker() -> None:
    """Browser WS hijack error messages must say 'for this session', not 'for this worker'."""
    import undef.terminal.hijack.routes.browser_handlers as bh_module

    source = bh_module.__file__
    assert source is not None
    text = Path(source).read_text(encoding="utf-8")
    assert "for this worker" not in text, "browser_handlers.py still has 'for this worker' in error strings"


async def test_runtime_stops_on_permanent_http_error() -> None:
    """HostedSessionRuntime._run must stop retrying on permanent HTTP 401/403/404."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from undef.terminal.server.models import RecordingConfig, SessionDefinition
    from undef.terminal.server.runtime import HostedSessionRuntime

    session = SessionDefinition(session_id="s1", display_name="S1", connector_type="demo", auto_start=False)
    runtime = HostedSessionRuntime(session, public_base_url="http://localhost:9999", recording=RecordingConfig())

    class FakeStatusError(Exception):
        status_code = 401

    mock_connector = AsyncMock()
    mock_connector.is_connected = MagicMock(return_value=True)
    mock_connector.set_mode = AsyncMock(return_value=[])
    mock_connector.get_snapshot = AsyncMock(return_value={"type": "snapshot", "screen": "", "ts": 0})
    mock_connector.stop = AsyncMock()

    class _FakeCtx:
        async def __aenter__(self) -> None:
            raise FakeStatusError("Unauthorized")

        async def __aexit__(self, *_: object) -> None:
            return None

    fake_ws_mod = MagicMock()
    fake_ws_mod.connect = MagicMock(return_value=_FakeCtx())

    import sys

    real_ws = sys.modules.pop("websockets", None)
    sys.modules["websockets"] = fake_ws_mod
    try:
        with patch("undef.terminal.server.runtime.build_connector", return_value=mock_connector):
            await runtime.start()
            for _ in range(50):
                await asyncio.sleep(0.02)
                if runtime._state == "error" and (runtime._task is None or runtime._task.done()):
                    break
    finally:
        if real_ws is not None:
            sys.modules["websockets"] = real_ws
        else:
            sys.modules.pop("websockets", None)

    # _run() always sets _state="stopped" on exit; verify the task exited early
    # (permanent error) rather than looping, and that _last_error is populated.
    assert runtime._task is not None and runtime._task.done(), (
        "runtime task should have exited after permanent HTTP 401"
    )
    assert runtime._last_error is not None, "last_error should be set after a permanent HTTP failure"


def test_pages_use_state_principal_not_double_resolved(monkeypatch: pytest.MonkeyPatch) -> None:
    """Page routes must use request.state.uterm_principal set by _require_authenticated
    and must not call resolve_http_principal a second time."""
    import undef.terminal.server.routes.pages as pages_module

    call_count = {"n": 0}
    original = pages_module.resolve_http_principal

    def _spy(request: object, auth: object) -> object:
        call_count["n"] += 1
        return original(request, auth)  # type: ignore[arg-type]

    monkeypatch.setattr(pages_module, "resolve_http_principal", _spy)

    config = default_server_config()
    config.auth.mode = "dev"
    app = create_server_app(config)
    with TestClient(app) as client:
        r = client.get(config.ui.app_path + "/")
        assert r.status_code == 200

    # _require_authenticated sets request.state.uterm_principal before page handlers run;
    # page routes must use that value without calling resolve_http_principal again.
    assert call_count["n"] == 0, (
        f"resolve_http_principal called {call_count['n']} time(s) — expected 0 (state principal reused)"
    )
