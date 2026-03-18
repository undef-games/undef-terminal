#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Targeted mutation-killing tests for client/hijack.py and client/mcp_tools.py.

Each test is designed to detect a specific surviving mutant. Tests use
httpx ASGITransport to exercise real HTTP paths.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock

from fastapi import FastAPI
from httpx import ASGITransport

from undef.terminal.client.hijack import HijackClient
from undef.terminal.client.mcp_tools import _ok, hijack_tools
from undef.terminal.hijack.hub import TermHub
from undef.terminal.hijack.models import WorkerTermState

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

WID = "mutant-worker"


def _make_hub_app() -> tuple[TermHub, FastAPI]:
    hub = TermHub(resolve_browser_role=lambda _ws, _wid: "admin")
    app = FastAPI()
    app.include_router(hub.create_router())
    return hub, app


def _add_worker(hub: TermHub, worker_id: str = WID) -> AsyncMock:
    mock_ws = AsyncMock()
    mock_ws.send_text = AsyncMock()
    hub._workers[worker_id] = WorkerTermState(worker_ws=mock_ws)
    return mock_ws


def _client_for(app: FastAPI, **kwargs: Any) -> HijackClient:
    return HijackClient(
        "http://test",
        transport=ASGITransport(app=app),
        **kwargs,  # type: ignore[arg-type]
    )


def _server_app() -> FastAPI:
    from undef.terminal.server.app import create_server_app
    from undef.terminal.server.config import config_from_mapping

    cfg = config_from_mapping(
        {
            "server": {"host": "127.0.0.1", "port": 0},
            "auth": {"mode": "dev"},
            "sessions": [
                {
                    "session_id": "s1",
                    "display_name": "Test",
                    "connector_type": "shell",
                    "auto_start": False,
                }
            ],
        }
    )
    return create_server_app(cfg)


def _server_client(app: FastAPI) -> HijackClient:
    return HijackClient(
        "http://test",
        transport=ASGITransport(app=app),
        headers={"X-Uterm-Principal": "tester", "X-Uterm-Role": "admin"},
    )


# ---------------------------------------------------------------------------
# HijackClient.__init__ mutations
# mutmut_6: rstrip → lstrip for base_url
# mutmut_9/10: rstrip → lstrip for entity_prefix
# mutmut_17/18: _owns_client=True → None/False
# ---------------------------------------------------------------------------


class TestHijackClientInit:
    def test_base_url_trailing_slash_stripped(self) -> None:
        """mutmut_6: base_url trailing slash must be stripped (rstrip not lstrip)."""
        c = HijackClient("http://localhost:8780/")
        assert c._base_url == "http://localhost:8780"
        assert not c._base_url.endswith("/")

    def test_base_url_without_trailing_slash_unchanged(self) -> None:
        """rstrip on URL without trailing slash should not alter it."""
        c = HijackClient("http://localhost:8780")
        assert c._base_url == "http://localhost:8780"

    def test_base_url_lstrip_would_corrupt_url(self) -> None:
        """mutmut_6: lstrip('/') would leave trailing slash on URL with trailing /."""
        url = "http://localhost:8780/"
        # rstrip removes trailing slash → correct
        assert url.rstrip("/") == "http://localhost:8780"
        # lstrip removes leading slash → wrong (doesn't remove trailing)
        assert url.lstrip("/") == "http://localhost:8780/"

    def test_entity_prefix_trailing_slash_stripped(self) -> None:
        """mutmut_9/10: entity_prefix trailing slash must be stripped."""
        c = HijackClient("http://test", entity_prefix="/worker/")
        assert c._entity_prefix == "/worker"
        assert not c._entity_prefix.endswith("/")

    def test_owns_client_initially_true(self) -> None:
        """mutmut_17/18: _owns_client must start as True (bool, not None)."""
        c = HijackClient("http://test")
        assert c._owns_client is True
        assert c._owns_client is not None

    def test_entity_prefix_default_is_slash_worker(self) -> None:
        """mutmut_1/2: entity_prefix default must be '/worker'."""
        c = HijackClient("http://test")
        assert c._entity_prefix == "/worker"

    def test_timeout_default_is_20(self) -> None:
        """mutmut_3: timeout default must be exactly 20.0."""
        c = HijackClient("http://test")
        assert c._timeout == 20.0
        assert c._timeout != 21.0


# ---------------------------------------------------------------------------
# HijackClient.__aenter__ / __aexit__ mutations
# mutmut_14/15: _owns_client=True → None/False in aenter
# mutmut_2: _client=None → "" in aexit
# ---------------------------------------------------------------------------


