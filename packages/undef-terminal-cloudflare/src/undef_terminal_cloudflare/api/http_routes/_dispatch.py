#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlparse

from undef_terminal_cloudflare.api.http_routes._hijack import route_hijack
from undef_terminal_cloudflare.api.http_routes._session import route_session
from undef_terminal_cloudflare.api.http_routes._shared import (
    _SESSION_ROUTE_RE,
    _session_status_item,
)
from undef_terminal_cloudflare.cf_types import json_response

if TYPE_CHECKING:
    from undef_terminal_cloudflare.contracts import RuntimeProtocol


async def route_http(runtime: RuntimeProtocol, request: object) -> object:
    url = str(getattr(request, "url", ""))
    path = urlparse(url).path
    method = str(getattr(request, "method", "GET")).upper()

    if path == "/api/health":
        return json_response({"ok": True, "service": "undef-terminal-cloudflare"})

    if path == "/api/sessions":
        return json_response([_session_status_item(runtime)], headers={"X-Sessions-Scope": "local"})

    hijack_result = await route_hijack(runtime, request, path, url, method)
    if hijack_result is not None:
        return hijack_result

    session_match = _SESSION_ROUTE_RE.match(path)
    if session_match:
        return await route_session(runtime, request, path, url, method, session_match)

    return json_response({"error": "not_found", "path": path}, status=404)
