#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Tests for undef.terminal.shell._commands — CommandDispatcher."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from undef.terminal.shell._commands import CommandDispatcher


def make_dispatcher(ctx: dict[str, Any] | None = None) -> CommandDispatcher:
    return CommandDispatcher(ctx or {})


def first_data(frames: list[dict]) -> str:
    return frames[0]["data"]


# ---------------------------------------------------------------------------
# dispatch — basic routing
# ---------------------------------------------------------------------------


async def test_dispatch_empty_line():
    d = make_dispatcher()
    frames = await d.dispatch("")
    assert frames[0]["data"].endswith(" ")  # PROMPT ends with space


async def test_dispatch_ctrl_c():
    d = make_dispatcher()
    frames = await d.dispatch("\x03")
    assert len(frames) == 1


async def test_dispatch_exit():
    d = make_dispatcher()
    frames = await d.dispatch("exit")
    assert "Goodbye" in first_data(frames)


async def test_dispatch_quit():
    d = make_dispatcher()
    frames = await d.dispatch("quit")
    assert "Goodbye" in first_data(frames)


async def test_dispatch_ctrl_d():
    d = make_dispatcher()
    frames = await d.dispatch("\x04")
    assert "Goodbye" in first_data(frames)


async def test_dispatch_help():
    d = make_dispatcher()
    frames = await d.dispatch("help")
    assert "ushell commands" in first_data(frames)


async def test_dispatch_clear():
    d = make_dispatcher()
    frames = await d.dispatch("clear")
    # clear screen escape
    assert "\x1b[2J" in first_data(frames)


async def test_dispatch_unknown_command():
    d = make_dispatcher()
    frames = await d.dispatch("bogus")
    assert "unknown command" in first_data(frames)


async def test_dispatch_case_insensitive():
    d = make_dispatcher()
    frames = await d.dispatch("HELP")
    assert "ushell commands" in first_data(frames)


async def test_dispatch_strips_whitespace():
    d = make_dispatcher()
    frames = await d.dispatch("  help  ")
    assert "ushell commands" in first_data(frames)


# ---------------------------------------------------------------------------
# py command
# ---------------------------------------------------------------------------


async def test_cmd_py_no_arg():
    d = make_dispatcher()
    frames = await d.dispatch("py")
    assert "usage: py" in first_data(frames)


async def test_cmd_py_expression():
    d = make_dispatcher()
    frames = await d.dispatch("py 2+2")
    assert "4" in first_data(frames)


async def test_cmd_py_no_output_shows_ok():
    d = make_dispatcher()
    frames = await d.dispatch("py None")
    assert "ok" in first_data(frames)


async def test_cmd_py_statement():
    d = make_dispatcher()
    frames = await d.dispatch("py x = 5")
    # assignment → no result, shows "ok"
    assert "ok" in first_data(frames)


# ---------------------------------------------------------------------------
# sessions command
# ---------------------------------------------------------------------------


async def test_cmd_sessions_no_list_fn():
    d = make_dispatcher()
    frames = await d.dispatch("sessions")
    assert "not available" in first_data(frames)


async def test_cmd_sessions_empty():
    async def list_fn():
        return []

    d = make_dispatcher({"list_kv_sessions": list_fn})
    frames = await d.dispatch("sessions")
    assert "no sessions" in first_data(frames)


async def test_cmd_sessions_with_data():
    async def list_fn():
        return [
            {"session_id": "s1", "lifecycle_state": "running", "connector_type": "shell", "connected": True},
            {"session_id": "s2", "lifecycle_state": "idle", "connector_type": "telnet", "connected": False},
        ]

    d = make_dispatcher({"list_kv_sessions": list_fn})
    frames = await d.dispatch("sessions")
    data = first_data(frames)
    assert "s1" in data
    assert "live" in data
    assert "idle" in data


async def test_cmd_sessions_exception():
    async def list_fn():
        raise RuntimeError("kv error")

    d = make_dispatcher({"list_kv_sessions": list_fn})
    frames = await d.dispatch("sessions")
    assert "kv error" in first_data(frames)


async def test_cmd_sessions_missing_fields():
    async def list_fn():
        return [{}]  # all fields missing → defaults to "?"

    d = make_dispatcher({"list_kv_sessions": list_fn})
    frames = await d.dispatch("sessions")
    assert "?" in first_data(frames)