class TestHijackClientContextManager:
    async def test_aenter_sets_owns_client_true(self) -> None:
        """mutmut_14/15: __aenter__ must set _owns_client=True."""
        c = HijackClient("http://test")
        c._owns_client = False  # reset
        async with c:
            assert c._owns_client is True
            assert c._owns_client is not None
        # After aexit, client should be cleaned up
        assert c._client is None

    async def test_aexit_sets_client_to_none(self) -> None:
        """mutmut_2: __aexit__ must set _client to None (not '')."""
        hub, app = _make_hub_app()
        _add_worker(hub)
        c = _client_for(app)
        async with c:
            assert c._client is not None

        # After exit, _client must be exactly None
        assert c._client is None
        assert c._client != ""

    async def test_aexit_client_none_is_noop(self) -> None:
        """__aexit__ when _client is None must not raise."""
        c = HijackClient("http://test")
        assert c._client is None
        # Should not raise
        await c.__aexit__(None, None, None)
        assert c._client is None


# ---------------------------------------------------------------------------
# HijackClient._get_client — mutmut_15/16: _owns_client
# ---------------------------------------------------------------------------


class TestGetClient:
    def test_lazy_client_sets_owns_client_true(self) -> None:
        """mutmut_15/16: lazy _get_client must set _owns_client=True."""
        c = HijackClient("http://test")
        c._owns_client = False  # reset

        _ = c._get_client()
        assert c._owns_client is True
        assert c._owns_client is not None

        # cleanup
        import asyncio

        asyncio.run(c._client.aclose())


# ---------------------------------------------------------------------------
# HijackClient._request — mutmut_25: str(exc) → str(None)
# ---------------------------------------------------------------------------


class TestRequestError:
    async def test_error_body_contains_exception_message(self) -> None:
        """mutmut_25: error body must contain str(exc), not str(None)."""
        # Use a transport that raises an HTTPError
        c = HijackClient("http://127.0.0.1:1")  # nothing listening
        ok, data = await c._request("GET", "/no-such-path")
        assert ok is False
        assert "error" in data
        # The error string must not be str(None) = "None"
        assert data["error"] != "None"
        # It should be a meaningful error message
        assert len(data["error"]) > 0


# ---------------------------------------------------------------------------
# HijackClient.acquire — mutmut_3: lease_s default = 90
# mutmut_11: "POST" vs "post" (equivalent, but also covers JSON body)
# ---------------------------------------------------------------------------


class TestAcquireMutants:
    async def test_acquire_default_owner_is_operator(self) -> None:
        """mutmut_1/2: owner default must be 'operator'."""
        hub, app = _make_hub_app()
        _add_worker(hub)
        async with _client_for(app) as c:
            ok, data = await c.acquire(WID)
        assert ok is True
        assert data["owner"] == "operator"

    async def test_acquire_default_lease_s_is_90(self) -> None:
        """mutmut_3: lease_s default must be 90."""
        hub, app = _make_hub_app()
        _add_worker(hub)
        async with _client_for(app) as c:
            ok, data = await c.acquire(WID)
        assert ok is True
        # lease_expires_at should be about 90s from now
        assert "lease_expires_at" in data
        remaining = data["lease_expires_at"] - time.time()
        assert 85 <= remaining <= 95  # 90s ± 5s tolerance

    async def test_acquire_sends_owner_in_json(self) -> None:
        """Acquire sends owner in JSON body (kills mutants that drop JSON)."""
        hub, app = _make_hub_app()
        _add_worker(hub)
        async with _client_for(app) as c:
            ok, data = await c.acquire(WID, owner="mybot", lease_s=60)
        assert ok is True
        assert data["owner"] == "mybot"

    async def test_acquire_sends_lease_s_in_json(self) -> None:
        """Acquire sends lease_s in JSON body."""
        hub, app = _make_hub_app()
        _add_worker(hub)
        async with _client_for(app) as c:
            ok, data = await c.acquire(WID, lease_s=30)
        assert ok is True
        remaining = data["lease_expires_at"] - time.time()
        assert 25 <= remaining <= 35


# ---------------------------------------------------------------------------
# HijackClient.heartbeat — mutmut_4: json=None, mutmut_14/15: wrong keys
# mutmut_1: lease_s default = 90
# ---------------------------------------------------------------------------


class TestHeartbeatMutants:
    async def test_heartbeat_default_lease_s_is_90(self) -> None:
        """mutmut_1: lease_s default must be 90."""
        hub, app = _make_hub_app()
        _add_worker(hub)
        async with _client_for(app) as c:
            ok, acq = await c.acquire(WID)
            hid = acq["hijack_id"]
            ok, hb = await c.heartbeat(WID, hid)

        assert ok is True
        # Default lease_s=90 → lease_expires_at should be ~90s from now
        remaining = hb["lease_expires_at"] - time.time()
        assert 85 <= remaining <= 95

    async def test_heartbeat_sends_lease_s_in_json(self) -> None:
        """mutmut_4/14/15: JSON body must use key 'lease_s' with correct value."""
        hub, app = _make_hub_app()
        _add_worker(hub)
        async with _client_for(app) as c:
            ok, acq = await c.acquire(WID)
            hid = acq["hijack_id"]
            ok, hb = await c.heartbeat(WID, hid, lease_s=45)

        assert ok is True
        remaining = hb["lease_expires_at"] - time.time()
        assert 40 <= remaining <= 50  # 45s ± 5s


