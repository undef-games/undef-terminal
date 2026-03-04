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

from fastapi import FastAPI, WebSocket
from starlette.staticfiles import StaticFiles

from undef.terminal.hijack.hub import TermHub
from undef.terminal.server.auth import resolve_ws_principal
from undef.terminal.server.policy import SessionPolicyResolver
from undef.terminal.server.registry import SessionRegistry
from undef.terminal.server.routes.api import create_api_router
from undef.terminal.server.routes.pages import create_page_router

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from undef.terminal.server.models import ServerConfig


def create_server_app(config: ServerConfig) -> FastAPI:
    """Create the standalone reference server application."""
    policy = SessionPolicyResolver(config.auth)
    registry: SessionRegistry | None = None

    async def _resolve_browser_role(ws: WebSocket, worker_id: str) -> str:
        principal = resolve_ws_principal(ws, config.auth)
        session = await registry.get_definition(worker_id) if registry is not None else None
        if session is None:
            return "admin" if config.auth.mode in {"none", "dev"} else "viewer"
        return policy.role_for(principal, session)

    hub = TermHub(resolve_browser_role=_resolve_browser_role)
    registry = SessionRegistry(
        config.sessions,
        hub=hub,
        public_base_url=config.server.public_base_url,
        recording=config.recording,
    )

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
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
    app.state.uterm_hub = hub
    app.state.uterm_registry = registry

    app.include_router(hub.create_router())
    app.include_router(create_api_router())
    app.include_router(create_page_router(), prefix=config.ui.app_path)

    frontend_path = importlib.resources.files("undef.terminal") / "frontend"
    app.mount(config.ui.assets_path, StaticFiles(directory=str(frontend_path), html=False), name="uterm-assets")
    return app
