#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""FastAPI application factory for the hosted terminal server."""

from __future__ import annotations

import asyncio
import contextlib
import importlib.resources
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketException, status
from starlette.requests import HTTPConnection  # noqa: TC002
from starlette.staticfiles import StaticFiles

from undef.terminal.hijack.hub import TermHub
from undef.terminal.server.auth import resolve_http_principal, resolve_ws_principal
from undef.terminal.server.authorization import AuthorizationService
from undef.terminal.server.policy import SessionPolicyResolver
from undef.terminal.server.registry import SessionRegistry
from undef.terminal.server.routes.api import create_api_router
from undef.terminal.server.routes.pages import create_page_router

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from undef.terminal.server.models import ServerConfig


def create_server_app(config: ServerConfig) -> FastAPI:
    """Create the standalone reference server application."""
    authz = AuthorizationService()
    policy = SessionPolicyResolver(config.auth, authz=authz)
    registry: SessionRegistry | None = None

    async def _require_authenticated(connection: HTTPConnection) -> None:
        if connection.scope.get("type") == "websocket":
            principal = resolve_ws_principal(connection, config.auth)
            connection.state.uterm_principal = principal
            if config.auth.mode not in {"none", "dev"} and principal.subject_id == "anonymous":
                raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="authentication required")
            return
        principal = resolve_http_principal(connection, config.auth)
        connection.state.uterm_principal = principal
        if config.auth.mode not in {"none", "dev"} and principal.subject_id == "anonymous":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")

    async def _resolve_browser_role(ws: WebSocket, worker_id: str) -> str:
        principal = getattr(ws.state, "uterm_principal", None)
        if principal is None:
            principal = resolve_ws_principal(ws, config.auth)
        session = await registry.get_definition(worker_id) if registry is not None else None
        if session is None:
            return "admin" if config.auth.mode in {"none", "dev"} else "viewer"
        if not authz.can_read_session(principal, session):
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="insufficient privileges")
        return policy.role_for(principal, session)

    hub = TermHub(resolve_browser_role=_resolve_browser_role)
    registry = SessionRegistry(
        config.sessions,
        hub=hub,
        public_base_url=config.server.public_base_url,
        recording=config.recording,
        worker_bearer_token=config.auth.worker_bearer_token,
    )

    @asynccontextmanager
    async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
        async def _delayed_boot() -> None:
            await asyncio.sleep(0.15)
            await registry.start_auto_start_sessions()

        boot_task = asyncio.create_task(_delayed_boot())
        try:
            yield
        finally:
            boot_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await boot_task
            await registry.shutdown()

    app = FastAPI(title=config.server.title, lifespan=_lifespan)
    app.state.uterm_config = config
    app.state.uterm_policy = policy
    app.state.uterm_authz = authz
    app.state.uterm_hub = hub
    app.state.uterm_registry = registry

    app.include_router(hub.create_router(), dependencies=[Depends(_require_authenticated)])
    app.include_router(create_api_router(), dependencies=[Depends(_require_authenticated)])
    app.include_router(create_page_router(), prefix=config.ui.app_path)

    frontend_path = importlib.resources.files("undef.terminal") / "frontend"
    app.mount(config.ui.assets_path, StaticFiles(directory=str(frontend_path), html=False), name="uterm-assets")
    return app