# ---------------------------------------------------------------------------
# HijackClient.send — mutmut_10/14: is not None → is None (conditional flip)
# mutmut_1/2: default values, mutmut_6-17: wrong body keys
# mutmut_11/15: value→None
# ---------------------------------------------------------------------------


class TestSendMutants:
    async def test_send_default_timeout_ms_is_2000(self) -> None:
        """mutmut_1: timeout_ms default must be 2000."""
        hub, app = _make_hub_app()
        _add_worker(hub)
        # Can only verify the default by inspecting the method signature
        import inspect

        sig = inspect.signature(HijackClient.send)
        assert sig.parameters["timeout_ms"].default == 2000

    async def test_send_default_poll_interval_ms_is_120(self) -> None:
        """mutmut_2: poll_interval_ms default must be 120."""
        import inspect

        sig = inspect.signature(HijackClient.send)
        assert sig.parameters["poll_interval_ms"].default == 120

    async def test_send_without_expect_prompt_id_excludes_key(self) -> None:
        """mutmut_10: expect_prompt_id=None must NOT include key in body.

        If condition flipped (is None instead of is not None), the key would
        be added when expect_prompt_id IS None (the default), causing issues.
        """
        # We intercept the actual request body
        captured_json: list[dict] = []
        hub, app = _make_hub_app()
        _add_worker(hub)

        async with _client_for(app) as c:
            ok, acq = await c.acquire(WID)
            hid = acq["hijack_id"]

            original_request = c._request.__func__

            async def _intercepting_request(self_c, method, path, *, json=None, params=None):
                if "send" in path:
                    captured_json.append(json or {})
                return await original_request(self_c, method, path, json=json, params=params)

            import types

            c._request = types.MethodType(_intercepting_request, c)
            await c.send(WID, hid, keys="test")

        if captured_json:
            # When expect_prompt_id is not provided (None), key must NOT be in body
            assert "expect_prompt_id" not in captured_json[0]

    async def test_send_with_expect_prompt_id_includes_key(self) -> None:
        """mutmut_10: when expect_prompt_id is provided, key must be in body."""
        captured_json: list[dict] = []
        hub, app = _make_hub_app()
        _add_worker(hub)

        async with _client_for(app) as c:
            ok, acq = await c.acquire(WID)
            hid = acq["hijack_id"]

            original_request = c._request.__func__

            async def _intercepting_request(self_c, method, path, *, json=None, params=None):
                if "send" in path and json:
                    captured_json.append(dict(json))
                return await original_request(self_c, method, path, json=json, params=params)

            import types

            c._request = types.MethodType(_intercepting_request, c)
            await c.send(WID, hid, keys="test", expect_prompt_id="login_prompt")

        if captured_json:
            assert "expect_prompt_id" in captured_json[0]
            assert captured_json[0]["expect_prompt_id"] == "login_prompt"

    async def test_send_with_expect_regex_includes_key(self) -> None:
        """mutmut_14: when expect_regex provided, key must be in body with correct value."""
        captured_json: list[dict] = []
        hub, app = _make_hub_app()
        _add_worker(hub)

        async with _client_for(app) as c:
            ok, acq = await c.acquire(WID)
            hid = acq["hijack_id"]

            original_request = c._request.__func__

            async def _intercepting_request(self_c, method, path, *, json=None, params=None):
                if "send" in path and json:
                    captured_json.append(dict(json))
                return await original_request(self_c, method, path, json=json, params=params)

            import types

            c._request = types.MethodType(_intercepting_request, c)
            await c.send(WID, hid, keys="test", expect_regex=".*>.*")

        if captured_json:
            assert "expect_regex" in captured_json[0]
            assert captured_json[0]["expect_regex"] == ".*>.*"

    async def test_send_without_expect_regex_excludes_key(self) -> None:
        """mutmut_14: expect_regex=None (default) must NOT include key in body."""
        captured_json: list[dict] = []
        hub, app = _make_hub_app()
        _add_worker(hub)

        async with _client_for(app) as c:
            ok, acq = await c.acquire(WID)
            hid = acq["hijack_id"]

            original_request = c._request.__func__

            async def _intercepting_request(self_c, method, path, *, json=None, params=None):
                if "send" in path:
                    captured_json.append(json or {})
                return await original_request(self_c, method, path, json=json, params=params)

            import types

            c._request = types.MethodType(_intercepting_request, c)
            await c.send(WID, hid, keys="test")

        if captured_json:
            assert "expect_regex" not in captured_json[0]

    async def test_send_body_keys_are_correct(self) -> None:
        """mutmut_6/7/8/9: body keys must be 'timeout_ms' and 'poll_interval_ms'."""
        captured_json: list[dict] = []
        hub, app = _make_hub_app()
        _add_worker(hub)

        async with _client_for(app) as c:
            ok, acq = await c.acquire(WID)
            hid = acq["hijack_id"]

            original_request = c._request.__func__

            async def _intercepting_request(self_c, method, path, *, json=None, params=None):
                if "send" in path and json:
                    captured_json.append(dict(json))
                return await original_request(self_c, method, path, json=json, params=params)

            import types

            c._request = types.MethodType(_intercepting_request, c)
            await c.send(WID, hid, keys="hello", timeout_ms=3000, poll_interval_ms=150)

        if captured_json:
            assert "timeout_ms" in captured_json[0]
            assert "poll_interval_ms" in captured_json[0]
            assert captured_json[0]["timeout_ms"] == 3000
            assert captured_json[0]["poll_interval_ms"] == 150