# ---------------------------------------------------------------------------
# kv command
# ---------------------------------------------------------------------------


def make_kv_ctx(kv: Any) -> dict:
    env = SimpleNamespace(SESSION_REGISTRY=kv)
    return {"env": env}


async def test_cmd_kv_no_env():
    d = make_dispatcher()
    frames = await d.dispatch("kv list")
    assert "not available" in first_data(frames)


async def test_cmd_kv_env_without_session_registry():
    env = SimpleNamespace()  # no SESSION_REGISTRY attr
    d = make_dispatcher({"env": env})
    frames = await d.dispatch("kv list")
    assert "not available" in first_data(frames)


async def test_cmd_kv_list_with_keys_as_dicts():
    kv = AsyncMock()
    result = MagicMock()
    result.keys = [{"name": "session:abc"}, {"name": "session:def"}]
    kv.list = AsyncMock(return_value=result)
    d = make_dispatcher(make_kv_ctx(kv))
    frames = await d.dispatch("kv list")
    data = first_data(frames)
    assert "session:abc" in data


async def test_cmd_kv_list_with_keys_as_objects():
    kv = AsyncMock()
    result = MagicMock()
    key_obj = SimpleNamespace(name="session:xyz")
    result.keys = [key_obj]
    kv.list = AsyncMock(return_value=result)
    d = make_dispatcher(make_kv_ctx(kv))
    frames = await d.dispatch("kv list")
    assert "session:xyz" in first_data(frames)


async def test_cmd_kv_list_keys_as_plain_strings():
    kv = AsyncMock()
    result = MagicMock()
    # Object without .name — falls back to str(k)
    result.keys = ["session:plain"]
    # hasattr(result, 'keys') is True (it's an attribute)
    kv.list = AsyncMock(return_value=result)
    d = make_dispatcher(make_kv_ctx(kv))
    frames = await d.dispatch("kv list")
    assert "session:plain" in first_data(frames)


async def test_cmd_kv_list_empty():
    kv = AsyncMock()
    result = MagicMock()
    result.keys = []
    kv.list = AsyncMock(return_value=result)
    d = make_dispatcher(make_kv_ctx(kv))
    frames = await d.dispatch("kv list")
    assert "no keys" in first_data(frames)


async def test_cmd_kv_list_exception():
    kv = AsyncMock()
    kv.list = AsyncMock(side_effect=Exception("list error"))
    d = make_dispatcher(make_kv_ctx(kv))
    frames = await d.dispatch("kv list")
    assert "list error" in first_data(frames)


async def test_cmd_kv_list_result_as_dict():
    # result without .keys attr — falls back to result.get("keys", [])
    # Use a MagicMock that returns False for hasattr(..., "keys")
    kv = AsyncMock()
    result = MagicMock(spec=[])  # spec=[] means no attributes, so hasattr(result, "keys") is False
    result.get = MagicMock(return_value=[{"name": "session:dictkey"}])
    kv.list = AsyncMock(return_value=result)
    d = make_dispatcher(make_kv_ctx(kv))
    frames = await d.dispatch("kv list")
    assert "session:dictkey" in first_data(frames)


async def test_cmd_kv_get_no_key():
    kv = AsyncMock()
    d = make_dispatcher(make_kv_ctx(kv))
    frames = await d.dispatch("kv get")
    assert "usage: kv get" in first_data(frames)


async def test_cmd_kv_get_with_prefix():
    kv = AsyncMock()
    kv.get = AsyncMock(return_value="some_value")
    d = make_dispatcher(make_kv_ctx(kv))
    frames = await d.dispatch("kv get session:mykey")
    data = first_data(frames)
    assert "some_value" in data
    assert "session:mykey" in data


async def test_cmd_kv_get_without_prefix():
    kv = AsyncMock()
    kv.get = AsyncMock(return_value="val")
    d = make_dispatcher(make_kv_ctx(kv))
    await d.dispatch("kv get mykey")
    # should prepend session:
    kv.get.assert_called_once_with("session:mykey")


async def test_cmd_kv_get_missing_key():
    kv = AsyncMock()
    kv.get = AsyncMock(return_value=None)
    d = make_dispatcher(make_kv_ctx(kv))
    frames = await d.dispatch("kv get missing")
    assert "key not found" in first_data(frames)


