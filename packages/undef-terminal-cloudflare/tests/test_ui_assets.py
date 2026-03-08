#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Unit tests for ui/assets.py — serve_asset()."""

from __future__ import annotations

import importlib.resources
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_file(name: str, content: str) -> SimpleNamespace:
    """Traversable-like file object that always reports is_file=True."""
    return SimpleNamespace(
        is_file=lambda: True,
        name=name,
        read_text=lambda encoding="utf-8": content,
    )


def _not_found_file() -> SimpleNamespace:
    """Traversable-like object that reports is_file=False."""
    return SimpleNamespace(is_file=lambda: False, name="")


def _patch_files_local(file_obj):
    """Patch importlib.resources.files so files(...) / 'static' / rel → file_obj."""
    local_root = MagicMock()
    local_root.__truediv__.return_value = file_obj  # local_root / rel

    pkg = MagicMock()
    pkg.__truediv__.return_value = local_root  # pkg / "static"

    return patch.object(importlib.resources, "files", return_value=pkg)


def _patch_files_fallthrough(file_obj):
    """First call (local pkg) raises ModuleNotFoundError; second returns file_obj."""
    call_count = [0]

    def _side_effect(pkg_name: str):
        call_count[0] += 1
        if call_count[0] == 1:
            raise ModuleNotFoundError("no local static")
        # Second call: undef.terminal frontend
        frontend_dir = MagicMock()
        frontend_dir.__truediv__.return_value = file_obj  # frontend_dir / rel
        root = MagicMock()
        root.__truediv__.return_value = frontend_dir  # root / "frontend"
        return root

    return patch.object(importlib.resources, "files", side_effect=_side_effect)


# ---------------------------------------------------------------------------
# Path traversal protection
# ---------------------------------------------------------------------------


def test_path_traversal_single_dotdot_blocked() -> None:
    from undef_terminal_cloudflare.ui.assets import serve_asset

    resp = serve_asset("../../etc/passwd")
    assert resp.status == 403


def test_path_traversal_nested_blocked() -> None:
    from undef_terminal_cloudflare.ui.assets import serve_asset

    resp = serve_asset("a/../../../secret")
    assert resp.status == 403


# ---------------------------------------------------------------------------
# Local static file served
# ---------------------------------------------------------------------------


def test_serve_js_file_local() -> None:
    from undef_terminal_cloudflare.ui.assets import serve_asset

    with _patch_files_local(_mock_file("app.js", "console.log('hi');")):
        resp = serve_asset("app.js")

    assert resp.status == 200
    assert "javascript" in resp.headers["content-type"]
    assert "console.log" in resp.body


def test_serve_css_file_local() -> None:
    from undef_terminal_cloudflare.ui.assets import serve_asset

    with _patch_files_local(_mock_file("style.css", "body { color: red; }")):
        resp = serve_asset("style.css")

    assert resp.status == 200
    assert "css" in resp.headers["content-type"]


def test_serve_html_file_local() -> None:
    from undef_terminal_cloudflare.ui.assets import serve_asset

    with _patch_files_local(_mock_file("index.html", "<html/>")):
        resp = serve_asset("index.html")

    assert resp.status == 200
    assert "html" in resp.headers["content-type"]


def test_serve_unknown_mime_type() -> None:
    from undef_terminal_cloudflare.ui.assets import serve_asset

    with _patch_files_local(_mock_file("data.bin", "raw bytes")):
        resp = serve_asset("data.bin")

    assert resp.status == 200
    assert resp.headers["content-type"] == "application/octet-stream"


# ---------------------------------------------------------------------------
# Fallback: local static missing → undef.terminal frontend
# ---------------------------------------------------------------------------


def test_falls_through_to_frontend_package() -> None:
    from undef_terminal_cloudflare.ui.assets import serve_asset

    with _patch_files_fallthrough(_mock_file("hijack.js", "// hijack")):
        resp = serve_asset("hijack.js")

    assert resp.status == 200
    assert "javascript" in resp.headers["content-type"]
    assert "hijack" in resp.body


def test_frontend_file_not_found_returns_404() -> None:
    from undef_terminal_cloudflare.ui.assets import serve_asset

    with _patch_files_fallthrough(_not_found_file()):
        resp = serve_asset("nonexistent.js")

    assert resp.status == 404
    assert "not found" in resp.body


def test_frontend_module_not_found_returns_404() -> None:
    from undef_terminal_cloudflare.ui.assets import serve_asset

    call_count = [0]

    def _always_raise(pkg_name: str):
        call_count[0] += 1
        raise ModuleNotFoundError(f"no package ({call_count[0]})")

    with patch.object(importlib.resources, "files", side_effect=_always_raise):
        resp = serve_asset("missing.js")

    assert resp.status == 404
    assert "unavailable" in resp.body