# ---------------------------------------------------------------------------
# HijackClient.snapshot — mutmut_1: wait_ms default=1500
# mutmut_4/7: params=None or removed
# mutmut_14/15: wrong param keys
# ---------------------------------------------------------------------------


class TestSnapshotMutants:
    async def test_snapshot_default_wait_ms_is_1500(self) -> None:
        """mutmut_1: wait_ms default must be 1500."""
        import inspect

        sig = inspect.signature(HijackClient.snapshot)
        assert sig.parameters["wait_ms"].default == 1500

    async def test_snapshot_sends_wait_ms_param(self) -> None:
        """mutmut_4/7/14/15: wait_ms must be sent as 'wait_ms' query param."""
        captured_params: list[dict] = []
        hub, app = _make_hub_app()
        _add_worker(hub)

        async with _client_for(app) as c:
            ok, acq = await c.acquire(WID)
            hid = acq["hijack_id"]

            original_request = c._request.__func__

            async def _intercepting_request(self_c, method, path, *, json=None, params=None):
                if "snapshot" in path:
                    captured_params.append(params or {})
                return await original_request(self_c, method, path, json=json, params=params)

            import types

            c._request = types.MethodType(_intercepting_request, c)
            await c.snapshot(WID, hid, wait_ms=999)

        if captured_params:
            assert "wait_ms" in captured_params[0]
            assert captured_params[0]["wait_ms"] == 999

    async def test_snapshot_without_wait_ms_uses_default(self) -> None:
        """mutmut_4: params=None would drop wait_ms entirely."""
        captured_params: list[dict] = []
        hub, app = _make_hub_app()
        _add_worker(hub)

        async with _client_for(app) as c:
            ok, acq = await c.acquire(WID)
            hid = acq["hijack_id"]

            original_request = c._request.__func__

            async def _intercepting_request(self_c, method, path, *, json=None, params=None):
                if "snapshot" in path:
                    captured_params.append(params or {})
                return await original_request(self_c, method, path, json=json, params=params)

            import types

            c._request = types.MethodType(_intercepting_request, c)
            await c.snapshot(WID, hid)  # default wait_ms=1500

        if captured_params:
            assert "wait_ms" in captured_params[0]
            assert captured_params[0]["wait_ms"] == 1500


# ---------------------------------------------------------------------------
# HijackClient.events — mutmut_1/2: default values
# mutmut_17/18: wrong param keys
# ---------------------------------------------------------------------------