async def test_cmd_kv_get_exception():
    kv = AsyncMock()
    kv.get = AsyncMock(side_effect=Exception("get error"))
    d = make_dispatcher(make_kv_ctx(kv))
    frames = await d.dispatch("kv get mykey")
    assert "get error" in first_data(frames)


async def test_cmd_kv_invalid_subcommand():
    kv = AsyncMock()
    d = make_dispatcher(make_kv_ctx(kv))
    frames = await d.dispatch("kv foo")
    assert "usage: kv list" in first_data(frames)


async def test_cmd_kv_no_subcommand():
    kv = AsyncMock()
    d = make_dispatcher(make_kv_ctx(kv))
    frames = await d.dispatch("kv")
    assert "usage: kv list" in first_data(frames)


# ---------------------------------------------------------------------------
# fetch command
# ---------------------------------------------------------------------------


async def test_cmd_fetch_no_url():
    d = make_dispatcher()
    frames = await d.dispatch("fetch")
    assert "usage: fetch" in first_data(frames)


async def test_cmd_fetch_urllib_success():
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = b"Hello world"
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        d = make_dispatcher()
        frames = await d.dispatch("fetch http://example.com")
    data = first_data(frames)
    assert "HTTP 200" in data
    assert "Hello world" in data


async def test_cmd_fetch_urllib_4xx():
    mock_response = MagicMock()
    mock_response.status = 404
    mock_response.read.return_value = b"Not Found"
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        d = make_dispatcher()
        frames = await d.dispatch("fetch http://example.com/missing")
    data = first_data(frames)
    assert "HTTP 404" in data


async def test_cmd_fetch_urllib_5xx():
    mock_response = MagicMock()
    mock_response.status = 500
    mock_response.read.return_value = b"Server Error"
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        d = make_dispatcher()
        frames = await d.dispatch("fetch http://example.com/error")
    data = first_data(frames)
    assert "HTTP 500" in data


async def test_cmd_fetch_body_truncated():
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = b"X" * 900
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        d = make_dispatcher()
        frames = await d.dispatch("fetch http://example.com/big")
    data = first_data(frames)
    assert "…" in data


async def test_cmd_fetch_exception():
    with patch("urllib.request.urlopen", side_effect=Exception("connection refused")):
        d = make_dispatcher()
        frames = await d.dispatch("fetch http://badhost")
    assert "connection refused" in first_data(frames)


async def test_cmd_fetch_js_fetch_path():
    """Cover the js.fetch branch by injecting a fake 'js' module."""
    import sys
    import types

    fake_resp = MagicMock()
    fake_resp.status = 200

    # Make .text() an async callable
    async def fake_text():
        return "js-body"

    fake_resp.text = fake_text

    async def fake_fetch(url):
        return fake_resp

    fake_js = types.ModuleType("js")
    fake_js.fetch = fake_fetch
    sys.modules["js"] = fake_js
    try:
        d = make_dispatcher()
        frames = await d.dispatch("fetch http://example.com")
        data = first_data(frames)
        assert "HTTP 200" in data
        assert "js-body" in data
    finally:
        del sys.modules["js"]


# ---------------------------------------------------------------------------
# env command
# ---------------------------------------------------------------------------


async def test_cmd_env_no_env():
    d = make_dispatcher({"my_key": "val"})
    frames = await d.dispatch("env")
    assert "my_key" in first_data(frames)


async def test_cmd_env_with_env_object():
    env = SimpleNamespace(SESSION_REGISTRY=object(), _private="hidden")
    d = make_dispatcher({"env": env})
    frames = await d.dispatch("env")
    data = first_data(frames)
    assert "SESSION_REGISTRY" in data
    assert "_private" not in data


async def test_cmd_env_empty_ctx():
    d = make_dispatcher({})
    frames = await d.dispatch("env")
    assert "(empty context)" in first_data(frames)


async def test_cmd_env_with_env_no_public_attrs():
    # env object with only private attrs → shows context heading with no lines → empty context? No:
    # lines would be empty → output = info_msg("(empty context)")
    class _EmptyEnv:
        _x = 1

    d = make_dispatcher({"env": _EmptyEnv()})
    frames = await d.dispatch("env")
    # lines is empty → "(empty context)"
    assert "(empty context)" in first_data(frames)
