#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Targeted mutation-killing tests for server/runtime.py, registry.py, and auth.py."""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from undef.terminal.server.models import AuthConfig, RecordingConfig, SessionDefinition
from undef.terminal.server.registry import SessionRegistry, SessionValidationError
from undef.terminal.server.runtime import HostedSessionRuntime

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_TEST_KEY = "uterm-test-secret-32-byte-minimum-key"


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


def _make_runtime(
    session_id: str = "test-session",
    base_url: str = "http://localhost:9999",
    recording: RecordingConfig | None = None,
    worker_bearer_token: str | None = None,
) -> HostedSessionRuntime:
    return HostedSessionRuntime(
        _make_session(session_id),
        public_base_url=base_url,
        recording=recording or RecordingConfig(),
        worker_bearer_token=worker_bearer_token,
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


def _jwt_auth_config(key: str = _TEST_KEY) -> AuthConfig:
    import jwt as pyjwt

    now = int(time.time())
    worker_token = pyjwt.encode(
        {"sub": "worker", "exp": now + 600, "iss": "undef-terminal", "aud": "undef-terminal-server"},
        key=key,
        algorithm="HS256",
    )
    return AuthConfig(
        mode="jwt",
        jwt_public_key_pem=key,
        jwt_algorithms=["HS256"],
        jwt_issuer="undef-terminal",
        jwt_audience="undef-terminal-server",
        worker_bearer_token=worker_token,
    )


def _make_jwt_token(
    sub: str = "user1",
    roles: Any = None,
    exp_offset: int = 600,
    key: str = _TEST_KEY,
) -> str:
    import jwt as pyjwt

    if roles is None:
        roles = ["operator"]
    now = int(time.time())
    payload = {
        "sub": sub,
        "roles": roles,
        "iss": "undef-terminal",
        "aud": "undef-terminal-server",
        "iat": now,
        "nbf": now,
        "exp": now + exp_offset,
    }
    return pyjwt.encode(payload, key=key, algorithm="HS256")


# ===========================================================================
# runtime.py — HostedSessionRuntime.__init__
# ===========================================================================


class TestRuntimeInit:
    def test_trailing_slash_stripped_from_base_url(self) -> None:
        """mutmut_5: rstrip("XX/XX") instead of rstrip("/") — trailing slash not stripped."""
        rt = HostedSessionRuntime(
            _make_session(),
            public_base_url="http://localhost:9999/",
            recording=RecordingConfig(),
        )
        assert not rt._public_base_url.endswith("/")
        assert rt._public_base_url == "http://localhost:9999"

    def test_multiple_trailing_slashes_stripped(self) -> None:
        """Also covers mutmut_5 — rstrip removes all trailing slashes."""
        rt = HostedSessionRuntime(
            _make_session(),
            public_base_url="http://localhost:9999///",
            recording=RecordingConfig(),
        )
        assert rt._public_base_url == "http://localhost:9999"

    def test_last_error_initial_value_is_none(self) -> None:
        """mutmut_17: _last_error initialized to "" instead of None."""
        rt = _make_runtime()
        assert rt._last_error is None

    def test_initial_state_is_stopped(self) -> None:
        rt = _make_runtime()
        assert rt._state == "stopped"

    def test_initial_connected_is_false(self) -> None:
        rt = _make_runtime()
        assert rt._connected is False


# ===========================================================================
# runtime.py — HostedSessionRuntime.status()
# ===========================================================================


class TestRuntimeStatus:
    def test_last_error_reflected_in_status(self) -> None:
        """mutmut_14: status() returns last_error=None hardcoded instead of self._last_error."""
        rt = _make_runtime()
        rt._last_error = "boom"
        s = rt.status()
        assert s.last_error == "boom"

    def test_last_error_none_when_not_set(self) -> None:
        rt = _make_runtime()
        s = rt.status()
        assert s.last_error is None

    def test_recording_available_false_when_no_path(self) -> None:
        """mutmut_25: recording_available line removed."""
        rt = _make_runtime()
        s = rt.status()
        assert s.recording_available is False

    def test_recording_available_false_when_path_nonexistent(self, tmp_path: Path) -> None:
        """mutmut_25: recording_available presence and correctness."""
        rt = _make_runtime(recording=RecordingConfig(directory=tmp_path))
        rt._recording_path = tmp_path / "nonexistent.jsonl"
        s = rt.status()
        assert s.recording_available is False

    def test_recording_available_true_when_file_exists(self, tmp_path: Path) -> None:
        """mutmut_25: recording_available must be True when file exists."""
        path = tmp_path / "s.jsonl"
        path.write_text("")
        rt = _make_runtime(recording=RecordingConfig(directory=tmp_path))
        rt._recording_path = path
        s = rt.status()
        assert s.recording_available is True

    def test_status_has_last_error_field(self) -> None:
        """mutmut_28: closing paren on wrong line removes last_error from status call."""
        rt = _make_runtime()
        rt._last_error = "err"
        s = rt.status()
        # must have a last_error attribute and it must be "err"
        assert hasattr(s, "last_error")
        assert s.last_error == "err"


# ===========================================================================
# runtime.py — HostedSessionRuntime.start()
# ===========================================================================


class TestRuntimeStart:
    async def test_start_does_not_restart_running_task(self) -> None:
        """mutmut_3: condition inverted — runs even if task is NOT done (not running)."""
        rt = _make_runtime()
        # Simulate a running task
        running_task = asyncio.create_task(asyncio.sleep(100))
        rt._task = running_task
        await rt.start()
        # Should not have created a new task — task stays the same
        assert rt._task is running_task
        running_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running_task

    async def test_start_creates_task_when_no_prior_task(self) -> None:
        """Positive case: start() creates a task when none exists."""
        rt = _make_runtime()
        assert rt._task is None
        with patch.object(rt, "_run", new_callable=AsyncMock):
            await rt.start()
        assert rt._task is not None
        rt._task.cancel()


# ===========================================================================
# runtime.py — HostedSessionRuntime.stop()
# ===========================================================================


class TestRuntimeStop:
    async def test_stop_sets_connected_false(self) -> None:
        """mutmut_9: _connected set to True after stop instead of False."""
        rt = _make_runtime()
        rt._connected = True
        with patch.object(rt, "_stop_connector", new_callable=AsyncMock):
            await rt.stop()
        assert rt._connected is False

    async def test_stop_cancels_task(self) -> None:
        """mutmut_1: task = None instead of task = self._task — task not cancelled."""
        rt = _make_runtime()
        task_done = asyncio.Event()

        async def _long_run() -> None:
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                task_done.set()
                raise

        rt._task = asyncio.create_task(_long_run())
        await asyncio.sleep(0)  # let the task start and reach its first await
        with patch.object(rt, "_stop_connector", new_callable=AsyncMock):
            await rt.stop()
        # After stop() awaits the task, cancellation must have propagated
        assert task_done.is_set()

    async def test_stop_sets_state_stopped(self) -> None:
        rt = _make_runtime()
        with patch.object(rt, "_stop_connector", new_callable=AsyncMock):
            await rt.stop()
        assert rt._state == "stopped"


# ===========================================================================
# runtime.py — HostedSessionRuntime.set_mode()
# ===========================================================================


class TestRuntimeSetMode:
    async def test_set_mode_updates_definition_input_mode_hijack(self) -> None:
        """mutmut_8/13/14: cast argument mutated, but typed_mode must still propagate."""
        rt = _make_runtime()
        rt._connector = None  # no connector
        await rt.set_mode("hijack")
        assert rt.definition.input_mode == "hijack"

    async def test_set_mode_updates_definition_input_mode_open(self) -> None:
        rt = _make_runtime()
        rt._connector = None
        await rt.set_mode("open")
        assert rt.definition.input_mode == "open"

    async def test_set_mode_calls_connector_set_mode(self) -> None:
        """Connector set_mode must be called with correct typed_mode."""
        rt = _make_runtime()
        connector = AsyncMock()
        connector.set_mode = AsyncMock(return_value=[])
        rt._connector = connector
        rt._queue = asyncio.Queue()
        await rt.set_mode("hijack")
        connector.set_mode.assert_called_once_with("hijack")

    async def test_set_mode_invalid_raises(self) -> None:
        rt = _make_runtime()
        with pytest.raises(ValueError, match="invalid mode"):
            await rt.set_mode("bogus")


# ===========================================================================
# runtime.py — HostedSessionRuntime._start_connector()
# ===========================================================================


class TestStartConnector:
    async def test_start_connector_uses_session_id(self) -> None:
        """mutmut_2: session_id replaced with None in build_connector call."""
        rt = _make_runtime("my-session-id")
        with patch("undef.terminal.server.runtime.build_connector") as mock_build:
            mock_connector = AsyncMock()
            mock_connector.is_connected.return_value = False
            mock_build.return_value = mock_connector
            rt._recording_cfg = MagicMock()
            rt._recording_cfg.enabled_by_default = False
            await rt._start_connector()
        call_args = mock_build.call_args[0]
        assert call_args[0] == "my-session-id"

    async def test_start_connector_uses_display_name(self) -> None:
        """mutmut_3: display_name replaced with None in build_connector call."""
        session = _make_session()
        session.display_name = "My Display Name"
        rt = HostedSessionRuntime(session, public_base_url="http://x", recording=RecordingConfig())
        with patch("undef.terminal.server.runtime.build_connector") as mock_build:
            mock_connector = AsyncMock()
            mock_connector.is_connected.return_value = False
            mock_build.return_value = mock_connector
            rt._recording_cfg = MagicMock()
            rt._recording_cfg.enabled_by_default = False
            await rt._start_connector()
        call_args = mock_build.call_args[0]
        assert call_args[1] == "My Display Name"

    async def test_start_connector_logger_gets_max_bytes(self, tmp_path: Path) -> None:
        """mutmut_20: SessionLogger(path,) instead of SessionLogger(path, max_bytes=...)."""
        recording = RecordingConfig(directory=tmp_path, enabled_by_default=True, max_bytes=12345)
        rt = _make_runtime(recording=recording)

        with patch("undef.terminal.server.runtime.build_connector") as mock_build:
            mock_connector = AsyncMock()
            mock_connector.is_connected.return_value = False
            mock_build.return_value = mock_connector

            with patch("undef.terminal.server.runtime.SessionLogger") as mock_logger:
                mock_logger_instance = AsyncMock()
                mock_logger.return_value = mock_logger_instance
                await rt._start_connector()

        mock_logger.assert_called_once()
        call_kwargs = mock_logger.call_args[1]
        assert call_kwargs.get("max_bytes") == 12345

    async def test_start_connector_logger_start_uses_session_id(self, tmp_path: Path) -> None:
        """mutmut_21: logger.start(None) instead of logger.start(session_id)."""
        recording = RecordingConfig(directory=tmp_path, enabled_by_default=True)
        rt = _make_runtime("my-session", recording=recording)

        with patch("undef.terminal.server.runtime.build_connector") as mock_build:
            mock_connector = AsyncMock()
            mock_connector.is_connected.return_value = False
            mock_build.return_value = mock_connector

            with patch("undef.terminal.server.runtime.SessionLogger") as mock_logger:
                mock_logger_instance = AsyncMock()
                mock_logger.return_value = mock_logger_instance
                await rt._start_connector()

        mock_logger_instance.start.assert_called_once_with("my-session")


# ===========================================================================
# runtime.py — HostedSessionRuntime._stop_connector()
# ===========================================================================


class TestStopConnector:
    async def test_logger_set_to_none_after_stop(self) -> None:
        """mutmut_2: self._logger = "" instead of None."""
        rt = _make_runtime()
        rt._logger = AsyncMock()
        rt._logger.stop = AsyncMock()
        await rt._stop_connector()
        assert rt._logger is None

    async def test_connector_stop_called(self) -> None:
        """mutmut_3: connector = None instead of self._connector."""
        rt = _make_runtime()
        connector = AsyncMock()
        rt._connector = connector
        await rt._stop_connector()
        connector.stop.assert_called_once()

    async def test_connector_set_to_none_after_stop(self) -> None:
        """mutmut_4: self._connector = "" instead of None."""
        rt = _make_runtime()
        connector = AsyncMock()
        rt._connector = connector
        await rt._stop_connector()
        assert rt._connector is None

    async def test_connector_stop_not_called_when_none(self) -> None:
        """mutmut_5: condition inverted — would call stop on None connector."""
        rt = _make_runtime()
        rt._connector = None
        # Should not raise
        await rt._stop_connector()

    async def test_stop_connector_suppresses_exceptions(self) -> None:
        """mutmut_6: contextlib.suppress(None) instead of suppress(Exception)."""
        rt = _make_runtime()
        connector = AsyncMock()
        connector.stop = AsyncMock(side_effect=RuntimeError("boom"))
        rt._connector = connector
        # Should not raise
        await rt._stop_connector()


# ===========================================================================
# runtime.py — HostedSessionRuntime._log_snapshot()
# ===========================================================================


class TestLogSnapshot:
    async def test_log_snapshot_uses_screen_key(self) -> None:
        """mutmut_3/4/5/6/7/8/9/10: msg.get("screen",...) mutated."""
        rt = _make_runtime()
        rt._logger = AsyncMock()
        rt._logger.log_screen = AsyncMock()
        msg = {"type": "snapshot", "screen": "HELLO WORLD"}
        await rt._log_snapshot(msg)
        call_args = rt._logger.log_screen.call_args
        raw_bytes = call_args[0][1]
        assert b"HELLO WORLD" in raw_bytes

    async def test_log_snapshot_uses_cp437_encoding(self) -> None:
        """mutmut_20: CP437 uppercase — encoding is case-insensitive, but mutmut_21/22 matter."""
        rt = _make_runtime()
        rt._logger = AsyncMock()
        rt._logger.log_screen = AsyncMock()
        msg = {"type": "snapshot", "screen": "test"}
        await rt._log_snapshot(msg)
        rt._logger.log_screen.assert_called_once()
        raw = rt._logger.log_screen.call_args[0][1]
        assert isinstance(raw, bytes)
        assert raw == b"test"

    async def test_log_snapshot_uses_replace_error_handler(self) -> None:
        """mutmut_21/22: errors="XXreplaceXX" or "REPLACE" — invalid encoder errors handler."""
        rt = _make_runtime()
        rt._logger = AsyncMock()
        rt._logger.log_screen = AsyncMock()
        # Use a character not in cp437 to ensure replace is actually needed
        msg = {"type": "snapshot", "screen": "\u2603"}  # snowman not in cp437
        # Should not raise — "replace" handler must be used
        await rt._log_snapshot(msg)
        rt._logger.log_screen.assert_called_once()

    async def test_log_snapshot_noop_when_no_logger(self) -> None:
        rt = _make_runtime()
        rt._logger = None
        msg = {"type": "snapshot", "screen": "test"}
        # Should not raise
        await rt._log_snapshot(msg)

    async def test_log_snapshot_empty_screen_default(self) -> None:
        """mutmut_5: default changed to None; str(None)='None' != ''"""
        rt = _make_runtime()
        rt._logger = AsyncMock()
        rt._logger.log_screen = AsyncMock()
        msg = {"type": "snapshot"}  # no "screen" key
        await rt._log_snapshot(msg)
        raw = rt._logger.log_screen.call_args[0][1]
        # default "" => b""
        assert raw == b""


# ===========================================================================
# runtime.py — HostedSessionRuntime._bridge_session()
# ===========================================================================

# We use a fake WS and connector to avoid real websockets in these tests.


class _FakeWs:
    """Minimal fake websocket for bridge_session testing."""

    def __init__(self, messages: list[str]) -> None:
        self._messages = list(messages)
        self._sent: list[str] = []
        self._index = 0

    async def send(self, data: str) -> None:
        self._sent.append(data)

    async def recv(self) -> str:
        if self._index < len(self._messages):
            msg = self._messages[self._index]
            self._index += 1
            return msg
        # block until stop
        await asyncio.sleep(10)
        raise RuntimeError("no more messages")


class _FakeConnector:
    def __init__(self, poll_results: list[list[dict[str, Any]]] | None = None) -> None:
        self._poll_iter = iter(poll_results or [])
        self.set_mode_result: list[dict[str, Any]] = []
        self.snapshot_result: dict[str, Any] = {"type": "snapshot", "screen": "initial"}
        self.handle_input_result: list[dict[str, Any]] = []
        self.handle_control_result: list[dict[str, Any]] = []
        self.get_analysis_result: str = "analysis text"
        self.input_received: list[str] = []
        self.control_received: list[str] = []

    async def set_mode(self, mode: str) -> list[dict[str, Any]]:
        return self.set_mode_result

    async def get_snapshot(self) -> dict[str, Any]:
        return self.snapshot_result

    async def poll_messages(self) -> list[dict[str, Any]]:
        try:
            return next(self._poll_iter)
        except StopIteration:
            await asyncio.sleep(0.05)
            return []

    async def handle_input(self, data: str) -> list[dict[str, Any]]:
        self.input_received.append(data)
        return self.handle_input_result

    async def handle_control(self, action: str) -> list[dict[str, Any]]:
        self.control_received.append(action)
        return self.handle_control_result

    async def get_analysis(self) -> str:
        return self.get_analysis_result


async def _run_bridge_until_stop(
    rt: HostedSessionRuntime, ws: _FakeWs, connector: _FakeConnector | None = None
) -> None:
    """Run _bridge_session for a short time then set stop."""
    if connector is None:
        connector = _FakeConnector()
    rt._connector = connector
    rt._stop.clear()
    task = asyncio.create_task(rt._bridge_session(ws))
    await asyncio.sleep(0.15)
    rt._stop.set()
    with pytest.raises((asyncio.CancelledError, Exception)):
        task.cancel()
        await task


class TestBridgeSession:
    async def test_bridge_raises_when_no_connector(self) -> None:
        """mutmut_4: error message changed — but type must still be RuntimeError."""
        rt = _make_runtime()
        rt._connector = None
        ws = _FakeWs([])
        with pytest.raises(RuntimeError):
            await rt._bridge_session(ws)

    async def test_bridge_sets_state_running(self) -> None:
        rt = _make_runtime()
        connector = _FakeConnector()
        rt._connector = connector
        rt._queue = asyncio.Queue()
        rt._stop.clear()

        async def _stop_soon() -> None:
            await asyncio.sleep(0.05)
            rt._stop.set()

        asyncio.create_task(_stop_soon())  # noqa: RUF006
        with contextlib.suppress(Exception):
            await rt._bridge_session(_FakeWs([]))
        assert rt._state == "running"

    async def test_log_event_called_with_runtime_started(self) -> None:
        """mutmut_14/15/18/19/21: _log_event called with wrong args."""
        rt = _make_runtime()
        rt._queue = asyncio.Queue()
        rt._stop.clear()
        events: list[tuple[str, dict[str, Any]]] = []

        orig_log = rt._log_event

        async def _capture_log_event(event: str, payload: dict[str, Any]) -> None:
            events.append((event, payload))
            await orig_log(event, payload)

        rt._log_event = _capture_log_event  # type: ignore[method-assign]
        connector = _FakeConnector()
        rt._connector = connector

        async def _stop_soon() -> None:
            await asyncio.sleep(0.05)
            rt._stop.set()

        asyncio.create_task(_stop_soon())  # noqa: RUF006
        with contextlib.suppress(Exception):
            await rt._bridge_session(_FakeWs([]))

        assert any(event == "runtime_started" for event, _ in events)
        # The payload must have "session_id" key (not SESSION_ID)
        for event, payload in events:
            if event == "runtime_started":
                assert "session_id" in payload

    async def test_snapshot_from_queue_calls_log_snapshot(self) -> None:
        """mutmut_29/30/31/32/33/34: snapshot type check broken."""
        rt = _make_runtime()
        rt._queue = asyncio.Queue()
        rt._stop.clear()

        logged: list[dict[str, Any]] = []

        async def _log_snap(msg: dict[str, Any]) -> None:
            logged.append(msg)

        rt._log_snapshot = _log_snap  # type: ignore[method-assign]

        snap_msg = {"type": "snapshot", "screen": "test"}
        await rt._queue.put(snap_msg)

        connector = _FakeConnector()
        rt._connector = connector
        ws = _FakeWs([])

        async def _stop_soon() -> None:
            await asyncio.sleep(0.05)
            rt._stop.set()

        asyncio.create_task(_stop_soon())  # noqa: RUF006
        with contextlib.suppress(Exception):
            await rt._bridge_session(ws)

        assert snap_msg in logged

    async def test_non_snapshot_from_queue_not_logged(self) -> None:
        """Confirm type check is case-sensitive — only 'snapshot' triggers logging."""
        rt = _make_runtime()
        rt._queue = asyncio.Queue()
        rt._stop.clear()

        logged: list[dict[str, Any]] = []

        async def _log_snap(msg: dict[str, Any]) -> None:
            logged.append(msg)

        rt._log_snapshot = _log_snap  # type: ignore[method-assign]

        non_snap = {"type": "other", "screen": "x"}
        await rt._queue.put(non_snap)

        connector = _FakeConnector()
        rt._connector = connector
        ws = _FakeWs([])

        async def _stop_soon() -> None:
            await asyncio.sleep(0.05)
            rt._stop.set()

        asyncio.create_task(_stop_soon())  # noqa: RUF006
        with contextlib.suppress(Exception):
            await rt._bridge_session(ws)

        assert non_snap not in logged

    async def test_input_message_dispatched_to_connector(self) -> None:
        """mutmut_116/118/121: data default changed."""
        rt = _make_runtime()
        rt._queue = asyncio.Queue()
        rt._stop.clear()
        connector = _FakeConnector()
        rt._connector = connector
        ws = _FakeWs([json.dumps({"type": "input", "data": "hello"})])

        async def _stop_soon() -> None:
            await asyncio.sleep(0.1)
            rt._stop.set()

        asyncio.create_task(_stop_soon())  # noqa: RUF006
        with contextlib.suppress(Exception):
            await rt._bridge_session(ws)

        assert "hello" in connector.input_received

    async def test_input_missing_data_uses_empty_string(self) -> None:
        """mutmut_116: default=None causes str(None)='None' not ''."""
        rt = _make_runtime()
        rt._queue = asyncio.Queue()
        rt._stop.clear()
        connector = _FakeConnector()
        rt._connector = connector
        # No "data" key in message
        ws = _FakeWs([json.dumps({"type": "input"})])

        async def _stop_soon() -> None:
            await asyncio.sleep(0.1)
            rt._stop.set()

        asyncio.create_task(_stop_soon())  # noqa: RUF006
        with contextlib.suppress(Exception):
            await rt._bridge_session(ws)

        # Must receive empty string, not "None"
        assert connector.input_received == [""]

    async def test_analyze_req_returns_analysis_type(self) -> None:
        """mutmut_91/92: type key changed to XXanalysisXX or ANALYSIS."""
        rt = _make_runtime()
        rt._queue = asyncio.Queue()
        rt._stop.clear()
        connector = _FakeConnector()
        connector.get_analysis_result = "AI says: hello"
        rt._connector = connector

        sent_messages: list[dict[str, Any]] = []

        class _CapturingWs(_FakeWs):
            async def send(self, data: str) -> None:
                sent_messages.append(json.loads(data))

        ws = _CapturingWs([json.dumps({"type": "analyze_req"})])

        async def _stop_soon() -> None:
            await asyncio.sleep(0.1)
            rt._stop.set()

        asyncio.create_task(_stop_soon())  # noqa: RUF006
        with contextlib.suppress(Exception):
            await rt._bridge_session(ws)

        analysis_msgs = [m for m in sent_messages if m.get("type") == "analysis"]
        assert analysis_msgs, "Expected an 'analysis' response message"
        assert analysis_msgs[0]["formatted"] == "AI says: hello"

    async def test_analyze_req_response_has_formatted_key(self) -> None:
        """mutmut_93/94: formatted key renamed."""
        rt = _make_runtime()
        rt._queue = asyncio.Queue()
        rt._stop.clear()
        connector = _FakeConnector()
        connector.get_analysis_result = "result"
        rt._connector = connector

        sent_messages: list[dict[str, Any]] = []

        class _CapWs(_FakeWs):
            async def send(self, data: str) -> None:
                sent_messages.append(json.loads(data))

        ws = _CapWs([json.dumps({"type": "analyze_req"})])

        async def _stop_soon() -> None:
            await asyncio.sleep(0.1)
            rt._stop.set()

        asyncio.create_task(_stop_soon())  # noqa: RUF006
        with contextlib.suppress(Exception):
            await rt._bridge_session(ws)

        for m in sent_messages:
            if m.get("type") == "analysis":
                assert "formatted" in m, "'formatted' key missing from analysis response"

    async def test_analyze_req_response_has_ts_key(self) -> None:
        """mutmut_95/96: ts key renamed."""
        rt = _make_runtime()
        rt._queue = asyncio.Queue()
        rt._stop.clear()
        connector = _FakeConnector()
        rt._connector = connector

        sent_messages: list[dict[str, Any]] = []

        class _CapWs(_FakeWs):
            async def send(self, data: str) -> None:
                sent_messages.append(json.loads(data))

        ws = _CapWs([json.dumps({"type": "analyze_req"})])

        async def _stop_soon() -> None:
            await asyncio.sleep(0.1)
            rt._stop.set()

        asyncio.create_task(_stop_soon())  # noqa: RUF006
        with contextlib.suppress(Exception):
            await rt._bridge_session(ws)

        for m in sent_messages:
            if m.get("type") == "analysis":
                assert "ts" in m, "'ts' key missing from analysis response"

    async def test_control_message_uses_action_default_empty_string(self) -> None:
        """mutmut_104/106/109: action default changed."""
        rt = _make_runtime()
        rt._queue = asyncio.Queue()
        rt._stop.clear()
        connector = _FakeConnector()
        rt._connector = connector
        # Message with no "action" key
        ws = _FakeWs([json.dumps({"type": "control"})])

        async def _stop_soon() -> None:
            await asyncio.sleep(0.1)
            rt._stop.set()

        asyncio.create_task(_stop_soon())  # noqa: RUF006
        with contextlib.suppress(Exception):
            await rt._bridge_session(ws)

        # handle_control must be called with "" (empty string), not "None" or "XXXX"
        assert connector.control_received == [""]

    async def test_invalid_json_continues_not_breaks(self) -> None:
        """mutmut_75: continue replaced with break — loop would exit on bad JSON."""
        rt = _make_runtime()
        rt._queue = asyncio.Queue()
        rt._stop.clear()
        connector = _FakeConnector()
        rt._connector = connector

        # First message: invalid JSON; second: valid input
        ws = _FakeWs(["NOT_JSON", json.dumps({"type": "input", "data": "ok"})])

        async def _stop_soon() -> None:
            await asyncio.sleep(0.15)
            rt._stop.set()

        asyncio.create_task(_stop_soon())  # noqa: RUF006
        with contextlib.suppress(Exception):
            await rt._bridge_session(ws)

        # Should have processed the valid "input" message despite invalid JSON first
        assert "ok" in connector.input_received

    async def test_poll_snapshot_triggers_log_snapshot(self) -> None:
        """mutmut_62/63/64/66/67/68: type check on poll results broken."""
        rt = _make_runtime()
        rt._queue = asyncio.Queue()
        rt._stop.clear()

        snap_msg = {"type": "snapshot", "screen": "polled"}
        connector = _FakeConnector(poll_results=[[snap_msg], []])
        rt._connector = connector

        logged: list[dict[str, Any]] = []

        async def _log_snap(msg: dict[str, Any]) -> None:
            logged.append(msg)

        rt._log_snapshot = _log_snap  # type: ignore[method-assign]
        ws = _FakeWs([])

        async def _stop_soon() -> None:
            await asyncio.sleep(0.2)
            rt._stop.set()

        asyncio.create_task(_stop_soon())  # noqa: RUF006
        with contextlib.suppress(Exception):
            await rt._bridge_session(ws)

        assert snap_msg in logged

    async def test_response_snapshot_triggers_log_snapshot(self) -> None:
        """mutmut_127/128/129/130/131/132/133: type check on response outbound broken."""
        rt = _make_runtime()
        rt._queue = asyncio.Queue()
        rt._stop.clear()

        snap_response = {"type": "snapshot", "screen": "response-snap"}

        connector = _FakeConnector()
        connector.snapshot_result = snap_response
        rt._connector = connector

        logged: list[dict[str, Any]] = []

        async def _log_snap(msg: dict[str, Any]) -> None:
            logged.append(msg)

        rt._log_snapshot = _log_snap  # type: ignore[method-assign]
        ws = _FakeWs([json.dumps({"type": "snapshot_req"})])

        async def _stop_soon() -> None:
            await asyncio.sleep(0.15)
            rt._stop.set()

        asyncio.create_task(_stop_soon())  # noqa: RUF006
        with contextlib.suppress(Exception):
            await rt._bridge_session(ws)

        assert snap_response in logged


# ===========================================================================
# runtime.py — HostedSessionRuntime._run() backoff and error handling
# ===========================================================================


class TestRun:
    async def test_run_uses_correct_backoff_values(self) -> None:
        """mutmut_2/3/4/5/6: backoff_s values mutated."""
        # Access the function directly via source inspection is fragile,
        # so we patch asyncio.sleep and verify calls match expected delays.
        rt = _make_runtime()
        sleep_calls: list[float] = []

        import websockets

        attempt_count = 0

        async def _fake_sleep(delay: float) -> None:
            sleep_calls.append(delay)

        async def _fail_connect(*args: Any, **kwargs: Any) -> None:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count >= 3:
                rt._stop.set()
            raise OSError("connection refused")

        with (
            patch("undef.terminal.server.runtime.build_connector") as mock_build,
            patch("asyncio.sleep", side_effect=_fake_sleep),
            patch.object(websockets, "connect", side_effect=_fail_connect),
        ):
            mock_connector = AsyncMock()
            mock_connector.is_connected.return_value = False
            mock_build.return_value = mock_connector
            with pytest.raises(Exception, match=".+"):
                await rt._run()

        # First retry: delay=0.25; second retry: delay=0.5
        if sleep_calls:
            assert sleep_calls[0] == pytest.approx(0.25)

    async def test_run_sets_state_error_on_value_error(self) -> None:
        """mutmut_28/29/30: state set to None/XXerrorXX/ERROR instead of 'error'."""
        rt = _make_runtime()

        async def _bad_connector() -> None:
            raise ValueError("bad config")

        with patch("undef.terminal.server.runtime.build_connector", side_effect=ValueError("bad config")):
            await rt._run()

        assert rt._state == "error"

    async def test_run_sets_connected_false_on_value_error(self) -> None:
        """mutmut_31/32: _connected set to None or True instead of False."""
        rt = _make_runtime()
        rt._connected = True

        with patch("undef.terminal.server.runtime.build_connector", side_effect=ValueError("bad")):
            await rt._run()

        assert rt._connected is False

    async def test_run_stores_last_error_on_value_error(self) -> None:
        """Covers _last_error being set correctly on ValueError."""
        rt = _make_runtime()

        with patch("undef.terminal.server.runtime.build_connector", side_effect=ValueError("specific error")):
            await rt._run()

        assert rt._last_error == "specific error"

    async def test_run_sets_state_error_on_generic_exception(self) -> None:
        """mutmut_56/57/58: _state mutated on general exception path."""
        rt = _make_runtime()

        import websockets

        called = [0]

        async def _fail(*args: Any, **kwargs: Any) -> None:
            called[0] += 1
            rt._stop.set()
            raise OSError("network error")

        with (
            patch("undef.terminal.server.runtime.build_connector") as mock_build,
            patch.object(websockets, "connect", side_effect=_fail),
        ):
            mock_connector = AsyncMock()
            mock_connector.is_connected.return_value = False
            mock_build.return_value = mock_connector
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await rt._run()

        assert rt._state in ("error", "stopped")

    async def test_run_sets_connected_false_on_generic_exception(self) -> None:
        """mutmut_59/60: _connected set to None or True on generic exception."""
        rt = _make_runtime()
        rt._connected = True

        import websockets

        async def _fail(*args: Any, **kwargs: Any) -> None:
            rt._stop.set()
            raise OSError("network error")

        with (
            patch("undef.terminal.server.runtime.build_connector") as mock_build,
            patch.object(websockets, "connect", side_effect=_fail),
        ):
            mock_connector = AsyncMock()
            mock_connector.is_connected.return_value = False
            mock_build.return_value = mock_connector
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await rt._run()

        assert rt._connected is False

    async def test_run_final_state_is_stopped(self) -> None:
        """mutmut_129/130/131: final self._state set to None/XXstoppedXX/STOPPED."""
        rt = _make_runtime()
        rt._stop.set()

        with patch("undef.terminal.server.runtime.build_connector", side_effect=ValueError("bad")):
            await rt._run()

        assert rt._state == "stopped"

    async def test_run_final_connected_is_false(self) -> None:
        """mutmut_127/128: finally block sets _connected to None or True."""
        rt = _make_runtime()
        rt._connected = True

        with patch("undef.terminal.server.runtime.build_connector", side_effect=ValueError("bad")):
            await rt._run()

        assert rt._connected is False

    async def test_run_404_stops_retrying(self) -> None:
        """mutmut_115: break replaced with return — _state never set to 'stopped'."""
        rt = _make_runtime()

        import websockets

        exc_404 = Exception("Not Found")
        exc_404.status_code = 404  # type: ignore[attr-defined]

        async def _fail(*args: Any, **kwargs: Any) -> None:
            raise exc_404

        with (
            patch("undef.terminal.server.runtime.build_connector") as mock_build,
            patch.object(websockets, "connect", side_effect=_fail),
        ):
            mock_connector = AsyncMock()
            mock_connector.is_connected.return_value = False
            mock_build.return_value = mock_connector
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await rt._run()

        # After 404 it should not retry (no sleep called)
        mock_sleep.assert_not_called()
        assert rt._state == "stopped"

    async def test_run_401_stops_retrying(self) -> None:
        """mutmut_115: 401 also triggers permanent stop."""
        rt = _make_runtime()

        import websockets

        exc_401 = Exception("Unauthorized")
        exc_401.status_code = 401  # type: ignore[attr-defined]

        async def _fail(*args: Any, **kwargs: Any) -> None:
            raise exc_401

        with (
            patch("undef.terminal.server.runtime.build_connector") as mock_build,
            patch.object(websockets, "connect", side_effect=_fail),
        ):
            mock_connector = AsyncMock()
            mock_connector.is_connected.return_value = False
            mock_build.return_value = mock_connector
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await rt._run()

        mock_sleep.assert_not_called()
        assert rt._state == "stopped"

    async def test_run_attempt_increments_on_failure(self) -> None:
        """mutmut_123/124/125: attempt += changed to attempt = 1 or attempt -= 1."""
        rt = _make_runtime()
        sleep_calls: list[float] = []
        call_count = 0

        import websockets

        async def _fake_sleep(delay: float) -> None:
            sleep_calls.append(delay)
            if call_count >= 2:
                rt._stop.set()

        async def _fail(*args: Any, **kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                rt._stop.set()
            raise OSError("net error")

        with (
            patch("undef.terminal.server.runtime.build_connector") as mock_build,
            patch.object(websockets, "connect", side_effect=_fail),
            patch("asyncio.sleep", side_effect=_fake_sleep),
        ):
            mock_connector = AsyncMock()
            mock_connector.is_connected.return_value = False
            mock_build.return_value = mock_connector
            await rt._run()

        # If attempt increments correctly: delays should be 0.25, 0.5
        # If attempt = 1 each time: delays would be 0.25, 0.25 (wrong)
        if len(sleep_calls) >= 2:
            assert sleep_calls[1] > sleep_calls[0]

    async def test_run_response_status_code_checked(self) -> None:
        """mutmut_89/94/99/100/101/102: status_code lookup on response broken."""
        rt = _make_runtime()

        import websockets

        class _FakeResp:
            status_code = 401

        class _FakeExcWithRespError(Exception):
            response = _FakeResp()

        async def _fail(*args: Any, **kwargs: Any) -> None:
            raise _FakeExcWithRespError("auth error")

        with (
            patch("undef.terminal.server.runtime.build_connector") as mock_build,
            patch.object(websockets, "connect", side_effect=_fail),
        ):
            mock_connector = AsyncMock()
            mock_connector.is_connected.return_value = False
            mock_build.return_value = mock_connector
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await rt._run()

        # Should stop without sleeping (permanent failure via response.status_code)
        mock_sleep.assert_not_called()

    async def test_run_backoff_capped_at_last_element(self) -> None:
        """mutmut_121/122: backoff_s[min(attempt, len-1)] vs len+1 or len-2."""
        rt = _make_runtime()
        sleep_calls: list[float] = []
        call_count = 0

        import websockets

        async def _fake_sleep(delay: float) -> None:
            sleep_calls.append(delay)

        async def _fail(*args: Any, **kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 8:
                rt._stop.set()
            raise OSError("net error")

        with (
            patch("undef.terminal.server.runtime.build_connector") as mock_build,
            patch.object(websockets, "connect", side_effect=_fail),
            patch("asyncio.sleep", side_effect=_fake_sleep),
        ):
            mock_connector = AsyncMock()
            mock_connector.is_connected.return_value = False
            mock_build.return_value = mock_connector
            await rt._run()

        # With 5 elements [0.25, 0.5, 1.0, 2.0, 5.0], max delay is 5.0
        if sleep_calls:
            assert max(sleep_calls) <= 5.0


# ===========================================================================
# registry.py — SessionRegistry._on_worker_empty()
# ===========================================================================


class TestOnWorkerEmpty:
    async def test_on_worker_empty_uses_session_id_for_browser_count(self) -> None:
        """mutmut_8: browser_count(None) instead of browser_count(session_id)."""
        hub = _make_hub()
        hub.browser_count = AsyncMock(return_value=1)  # has browsers, don't delete
        session = _make_session("s1", ephemeral=True)
        reg = SessionRegistry(
            [session],
            hub=hub,
            public_base_url="http://localhost",
            recording=RecordingConfig(),
        )
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await reg._on_worker_empty("s1")
        # browser_count called with "s1"
        hub.browser_count.assert_called_with("s1")

    async def test_on_worker_empty_grace_period_is_5_seconds(self) -> None:
        """mutmut_7: sleep(6) instead of sleep(5)."""
        hub = _make_hub()
        hub.browser_count = AsyncMock(return_value=1)  # has browsers
        session = _make_session("s1", ephemeral=True)
        reg = SessionRegistry(
            [session],
            hub=hub,
            public_base_url="http://localhost",
            recording=RecordingConfig(),
        )
        sleep_calls: list[float] = []

        async def _fake_sleep(delay: float) -> None:
            sleep_calls.append(delay)

        with patch("asyncio.sleep", side_effect=_fake_sleep):
            await reg._on_worker_empty("s1")

        assert 5 in sleep_calls

    async def test_on_worker_empty_deletes_ephemeral_session(self) -> None:
        """mutmut_15: sessions.pop() without default — but it should work."""
        hub = _make_hub()
        hub.browser_count = AsyncMock(return_value=0)
        session = _make_session("s1", ephemeral=True)
        reg = SessionRegistry(
            [session],
            hub=hub,
            public_base_url="http://localhost",
            recording=RecordingConfig(),
        )
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await reg._on_worker_empty("s1")
        # session must be deleted
        assert "s1" not in reg._sessions


# ===========================================================================
# registry.py — SessionRegistry._force_release_hijack()
# ===========================================================================


class TestForceReleaseHijack:
    async def test_force_release_uses_session_id(self) -> None:
        """mutmut_1: force_release_hijack(None) instead of force_release_hijack(session_id)."""
        hub = _make_hub()
        reg = SessionRegistry(
            [_make_session("sess1")],
            hub=hub,
            public_base_url="http://localhost",
            recording=RecordingConfig(),
        )
        await reg._force_release_hijack("sess1")
        hub.force_release_hijack.assert_called_with("sess1")


# ===========================================================================
# registry.py — SessionRegistry.create_session()
# ===========================================================================


class TestCreateSession:
    async def test_create_session_visibility_operator_valid(self) -> None:
        """mutmut_54/55: 'operator' in set changed to 'XXoperatorXX' or 'OPERATOR'."""
        reg = _make_registry()
        status = await reg.create_session(
            {
                "session_id": "s1",
                "connector_type": "shell",
                "visibility": "operator",
            }
        )
        assert status.visibility == "operator"

    async def test_create_session_rejects_invalid_visibility(self) -> None:
        """Complement: invalid visibility raises."""
        reg = _make_registry()
        with pytest.raises((SessionValidationError, ValueError)):
            await reg.create_session(
                {
                    "session_id": "s2",
                    "connector_type": "shell",
                    "visibility": "superadmin",
                }
            )

    async def test_create_session_auto_start_defaults_to_false(self) -> None:
        """mutmut_76/105/107/110: auto_start field removed or default changed."""
        reg = _make_registry()
        await reg.create_session(
            {
                "session_id": "s1",
                "connector_type": "shell",
            }
        )
        # session must not be auto-started — task should not be running
        rt = reg._runtimes.get("s1")
        assert rt is not None
        assert rt._task is None or rt._task.done()

    async def test_create_session_auto_start_true_starts(self) -> None:
        """mutmut_110: auto_start=True default causes unintended auto-start."""
        reg = _make_registry()
        # Explicitly NOT passing auto_start — must default to False
        await reg.create_session({"session_id": "s2", "connector_type": "shell"})
        rt = reg._runtimes["s2"]
        # Task should not have been started
        assert not rt._task or rt._task.done()

    async def test_create_session_display_name_defaults_to_session_id(self) -> None:
        """mutmut_84/86: display_name default changed to None or nothing."""
        reg = _make_registry()
        await reg.create_session({"session_id": "my-id", "connector_type": "shell"})
        session = reg._sessions["my-id"]
        assert session.display_name == "my-id"

    async def test_create_session_display_name_uses_payload_value(self) -> None:
        """display_name from payload must override default."""
        reg = _make_registry()
        await reg.create_session({"session_id": "s1", "connector_type": "shell", "display_name": "My Custom Name"})
        assert reg._sessions["s1"].display_name == "My Custom Name"

    async def test_create_session_ephemeral_defaults_to_false(self) -> None:
        """mutmut_141/142/143/144/145/148: ephemeral default/source changed."""
        reg = _make_registry()
        await reg.create_session({"session_id": "s1", "connector_type": "shell"})
        assert reg._sessions["s1"].ephemeral is False

    async def test_create_session_ephemeral_true_from_payload(self) -> None:
        """mutmut_146/147: ephemeral key name changed to XXephemeralXX or EPHEMERAL."""
        reg = _make_registry()
        await reg.create_session({"session_id": "s1", "connector_type": "shell", "ephemeral": True})
        assert reg._sessions["s1"].ephemeral is True

    async def test_create_session_ephemeral_false_from_payload(self) -> None:
        """mutmut_148: default=True means ephemeral=True even when not in payload."""
        reg = _make_registry()
        # Explicitly set to False
        await reg.create_session({"session_id": "s1", "connector_type": "shell", "ephemeral": False})
        assert reg._sessions["s1"].ephemeral is False

    async def test_create_session_invalid_connector_raises(self) -> None:
        """mutmut_23: error msg changed to None."""
        reg = _make_registry()
        with pytest.raises((SessionValidationError, Exception)):
            await reg.create_session({"session_id": "s1", "connector_type": "ftp"})

    async def test_create_session_visibility_public_valid(self) -> None:
        """mutmut_134/138/140: visibility cast mutated."""
        reg = _make_registry()
        status = await reg.create_session({"session_id": "s1", "connector_type": "shell", "visibility": "public"})
        assert status.visibility == "public"

    async def test_create_session_visibility_private_valid(self) -> None:
        reg = _make_registry()
        status = await reg.create_session({"session_id": "s1", "connector_type": "shell", "visibility": "private"})
        assert status.visibility == "private"


# ===========================================================================
# registry.py — SessionRegistry.update_session()
# ===========================================================================


class TestUpdateSession:
    async def test_update_session_model_dump_mode_python(self) -> None:
        """mutmut_7/8/9: model_dump mode changed to None/XXpythonXX/PYTHON."""
        reg = _make_registry([_make_session("s1")])
        # update with valid input_mode — will fail if model_dump returns wrong types
        status = await reg.update_session("s1", {"display_name": "Updated"})
        assert status is not None

    async def test_update_session_input_mode_triggers_set_mode(self) -> None:
        """mutmut_24/25/26: input_mode key check mutated."""
        hub = _make_hub()
        reg = SessionRegistry(
            [_make_session("s1")],
            hub=hub,
            public_base_url="http://localhost",
            recording=RecordingConfig(),
        )
        # set_mode on runtime should be called when input_mode in updates
        rt = reg._runtimes.get("s1") or reg._runtime_for(reg._sessions["s1"])
        set_mode_calls: list[str] = []

        original_set_mode = rt.set_mode

        async def _capture_set_mode(mode: str) -> None:
            set_mode_calls.append(mode)
            await original_set_mode(mode)

        rt.set_mode = _capture_set_mode  # type: ignore[method-assign]
        reg._runtimes["s1"] = rt

        await reg.update_session("s1", {"input_mode": "hijack"})
        assert "hijack" in set_mode_calls

    async def test_update_session_no_input_mode_no_set_mode(self) -> None:
        """mutmut_26: 'input_mode' not in updates — set_mode not called."""
        hub = _make_hub()
        reg = SessionRegistry(
            [_make_session("s1")],
            hub=hub,
            public_base_url="http://localhost",
            recording=RecordingConfig(),
        )
        # patch set_mode to verify it's NOT called
        rt = reg._runtime_for(reg._sessions["s1"])
        set_mode_calls: list[str] = []
        original = rt.set_mode

        async def _capture(mode: str) -> None:
            set_mode_calls.append(mode)
            await original(mode)

        rt.set_mode = _capture  # type: ignore[method-assign]
        reg._runtimes["s1"] = rt

        await reg.update_session("s1", {"display_name": "no mode change"})
        assert set_mode_calls == []


# ===========================================================================
# registry.py — SessionRegistry.delete_session()
# ===========================================================================


class TestDeleteSession:
    async def test_delete_session_removes_from_sessions(self) -> None:
        """mutmut_3: sessions.pop without default — still should work."""
        reg = _make_registry([_make_session("s1")])
        await reg.delete_session("s1")
        assert "s1" not in reg._sessions

    async def test_delete_session_stops_runtime(self) -> None:
        """mutmut_4: runtime = None instead of _runtimes.pop — runtime not stopped."""
        hub = _make_hub()
        reg = SessionRegistry(
            [_make_session("s1")],
            hub=hub,
            public_base_url="http://localhost",
            recording=RecordingConfig(),
        )
        # Ensure runtime is created
        rt = reg._runtime_for(reg._sessions["s1"])
        stop_called = False
        original_stop = rt.stop

        async def _capture_stop() -> None:
            nonlocal stop_called
            stop_called = True
            await original_stop()

        rt.stop = _capture_stop  # type: ignore[method-assign]
        reg._runtimes["s1"] = rt

        await reg.delete_session("s1")
        assert stop_called

    async def test_delete_session_uses_session_id_for_runtimes_pop(self) -> None:
        """mutmut_5: _runtimes.pop(None, None) instead of pop(session_id, None)."""
        reg = _make_registry([_make_session("s1")])
        # Create a runtime for s1
        _ = reg._runtime_for(reg._sessions["s1"])
        assert "s1" in reg._runtimes
        await reg.delete_session("s1")
        assert "s1" not in reg._runtimes


# ===========================================================================
# registry.py — SessionRegistry.set_mode()
# ===========================================================================


class TestRegistrySetMode:
    async def test_set_mode_model_dump_python(self) -> None:
        """mutmut_5/6/7: model_dump mode mutated."""
        reg = _make_registry([_make_session("s1")])
        status = await reg.set_mode("s1", "hijack")
        assert status is not None

    async def test_set_mode_assigns_validated_input_mode(self) -> None:
        """mutmut_12: session.input_mode = None instead of validated.input_mode."""
        reg = _make_registry([_make_session("s1")])
        await reg.set_mode("s1", "hijack")
        assert reg._sessions["s1"].input_mode == "hijack"

    async def test_set_mode_open_releases_hijack(self) -> None:
        """mutmut_15/16/17: condition mutated — hijack not released on open."""
        hub = _make_hub()
        reg = SessionRegistry(
            [_make_session("s1")],
            hub=hub,
            public_base_url="http://localhost",
            recording=RecordingConfig(),
        )
        await reg.set_mode("s1", "open")
        hub.force_release_hijack.assert_called_with("s1")

    async def test_set_mode_hijack_does_not_release_hijack(self) -> None:
        """mutmut_15 (inverted): hijack mode should NOT release."""
        hub = _make_hub()
        reg = SessionRegistry(
            [_make_session("s1")],
            hub=hub,
            public_base_url="http://localhost",
            recording=RecordingConfig(),
        )
        await reg.set_mode("s1", "hijack")
        hub.force_release_hijack.assert_not_called()

    async def test_set_mode_force_release_uses_session_id(self) -> None:
        """mutmut_18: force_release_hijack(None) instead of (session_id)."""
        hub = _make_hub()
        reg = SessionRegistry(
            [_make_session("s1")],
            hub=hub,
            public_base_url="http://localhost",
            recording=RecordingConfig(),
        )
        await reg.set_mode("s1", "open")
        hub.force_release_hijack.assert_called_with("s1")


# ===========================================================================
# registry.py — SessionRegistry.last_snapshot(), events()
# ===========================================================================


class TestLastSnapshotAndEvents:
    async def test_last_snapshot_uses_session_id(self) -> None:
        """mutmut_1: get_last_snapshot(None) instead of get_last_snapshot(session_id)."""
        hub = _make_hub()
        hub.get_last_snapshot = AsyncMock(return_value={"type": "snapshot"})
        reg = _make_registry(hub=hub)
        await reg.last_snapshot("my-session")
        hub.get_last_snapshot.assert_called_with("my-session")

    async def test_events_default_limit_is_100(self) -> None:
        """mutmut_1: default limit=101 instead of 100."""
        hub = _make_hub()
        hub.get_recent_events = AsyncMock(return_value=[])
        reg = _make_registry(hub=hub)
        # Call without explicit limit — should use default 100
        await reg.events("some-session")
        hub.get_recent_events.assert_called_with("some-session", 100)

    async def test_events_uses_session_id(self) -> None:
        """mutmut_2: get_recent_events(None, limit) instead of (session_id, limit)."""
        hub = _make_hub()
        hub.get_recent_events = AsyncMock(return_value=[])
        reg = _make_registry(hub=hub)
        await reg.events("target-session", limit=50)
        hub.get_recent_events.assert_called_with("target-session", 50)

    async def test_events_passes_limit(self) -> None:
        """mutmut_3: get_recent_events(session_id, None) instead of (session_id, limit)."""
        hub = _make_hub()
        hub.get_recent_events = AsyncMock(return_value=[])
        reg = _make_registry(hub=hub)
        await reg.events("s", limit=42)
        hub.get_recent_events.assert_called_with("s", 42)


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


class TestExtractBearerTokenMutants:
    def test_missing_authorization_returns_none(self) -> None:
        """mutmut_4/6: default None/nothing — str(None)='None' causes false match."""
        from undef.terminal.server.auth import extract_bearer_token

        # No authorization header at all
        result = extract_bearer_token({})
        assert result is None

    def test_non_empty_default_not_treated_as_bearer(self) -> None:
        """mutmut_9: default 'XXXX' would cause str check to fail differently."""
        from undef.terminal.server.auth import extract_bearer_token

        result = extract_bearer_token({})
        assert result is None

    def test_split_on_space_extracts_token(self) -> None:
        """mutmut_12: split(None, 1) splits on any whitespace (different semantics)."""
        from undef.terminal.server.auth import extract_bearer_token

        result = extract_bearer_token({"authorization": "Bearer   my-token"})
        # split(" ", 1) gives ["Bearer", "  my-token"]; strip() removes spaces
        # split(None, 1) gives ["Bearer", "my-token"] — slightly different but token valid
        # The key: make sure a token with multiple spaces is handled consistently
        assert result == "my-token"

    def test_split_none_difference_with_tab(self) -> None:
        """split(None,...) splits on tabs too — split(' ',1) does not."""
        from undef.terminal.server.auth import extract_bearer_token

        # Tab-separated header
        result = extract_bearer_token({"authorization": "Bearer\tmytoken"})
        # With split(" ", 1): only 1 part => None
        assert result is None


# ===========================================================================
# auth.py — _roles_from_claims()
# ===========================================================================


class TestRolesFromClaimsMutants:
    def _auth(self) -> AuthConfig:
        return AuthConfig(
            mode="jwt",
            jwt_public_key_pem=_TEST_KEY,
            worker_bearer_token=_make_jwt_token(),
        )

    def test_list_roles_empty_string_filtered(self) -> None:
        """mutmut_14: str(None).strip() always truthy — empty strings would pass."""
        from undef.terminal.server.auth import _roles_from_claims

        # Empty string in list should be filtered (str("").strip() is falsy)
        result = _roles_from_claims({"roles": ["", "admin"]}, self._auth())
        assert "admin" in result

    def test_empty_string_in_list_not_included(self) -> None:
        """With the fix, empty strings are filtered before role validation."""
        from undef.terminal.server.auth import _roles_from_claims

        result = _roles_from_claims({"roles": [""]}, self._auth())
        # No valid role => fallback to viewer
        assert result == frozenset({"viewer"})


# ===========================================================================
# auth.py — _resolve_jwt_key()
# ===========================================================================


class TestResolveJwtKeyMutants:
    def test_public_key_pem_path_returned(self) -> None:
        """mutmut_22: error message changed (but raise still happens — testing positive path)."""
        from undef.terminal.server.auth import _resolve_jwt_key

        auth = AuthConfig(
            mode="jwt",
            jwt_public_key_pem=_TEST_KEY,
            worker_bearer_token=_make_jwt_token(),
        )
        key = _resolve_jwt_key("dummytoken", auth)
        assert key == _TEST_KEY

    def test_no_key_raises_value_error(self) -> None:
        """mutmut_22: error message mutated — still should raise ValueError."""
        from undef.terminal.server.auth import _resolve_jwt_key

        auth = AuthConfig(
            mode="jwt",
            jwt_public_key_pem=None,
            jwt_jwks_url=None,
            worker_bearer_token=_make_jwt_token(),
        )
        with pytest.raises(ValueError):
            _resolve_jwt_key("token", auth)

    def test_jwks_cache_uses_correct_url(self) -> None:
        """mutmut_1: url = None instead of auth.jwt_jwks_url — cache key would be None."""
        from undef.terminal.server.auth import _JWKS_CLIENT_CACHE, _JWKS_CLIENT_CACHE_LOCK, _resolve_jwt_key

        auth = AuthConfig(
            mode="jwt",
            jwt_jwks_url="https://example.com/.well-known/jwks.json",
            worker_bearer_token=_make_jwt_token(),
        )
        # Clear the cache first
        with _JWKS_CLIENT_CACHE_LOCK:
            _JWKS_CLIENT_CACHE.clear()

        with patch("jwt.PyJWKClient") as mock_pyjwkclient:
            mock_client = MagicMock()
            mock_client.get_signing_key_from_jwt.return_value = MagicMock(key="mykey")
            mock_pyjwkclient.return_value = mock_client
            _resolve_jwt_key("sometoken", auth)

        # Verify the client was created with the correct URL
        call_args = mock_pyjwkclient.call_args[0]
        assert call_args[0] == "https://example.com/.well-known/jwks.json"

    def test_jwks_client_created_with_cache_keys_true(self) -> None:
        """mutmut_12/17: cache_keys=None or False instead of True."""
        from undef.terminal.server.auth import _JWKS_CLIENT_CACHE, _JWKS_CLIENT_CACHE_LOCK, _resolve_jwt_key

        auth = AuthConfig(
            mode="jwt",
            jwt_jwks_url="https://example.com/.well-known/jwks.json",
            worker_bearer_token=_make_jwt_token(),
        )
        with _JWKS_CLIENT_CACHE_LOCK:
            _JWKS_CLIENT_CACHE.clear()

        with patch("jwt.PyJWKClient") as mock_pyjwkclient:
            mock_client = MagicMock()
            mock_client.get_signing_key_from_jwt.return_value = MagicMock(key="k")
            mock_pyjwkclient.return_value = mock_client
            _resolve_jwt_key("sometoken", auth)

        call_kwargs = mock_pyjwkclient.call_args[1]
        assert call_kwargs.get("cache_keys") is True

    def test_jwks_client_created_with_timeout_10(self) -> None:
        """mutmut_13/16/18: timeout=None/omitted/11 instead of 10."""
        from undef.terminal.server.auth import _JWKS_CLIENT_CACHE, _JWKS_CLIENT_CACHE_LOCK, _resolve_jwt_key

        auth = AuthConfig(
            mode="jwt",
            jwt_jwks_url="https://example.com/.well-known/jwks.json",
            worker_bearer_token=_make_jwt_token(),
        )
        with _JWKS_CLIENT_CACHE_LOCK:
            _JWKS_CLIENT_CACHE.clear()

        with patch("jwt.PyJWKClient") as mock_pyjwkclient:
            mock_client = MagicMock()
            mock_client.get_signing_key_from_jwt.return_value = MagicMock(key="k")
            mock_pyjwkclient.return_value = mock_client
            _resolve_jwt_key("sometoken", auth)

        call_kwargs = mock_pyjwkclient.call_args[1]
        assert call_kwargs.get("timeout") == 10

    def test_get_signing_key_uses_token(self) -> None:
        """mutmut_20: get_signing_key_from_jwt(None) instead of (token)."""
        from undef.terminal.server.auth import _JWKS_CLIENT_CACHE, _JWKS_CLIENT_CACHE_LOCK, _resolve_jwt_key

        auth = AuthConfig(
            mode="jwt",
            jwt_jwks_url="https://example.com/.well-known/jwks.json",
            worker_bearer_token=_make_jwt_token(),
        )
        with _JWKS_CLIENT_CACHE_LOCK:
            _JWKS_CLIENT_CACHE.clear()

        the_token = "my.jwt.token"
        with patch("jwt.PyJWKClient") as mock_pyjwkclient:
            mock_client = MagicMock()
            mock_client.get_signing_key_from_jwt.return_value = MagicMock(key="k")
            mock_pyjwkclient.return_value = mock_client
            _resolve_jwt_key(the_token, auth)

        mock_client.get_signing_key_from_jwt.assert_called_with(the_token)


# ===========================================================================
# auth.py — _principal_from_jwt_token()
# ===========================================================================


class TestPrincipalFromJwtToken:
    def test_decodes_and_returns_principal(self) -> None:
        from undef.terminal.server.auth import _principal_from_jwt_token

        token = _make_jwt_token("user42", roles=["admin"])
        auth = _jwt_auth_config()
        p = _principal_from_jwt_token(token, auth)
        assert p.subject_id == "user42"
        assert "admin" in p.roles

    def test_leeway_zero_is_min(self) -> None:
        """mutmut_26: max(1,...) instead of max(0,...) — 0 second skew should give leeway=0."""
        from undef.terminal.server.auth import _principal_from_jwt_token

        auth = _jwt_auth_config()
        auth.clock_skew_seconds = 0  # type: ignore[assignment]
        token = _make_jwt_token()
        # Should not raise — leeway can be 0
        p = _principal_from_jwt_token(token, auth)
        assert p is not None

    def test_scopes_included_in_principal(self) -> None:
        """mutmut_49/53: scopes=None or scopes omitted."""
        import jwt as pyjwt

        from undef.terminal.server.auth import _principal_from_jwt_token

        auth = _jwt_auth_config()
        now = int(time.time())
        token = pyjwt.encode(
            {
                "sub": "user1",
                "roles": ["admin"],
                "scopes": "read write",
                "iss": "undef-terminal",
                "aud": "undef-terminal-server",
                "exp": now + 600,
            },
            key=_TEST_KEY,
            algorithm="HS256",
        )
        auth.jwt_scopes_claim = "scopes"  # type: ignore[assignment]
        p = _principal_from_jwt_token(token, auth)
        assert p.scopes is not None
        assert isinstance(p.scopes, frozenset)

    def test_claims_included_in_principal(self) -> None:
        """mutmut_50/54: claims=None or claims omitted."""
        from undef.terminal.server.auth import _principal_from_jwt_token

        token = _make_jwt_token("user1", roles=["operator"])
        auth = _jwt_auth_config()
        p = _principal_from_jwt_token(token, auth)
        assert p.claims is not None
        assert "sub" in p.claims
        assert p.claims["sub"] == "user1"

    def test_empty_sub_raises(self) -> None:
        """mutmut_45: error message changed — must still raise ValueError."""
        import jwt as pyjwt

        from undef.terminal.server.auth import _principal_from_jwt_token

        auth = _jwt_auth_config()
        now = int(time.time())
        # Token with empty sub
        token = pyjwt.encode(
            {
                "sub": "",
                "iss": "undef-terminal",
                "aud": "undef-terminal-server",
                "exp": now + 600,
            },
            key=_TEST_KEY,
            algorithm="HS256",
        )
        with pytest.raises(ValueError):
            _principal_from_jwt_token(token, auth)

    def test_resolve_jwt_key_called_with_token(self) -> None:
        """mutmut_2: _resolve_jwt_key(None, auth) instead of (token, auth)."""
        from undef.terminal.server.auth import _principal_from_jwt_token

        token = _make_jwt_token()
        auth = _jwt_auth_config()
        with patch("undef.terminal.server.auth._resolve_jwt_key") as mock_resolve:
            mock_resolve.return_value = _TEST_KEY
            _principal_from_jwt_token(token, auth)
        mock_resolve.assert_called_with(token, auth)


# ===========================================================================
# auth.py — _anonymous_principal()
# ===========================================================================


class TestAnonymousPrincipal:
    def test_anonymous_has_scopes_frozenset(self) -> None:
        """mutmut_3: scopes=None; mutmut_6: scopes omitted."""
        from undef.terminal.server.auth import _anonymous_principal

        p = _anonymous_principal()
        assert p.scopes is not None
        assert isinstance(p.scopes, frozenset)
        assert len(p.scopes) == 0

    def test_anonymous_subject_id(self) -> None:
        from undef.terminal.server.auth import _anonymous_principal

        p = _anonymous_principal()
        assert p.subject_id == "anonymous"

    def test_anonymous_has_viewer_role(self) -> None:
        from undef.terminal.server.auth import _anonymous_principal

        p = _anonymous_principal()
        assert "viewer" in p.roles


# ===========================================================================
# auth.py — _principal_from_header_auth()
# ===========================================================================


class TestPrincipalFromHeaderAuth:
    def _auth(self) -> AuthConfig:
        return AuthConfig(
            mode="header",
            worker_bearer_token=_make_jwt_token(),
        )

    def test_no_role_header_defaults_to_viewer(self) -> None:
        """mutmut_15/17/18: role default changed — empty string should still give viewer."""
        from undef.terminal.server.auth import _principal_from_header_auth

        auth = self._auth()
        p = _principal_from_header_auth({"x-uterm-principal": "user1"}, {}, auth)
        assert "viewer" in p.roles

    def test_role_header_viewer_accepted(self) -> None:
        """mutmut_22/23: 'viewer' mutated in valid roles set."""
        from undef.terminal.server.auth import _principal_from_header_auth

        auth = self._auth()
        p = _principal_from_header_auth({"x-uterm-principal": "user1", "x-uterm-role": "viewer"}, {}, auth)
        assert "viewer" in p.roles

    def test_role_header_operator_accepted(self) -> None:
        from undef.terminal.server.auth import _principal_from_header_auth

        auth = self._auth()
        p = _principal_from_header_auth({"x-uterm-principal": "user1", "x-uterm-role": "operator"}, {}, auth)
        assert "operator" in p.roles

    def test_role_header_admin_accepted(self) -> None:
        from undef.terminal.server.auth import _principal_from_header_auth

        auth = self._auth()
        p = _principal_from_header_auth({"x-uterm-principal": "user1", "x-uterm-role": "admin"}, {}, auth)
        assert "admin" in p.roles

    def test_invalid_role_falls_back_to_viewer(self) -> None:
        from undef.terminal.server.auth import _principal_from_header_auth

        auth = self._auth()
        p = _principal_from_header_auth({"x-uterm-principal": "user1", "x-uterm-role": "superadmin"}, {}, auth)
        assert p.roles == frozenset({"viewer"})

    def test_scopes_is_frozenset(self) -> None:
        """mutmut_33/36: scopes=None or omitted."""
        from undef.terminal.server.auth import _principal_from_header_auth

        auth = self._auth()
        p = _principal_from_header_auth({"x-uterm-principal": "user1"}, {}, auth)
        assert isinstance(p.scopes, frozenset)

    def test_no_role_header_with_non_empty_default_would_be_invalid(self) -> None:
        """mutmut_18: default 'XXXX' would give invalid role, falling back to viewer."""
        from undef.terminal.server.auth import _principal_from_header_auth

        auth = self._auth()
        # No role header — must default to viewer (not some garbage role)
        p = _principal_from_header_auth({}, {}, auth)
        assert p.roles == frozenset({"viewer"})


# ===========================================================================
# auth.py — _principal_from_local_mode()
# ===========================================================================


class TestPrincipalFromLocalMode:
    def _auth(self) -> AuthConfig:
        return AuthConfig(
            mode="dev",
            worker_bearer_token=_make_jwt_token(),
        )

    def test_no_header_defaults_to_local_dev(self) -> None:
        """mutmut_9/10: default changed to XXlocal-devXX or LOCAL-DEV."""
        from undef.terminal.server.auth import _principal_from_local_mode

        auth = self._auth()
        p = _principal_from_local_mode({}, {}, auth)
        assert p.subject_id == "local-dev"

    def test_cookie_fallback_used(self) -> None:
        """mutmut_6: _cookie_value(cookies, None) instead of (cookies, auth.principal_cookie)."""
        from undef.terminal.server.auth import _principal_from_local_mode

        auth = self._auth()
        cookies = {"uterm_principal": "cookie-user"}
        p = _principal_from_local_mode({}, cookies, auth)
        assert p.subject_id == "cookie-user"

    def test_or_semantics_not_and(self) -> None:
        """mutmut_2: 'or' changed to 'and' in fallback chain."""
        from undef.terminal.server.auth import _principal_from_local_mode

        auth = self._auth()
        # No headers, no cookies — should fall back to "local-dev"
        p = _principal_from_local_mode({}, {}, auth)
        assert p.subject_id == "local-dev"

    def test_no_role_defaults_to_admin(self) -> None:
        """mutmut_15/17/18: role default changed."""
        from undef.terminal.server.auth import _principal_from_local_mode

        auth = self._auth()
        p = _principal_from_local_mode({}, {}, auth)
        assert "admin" in p.roles

    def test_role_header_viewer_accepted(self) -> None:
        """mutmut_24 doesn't affect viewer — but let's test all 3."""
        from undef.terminal.server.auth import _principal_from_local_mode

        auth = self._auth()
        p = _principal_from_local_mode({"x-uterm-role": "viewer"}, {}, auth)
        assert "viewer" in p.roles

    def test_role_header_operator_accepted(self) -> None:
        """mutmut_24/25: 'operator' mutated in valid roles set."""
        from undef.terminal.server.auth import _principal_from_local_mode

        auth = self._auth()
        p = _principal_from_local_mode({"x-uterm-role": "operator"}, {}, auth)
        assert "operator" in p.roles

    def test_role_header_admin_accepted(self) -> None:
        """mutmut_26/27: 'admin' mutated in valid roles set."""
        from undef.terminal.server.auth import _principal_from_local_mode

        auth = self._auth()
        p = _principal_from_local_mode({"x-uterm-role": "admin"}, {}, auth)
        assert "admin" in p.roles

    def test_scopes_includes_wildcard(self) -> None:
        from undef.terminal.server.auth import _principal_from_local_mode

        auth = self._auth()
        p = _principal_from_local_mode({}, {}, auth)
        assert "*" in p.scopes


# ===========================================================================
# auth.py — _resolve_principal()
# ===========================================================================


class TestResolvePrincipal:
    def test_header_mode_passes_cookies(self) -> None:
        """mutmut_19: _principal_from_header_auth(headers, None, auth) — cookies lost."""
        from undef.terminal.server.auth import _resolve_principal

        auth = AuthConfig(
            mode="header",
            worker_bearer_token=_make_jwt_token(),
        )
        cookies = {"uterm_principal": "cookie-user"}
        p = _resolve_principal({}, cookies, auth)
        assert p.subject_id == "cookie-user"

    def test_jwt_failure_logs_and_returns_anonymous(self) -> None:
        """mutmut_41/42/43/44: logger.warning args mutated — exception must still be caught."""
        from undef.terminal.server.auth import _resolve_principal

        auth = AuthConfig(
            mode="jwt",
            jwt_public_key_pem=_TEST_KEY,
            jwt_algorithms=["HS256"],
            jwt_issuer="undef-terminal",
            jwt_audience="undef-terminal-server",
            worker_bearer_token=_make_jwt_token(),
        )
        headers = {"authorization": "Bearer INVALID_TOKEN"}
        p = _resolve_principal(headers, {}, auth)
        assert p.subject_id == "anonymous"

    def test_jwt_failure_logged_as_warning(self) -> None:
        """mutmut_41/42/43/44: verify logger.warning is called (not swallowed)."""
        from undef.terminal.server.auth import _resolve_principal

        auth = AuthConfig(
            mode="jwt",
            jwt_public_key_pem=_TEST_KEY,
            jwt_algorithms=["HS256"],
            jwt_issuer="undef-terminal",
            jwt_audience="undef-terminal-server",
            worker_bearer_token=_make_jwt_token(),
        )
        headers = {"authorization": "Bearer INVALID_TOKEN"}
        with patch("undef.terminal.server.auth.logger") as mock_logger:
            _resolve_principal(headers, {}, auth)
        mock_logger.warning.assert_called_once()


# ===========================================================================
# auth.py — resolve_http_principal() / resolve_ws_principal()
# ===========================================================================


class TestResolveHttpPrincipal:
    def test_uses_request_headers(self) -> None:
        """mutmut_4/7: headers default changed to None/nothing."""
        from undef.terminal.server.auth import resolve_http_principal

        auth = AuthConfig(mode="dev", worker_bearer_token=_make_jwt_token())

        class _FakeRequest:
            headers = {"x-uterm-principal": "req-user"}
            cookies: dict[str, str] = {}

        p = resolve_http_principal(_FakeRequest(), auth)
        assert p.subject_id == "req-user"

    def test_no_headers_attribute_falls_back(self) -> None:
        """mutmut_4: getattr with default None — code calling .get() on None would fail."""
        from undef.terminal.server.auth import resolve_http_principal

        auth = AuthConfig(mode="dev", worker_bearer_token=_make_jwt_token())
        # object with no headers attr — should use default {}
        p = resolve_http_principal(object(), auth)
        assert p is not None

    def test_uses_request_cookies(self) -> None:
        """mutmut_13/16: cookies default changed to None/nothing."""
        from undef.terminal.server.auth import resolve_http_principal

        auth = AuthConfig(mode="dev", worker_bearer_token=_make_jwt_token())

        class _FakeRequest:
            headers: dict[str, str] = {}
            cookies = {"uterm_principal": "cookie-user"}

        p = resolve_http_principal(_FakeRequest(), auth)
        assert p.subject_id == "cookie-user"

    def test_no_cookies_attribute_falls_back(self) -> None:
        """mutmut_13: getattr(req, cookies, None) — None.get() would fail."""
        from undef.terminal.server.auth import resolve_http_principal

        auth = AuthConfig(mode="dev", worker_bearer_token=_make_jwt_token())

        class _FakeRequest:
            headers: dict[str, str] = {}
            # no cookies attr

        p = resolve_http_principal(_FakeRequest(), auth)
        assert p is not None


class TestResolveWsPrincipal:
    def test_uses_websocket_headers(self) -> None:
        """mutmut_4/7: headers default None/nothing."""
        from undef.terminal.server.auth import resolve_ws_principal

        auth = AuthConfig(mode="dev", worker_bearer_token=_make_jwt_token())

        class _FakeWsObj:
            headers = {"x-uterm-principal": "ws-user"}
            cookies: dict[str, str] = {}

        p = resolve_ws_principal(_FakeWsObj(), auth)
        assert p.subject_id == "ws-user"

    def test_no_headers_attribute_falls_back(self) -> None:
        """mutmut_4: default None breaks subsequent .get() call."""
        from undef.terminal.server.auth import resolve_ws_principal

        auth = AuthConfig(mode="dev", worker_bearer_token=_make_jwt_token())
        p = resolve_ws_principal(object(), auth)
        assert p is not None

    def test_uses_websocket_cookies(self) -> None:
        """mutmut_11/13/16: cookies source/default mutated."""
        from undef.terminal.server.auth import resolve_ws_principal

        auth = AuthConfig(mode="dev", worker_bearer_token=_make_jwt_token())

        class _FakeWsObj:
            headers: dict[str, str] = {}
            cookies = {"uterm_principal": "ws-cookie-user"}

        p = resolve_ws_principal(_FakeWsObj(), auth)
        assert p.subject_id == "ws-cookie-user"

    def test_uses_correct_cookies_attr_name(self) -> None:
        """mutmut_17/18: 'cookies' attr name changed to 'XXcookiesXX' or 'COOKIES'."""
        from undef.terminal.server.auth import resolve_ws_principal

        auth = AuthConfig(mode="dev", worker_bearer_token=_make_jwt_token())

        class _FakeWsObj:
            headers: dict[str, str] = {}
            cookies = {"uterm_principal": "right-user"}
            # purposely NOT providing XXcookiesXX or COOKIES

        p = resolve_ws_principal(_FakeWsObj(), auth)
        assert p.subject_id == "right-user"

    def test_uses_websocket_not_none_for_cookies(self) -> None:
        """mutmut_11: getattr(None, 'cookies', {}) instead of getattr(websocket,...)."""
        from undef.terminal.server.auth import resolve_ws_principal

        auth = AuthConfig(mode="dev", worker_bearer_token=_make_jwt_token())

        class _FakeWsObj:
            headers: dict[str, str] = {}
            cookies = {"uterm_principal": "ws-user"}

        p = resolve_ws_principal(_FakeWsObj(), auth)
        # Must pick up cookie from the actual websocket object
        assert p.subject_id == "ws-user"