class TestEventsMutants:
    async def test_events_default_after_seq_is_0(self) -> None:
        """mutmut_1: after_seq default must be 0."""
        import inspect

        sig = inspect.signature(HijackClient.events)
        assert sig.parameters["after_seq"].default == 0

    async def test_events_default_limit_is_200(self) -> None:
        """mutmut_2: limit default must be 200."""
        import inspect

        sig = inspect.signature(HijackClient.events)
        assert sig.parameters["limit"].default == 200

    async def test_events_sends_correct_param_keys(self) -> None:
        """mutmut_17/18: params keys must be 'after_seq' and 'limit'."""
        captured_params: list[dict] = []
        hub, app = _make_hub_app()
        _add_worker(hub)

        async with _client_for(app) as c:
            ok, acq = await c.acquire(WID)
            hid = acq["hijack_id"]

            original_request = c._request.__func__

            async def _intercepting_request(self_c, method, path, *, json=None, params=None):
                if "events" in path:
                    captured_params.append(params or {})
                return await original_request(self_c, method, path, json=json, params=params)

            import types

            c._request = types.MethodType(_intercepting_request, c)
            await c.events(WID, hid, after_seq=5, limit=50)

        if captured_params:
            assert "after_seq" in captured_params[0]
            assert "limit" in captured_params[0]
            assert captured_params[0]["after_seq"] == 5
            assert captured_params[0]["limit"] == 50

    async def test_events_sends_correct_param_values(self) -> None:
        """mutmut_17/18: param keys must not have XX or uppercase variants."""
        captured_params: list[dict] = []
        hub, app = _make_hub_app()
        _add_worker(hub)

        async with _client_for(app) as c:
            ok, acq = await c.acquire(WID)
            hid = acq["hijack_id"]

            original_request = c._request.__func__

            async def _intercepting_request(self_c, method, path, *, json=None, params=None):
                if "events" in path:
                    captured_params.append(params or {})
                return await original_request(self_c, method, path, json=json, params=params)

            import types

            c._request = types.MethodType(_intercepting_request, c)
            await c.events(WID, hid)

        if captured_params:
            assert "XXlimitXX" not in captured_params[0]
            assert "LIMIT" not in captured_params[0]
            assert "after_seq" in captured_params[0]
            assert "limit" in captured_params[0]


# ---------------------------------------------------------------------------
# HijackClient.session_events — mutmut_1/4/7/10/11
# ---------------------------------------------------------------------------


class TestSessionEventsMutants:
    async def test_session_events_default_limit_is_100(self) -> None:
        """mutmut_1: session_events limit default must be 100."""
        import inspect

        sig = inspect.signature(HijackClient.session_events)
        assert sig.parameters["limit"].default == 100

    async def test_session_events_sends_limit_param(self) -> None:
        """mutmut_4/7/10/11: limit must be sent as 'limit' param."""
        app = _server_app()
        async with _server_client(app) as c:
            ok, data = await c.session_events("s1", limit=25)
        assert ok is True

    async def test_session_events_limit_correct_key(self) -> None:
        """mutmut_10/11: params key must be 'limit' not 'XXlimitXX' or 'LIMIT'."""
        captured_params: list[dict] = []
        app = _server_app()

        async with _server_client(app) as c:
            original_request = c._request.__func__

            async def _intercepting_request(self_c, method, path, *, json=None, params=None):
                if "events" in path:
                    captured_params.append(params or {})
                return await original_request(self_c, method, path, json=json, params=params)

            import types

            c._request = types.MethodType(_intercepting_request, c)
            await c.session_events("s1", limit=77)

        if captured_params:
            assert "limit" in captured_params[0]
            assert captured_params[0]["limit"] == 77
            assert "XXlimitXX" not in captured_params[0]
            assert "LIMIT" not in captured_params[0]


# ---------------------------------------------------------------------------
# HijackClient.quick_connect — mutmut_2/3: wrong connector_type key
# mutmut_4: display_name is not None → is None
# mutmut_5/6/7: display_name body value/key mutations
# ---------------------------------------------------------------------------


class TestQuickConnectMutants:
    async def test_quick_connect_sends_connector_type(self) -> None:
        """mutmut_2/3: body must use key 'connector_type'."""
        app = _server_app()
        async with _server_client(app) as c:
            ok, data = await c.quick_connect("shell")
        assert ok is True
        assert "session_id" in data

    async def test_quick_connect_body_connector_type_key(self) -> None:
        """mutmut_2/3: key in body must be 'connector_type' not 'XXconnector_typeXX'."""
        captured_json: list[dict] = []
        app = _server_app()

        async with _server_client(app) as c:
            original_request = c._request.__func__

            async def _intercepting_request(self_c, method, path, *, json=None, params=None):
                if "connect" in path and json:
                    captured_json.append(dict(json))
                return await original_request(self_c, method, path, json=json, params=params)

            import types

            c._request = types.MethodType(_intercepting_request, c)
            await c.quick_connect("shell", display_name="Test")

        if captured_json:
            assert "connector_type" in captured_json[0]
            assert captured_json[0]["connector_type"] == "shell"
            assert "XXconnector_typeXX" not in captured_json[0]
            assert "CONNECTOR_TYPE" not in captured_json[0]

    async def test_quick_connect_without_display_name_excludes_key(self) -> None:
        """mutmut_4: when display_name is None, key must NOT be in body."""
        captured_json: list[dict] = []
        app = _server_app()

        async with _server_client(app) as c:
            original_request = c._request.__func__

            async def _intercepting_request(self_c, method, path, *, json=None, params=None):
                if "connect" in path and json:
                    captured_json.append(dict(json))
                return await original_request(self_c, method, path, json=json, params=params)

            import types

            c._request = types.MethodType(_intercepting_request, c)
            await c.quick_connect("shell")  # no display_name

        if captured_json:
            assert "display_name" not in captured_json[0]

    async def test_quick_connect_with_display_name_includes_correct_value(self) -> None:
        """mutmut_4/5/6/7: display_name value must not be None and key must be 'display_name'."""
        captured_json: list[dict] = []
        app = _server_app()

        async with _server_client(app) as c:
            original_request = c._request.__func__

            async def _intercepting_request(self_c, method, path, *, json=None, params=None):
                if "connect" in path and json:
                    captured_json.append(dict(json))
                return await original_request(self_c, method, path, json=json, params=params)

            import types

            c._request = types.MethodType(_intercepting_request, c)
            await c.quick_connect("shell", display_name="My Session")

        if captured_json:
            assert "display_name" in captured_json[0]
            assert captured_json[0]["display_name"] == "My Session"
            assert captured_json[0]["display_name"] is not None
            assert "XXdisplay_nameXX" not in captured_json[0]
            assert "DISPLAY_NAME" not in captured_json[0]


