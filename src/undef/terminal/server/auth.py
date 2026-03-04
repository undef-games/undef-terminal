#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""Principal resolution for the standalone terminal server."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from undef.terminal.server.models import AuthConfig


@dataclass(slots=True)
class Principal:
    """Resolved browser or API principal."""

    name: str
    requested_role: str | None = None
    surface: str | None = None


def _cookie_value(cookies: dict[str, str], key: str) -> str | None:
    value = cookies.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def resolve_http_principal(request: object, auth: AuthConfig) -> Principal:
    """Resolve a principal from a FastAPI/Starlette Request-like object."""
    headers = getattr(request, "headers", {})
    cookies = getattr(request, "cookies", {})
    principal = headers.get(auth.principal_header) or _cookie_value(cookies, auth.principal_cookie) or "anonymous"
    role = headers.get(auth.role_header)
    surface = _cookie_value(cookies, auth.surface_cookie)
    return Principal(name=str(principal), requested_role=(str(role) if role else None), surface=surface)


def resolve_ws_principal(websocket: object, auth: AuthConfig) -> Principal:
    """Resolve a principal from a FastAPI/Starlette WebSocket-like object."""
    headers = getattr(websocket, "headers", {})
    cookies = getattr(websocket, "cookies", {})
    principal = headers.get(auth.principal_header) or _cookie_value(cookies, auth.principal_cookie) or "anonymous"
    role = headers.get(auth.role_header)
    surface = _cookie_value(cookies, auth.surface_cookie)
    return Principal(name=str(principal), requested_role=(str(role) if role else None), surface=surface)