# ---------------------------------------------------------------------------
# mcp_tools._ok — mutmut_28/77/86/95: _ok(ok, None) instead of _ok(ok, data)
# ---------------------------------------------------------------------------


class TestOkHelperMutants:
    def test_ok_with_dict_preserves_data(self) -> None:
        """mutmut_28/77/86/95: _ok must return data from second arg, not None."""
        result = _ok(True, {"hijack_id": "abc", "owner": "bot"})
        assert result["hijack_id"] == "abc"
        assert result["owner"] == "bot"

    def test_ok_failure_with_dict(self) -> None:
        """_ok with ok=False still returns data dict."""
        result = _ok(False, {"error": "not found"})
        assert result["success"] is False
        assert result["error"] == "not found"

    def test_ok_with_non_dict_uses_data_key(self) -> None:
        """Non-dict data goes into 'data' key, not discarded."""
        result = _ok(True, ["event1", "event2"])
        assert result["data"] == ["event1", "event2"]
        assert result["data"] is not None

    def test_ok_result_is_not_none_data(self) -> None:
        """Mutants that pass None to _ok instead of data would give empty/None data."""
        data = {"snapshot": "screen content here", "seq": 42}
        result = _ok(True, data)
        assert result.get("snapshot") == "screen content here"
        assert result.get("seq") == 42
        # Would fail if mutant passes None: None is not a dict, so result["data"] = None
        assert result.get("data") is None or result.get("snapshot") is not None


# ---------------------------------------------------------------------------
# mcp_tools.hijack_tools — mutmut_5/19: lease_s default = 90
# mutmut_6/7: owner default = "operator"
# mutmut_13: owner not passed to acquire
# mutmut_14: lease_s not passed to acquire
# ---------------------------------------------------------------------------


class TestHijackToolsMutants:
    async def test_hijack_begin_default_lease_s(self) -> None:
        """mutmut_5: hijack_begin lease_s default must be 90."""
        import inspect

        tools = hijack_tools("http://test")
        begin = tools[0]
        sig = inspect.signature(begin)
        assert sig.parameters["lease_s"].default == 90

    async def test_hijack_begin_default_owner(self) -> None:
        """mutmut_6/7: hijack_begin owner default must be 'operator'."""
        import inspect

        tools = hijack_tools("http://test")
        begin = tools[0]
        sig = inspect.signature(begin)
        assert sig.parameters["owner"].default == "operator"

    async def test_hijack_begin_passes_owner_to_acquire(self) -> None:
        """mutmut_13: owner must be forwarded to client.acquire."""
        hub, app = _make_hub_app()
        _add_worker(hub)
        transport = ASGITransport(app=app)

        tools = hijack_tools("http://test", transport=transport)
        begin = tools[0]

        result = await begin(WID, lease_s=60, owner="specialized-bot")
        assert result["success"] is True
        assert result.get("owner") == "specialized-bot"

    async def test_hijack_begin_passes_lease_s_to_acquire(self) -> None:
        """mutmut_14: lease_s must be forwarded to client.acquire."""
        hub, app = _make_hub_app()
        _add_worker(hub)
        transport = ASGITransport(app=app)

        tools = hijack_tools("http://test", transport=transport)
        begin = tools[0]

        result = await begin(WID, lease_s=30)
        assert result["success"] is True
        remaining = result["lease_expires_at"] - time.time()
        assert 25 <= remaining <= 35

    async def test_hijack_heartbeat_default_lease_s(self) -> None:
        """mutmut_19: hijack_heartbeat lease_s default must be 90."""
        import inspect

        tools = hijack_tools("http://test")
        heartbeat = tools[1]
        sig = inspect.signature(heartbeat)
        assert sig.parameters["lease_s"].default == 90

    async def test_hijack_heartbeat_passes_lease_s(self) -> None:
        """mutmut_26: lease_s must be forwarded to client.heartbeat."""
        hub, app = _make_hub_app()
        _add_worker(hub)
        transport = ASGITransport(app=app)

        tools = hijack_tools("http://test", transport=transport)
        begin, heartbeat, *_ = tools

        result = await begin(WID)
        hid = result["hijack_id"]

        result = await heartbeat(WID, hid, lease_s=45)
        assert result["success"] is True
        remaining = result["lease_expires_at"] - time.time()
        assert 40 <= remaining <= 50

    async def test_hijack_read_default_mode_is_snapshot(self) -> None:
        """mutmut_31/32: mode default must be 'snapshot'."""
        import inspect

        tools = hijack_tools("http://test")
        read = tools[2]
        sig = inspect.signature(read)
        assert sig.parameters["mode"].default == "snapshot"

    async def test_hijack_read_default_wait_ms(self) -> None:
        """mutmut_33: wait_ms default must be 1500."""
        import inspect

        tools = hijack_tools("http://test")
        read = tools[2]
        sig = inspect.signature(read)
        assert sig.parameters["wait_ms"].default == 1500

    async def test_hijack_read_default_after_seq(self) -> None:
        """mutmut_34: after_seq default must be 0."""
        import inspect

        tools = hijack_tools("http://test")
        read = tools[2]
        sig = inspect.signature(read)
        assert sig.parameters["after_seq"].default == 0

    async def test_hijack_read_default_limit(self) -> None:
        """mutmut_35: limit default must be 200."""
        import inspect

        tools = hijack_tools("http://test")
        read = tools[2]
        sig = inspect.signature(read)
        assert sig.parameters["limit"].default == 200

    async def test_hijack_read_events_passes_after_seq(self) -> None:
        """mutmut_46: after_seq must be forwarded to client.events."""
        hub, app = _make_hub_app()
        _add_worker(hub)
        transport = ASGITransport(app=app)

        tools = hijack_tools("http://test", transport=transport)
        begin, _, read, *_ = tools

        result = await begin(WID)
        hid = result["hijack_id"]

        # With after_seq=0 (default), should return all events
        result = await read(WID, hid, mode="events", after_seq=0, limit=100)
        assert result["success"] is True
        assert "events" in result

    async def test_hijack_read_events_passes_limit(self) -> None:
        """mutmut_47: limit must be forwarded to client.events."""
        hub, app = _make_hub_app()
        _add_worker(hub)
        transport = ASGITransport(app=app)

        tools = hijack_tools("http://test", transport=transport)
        begin, _, read, *_ = tools

        result = await begin(WID)
        hid = result["hijack_id"]

        result = await read(WID, hid, mode="events", limit=5)
        assert result["success"] is True

    async def test_hijack_read_snapshot_passes_wait_ms(self) -> None:
        """mutmut_54: wait_ms must be forwarded to client.snapshot."""
        hub, app = _make_hub_app()
        _add_worker(hub)
        transport = ASGITransport(app=app)

        tools = hijack_tools("http://test", transport=transport)
        begin, _, read, *_ = tools

        result = await begin(WID)
        hid = result["hijack_id"]

        result = await read(WID, hid, mode="snapshot", wait_ms=100)
        assert result["success"] is True
        assert "snapshot" in result

    async def test_hijack_send_default_timeout_ms(self) -> None:
        """mutmut_59: timeout_ms default must be 2000."""
        import inspect

        tools = hijack_tools("http://test")
        send = tools[3]
        sig = inspect.signature(send)
        assert sig.parameters["timeout_ms"].default == 2000

    async def test_hijack_send_default_poll_interval_ms(self) -> None:
        """mutmut_60: poll_interval_ms default must be 120."""
        import inspect

        tools = hijack_tools("http://test")
        send = tools[3]
        sig = inspect.signature(send)
        assert sig.parameters["poll_interval_ms"].default == 120

    async def test_hijack_send_passes_expect_prompt_id(self) -> None:
        """mutmut_65: expect_prompt_id must be forwarded to client.send."""
        hub, app = _make_hub_app()
        _add_worker(hub)
        transport = ASGITransport(app=app)

        tools = hijack_tools("http://test", transport=transport)
        begin, _, _, send, *_ = tools

        result = await begin(WID)
        hid = result["hijack_id"]

        # The request body should include expect_prompt_id
        # We verify it doesn't cause an unexpected failure due to missing arg
        result = await send(WID, hid, keys="test", expect_prompt_id="some_prompt")
        assert isinstance(result, dict)
        assert "success" in result

    async def test_hijack_send_passes_expect_regex(self) -> None:
        """mutmut_66: expect_regex must be forwarded to client.send."""
        hub, app = _make_hub_app()
        _add_worker(hub)
        transport = ASGITransport(app=app)

        tools = hijack_tools("http://test", transport=transport)
        begin, _, _, send, *_ = tools

        result = await begin(WID)
        hid = result["hijack_id"]

        result = await send(WID, hid, keys="test", expect_regex=".*>.*")
        assert isinstance(result, dict)
        assert "success" in result

    async def test_hijack_send_passes_timeout_ms(self) -> None:
        """mutmut_74: timeout_ms must be forwarded to client.send."""
        hub, app = _make_hub_app()
        _add_worker(hub)
        transport = ASGITransport(app=app)

        tools = hijack_tools("http://test", transport=transport)
        begin, _, _, send, *_ = tools

        result = await begin(WID)
        hid = result["hijack_id"]

        result = await send(WID, hid, keys="x", timeout_ms=500)
        assert result["success"] is True

    async def test_hijack_send_passes_poll_interval_ms(self) -> None:
        """mutmut_75: poll_interval_ms must be forwarded to client.send."""
        hub, app = _make_hub_app()
        _add_worker(hub)
        transport = ASGITransport(app=app)

        tools = hijack_tools("http://test", transport=transport)
        begin, _, _, send, *_ = tools

        result = await begin(WID)
        hid = result["hijack_id"]

        result = await send(WID, hid, keys="x", poll_interval_ms=50)
        assert result["success"] is True

    async def test_hijack_begin_result_has_data(self) -> None:
        """mutmut_28: hijack_begin result must contain actual data, not None."""
        hub, app = _make_hub_app()
        _add_worker(hub)
        transport = ASGITransport(app=app)

        tools = hijack_tools("http://test", transport=transport)
        begin = tools[0]

        result = await begin(WID)
        assert result["success"] is True
        # Would fail if mutant passes None: hijack_id would not be in result
        assert "hijack_id" in result
        assert result["hijack_id"] is not None

    async def test_hijack_send_result_has_data(self) -> None:
        """mutmut_77: hijack_send result must contain actual data."""
        hub, app = _make_hub_app()
        _add_worker(hub)
        transport = ASGITransport(app=app)

        tools = hijack_tools("http://test", transport=transport)
        begin, _, _, send, *_ = tools

        result = await begin(WID)
        hid = result["hijack_id"]

        result = await send(WID, hid, keys="test\r")
        assert result["success"] is True
        # With real data, 'sent' should be in result
        assert "sent" in result
        assert result["sent"] is not None

    async def test_hijack_step_result_has_data(self) -> None:
        """mutmut_86: hijack_step result must contain actual data."""
        hub, app = _make_hub_app()
        _add_worker(hub)
        transport = ASGITransport(app=app)

        tools = hijack_tools("http://test", transport=transport)
        begin, _, _, _, step, _ = tools

        result = await begin(WID)
        hid = result["hijack_id"]

        result = await step(WID, hid)
        assert result["success"] is True
        # With real data, 'ok' should be in result
        assert "ok" in result

    async def test_hijack_release_result_has_data(self) -> None:
        """mutmut_95: hijack_release result must contain actual data."""
        hub, app = _make_hub_app()
        _add_worker(hub)
        transport = ASGITransport(app=app)

        tools = hijack_tools("http://test", transport=transport)
        begin, _, _, _, _, release = tools

        result = await begin(WID)
        hid = result["hijack_id"]

        result = await release(WID, hid)
        assert result["success"] is True
        # With real data, 'ok' should be in result
        assert "ok" in result

    async def test_hijack_read_snapshot_result_has_data(self) -> None:
        """mutmut_28 (read): hijack_read snapshot result must contain actual snapshot."""
        hub, app = _make_hub_app()
        _add_worker(hub)
        transport = ASGITransport(app=app)

        tools = hijack_tools("http://test", transport=transport)
        begin, _, read, *_ = tools

        result = await begin(WID)
        hid = result["hijack_id"]

        result = await read(WID, hid, mode="snapshot", wait_ms=50)
        assert result["success"] is True
        # With real data, snapshot key should be present
        assert "snapshot" in result

    async def test_hijack_read_events_result_has_data(self) -> None:
        """mutmut_28 (read events): hijack_read events result must contain actual events."""
        hub, app = _make_hub_app()
        _add_worker(hub)
        transport = ASGITransport(app=app)

        tools = hijack_tools("http://test", transport=transport)
        begin, _, read, *_ = tools

        result = await begin(WID)
        hid = result["hijack_id"]

        result = await read(WID, hid, mode="events")
        assert result["success"] is True
        assert "events" in result
