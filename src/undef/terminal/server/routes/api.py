#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""HTTP API routes for the hosted server app."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse

from undef.terminal.server.models import model_dump
from undef.terminal.server.registry import SessionRegistry


def _registry(request: Request) -> SessionRegistry:
    return request.app.state.uterm_registry


def create_api_router() -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/health")
    async def health() -> dict[str, object]:
        return {"ok": True, "service": "undefterm-server"}

    @router.get("/sessions")
    async def list_sessions(request: Request) -> list[dict[str, Any]]:
        sessions = await _registry(request).list_sessions()
        return [model_dump(session) for session in sessions]

    @router.post("/sessions")
    async def create_session(request: Request, payload: Annotated[dict[str, Any], Body(...)]) -> dict[str, Any]:
        try:
            session = await _registry(request).create_session(payload)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return model_dump(session)

    @router.get("/sessions/{session_id}")
    async def get_session(request: Request, session_id: str) -> dict[str, Any]:
        try:
            session = await _registry(request).get_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}") from exc
        return model_dump(session)

    @router.patch("/sessions/{session_id}")
    async def patch_session(
        request: Request, session_id: str, payload: Annotated[dict[str, Any], Body(...)]
    ) -> dict[str, Any]:
        try:
            session = await _registry(request).update_session(session_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}") from exc
        return model_dump(session)

    @router.delete("/sessions/{session_id}")
    async def delete_session(request: Request, session_id: str) -> dict[str, bool]:
        try:
            await _registry(request).delete_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}") from exc
        return {"ok": True}

    @router.post("/sessions/{session_id}/connect")
    async def connect_session(request: Request, session_id: str) -> dict[str, Any]:
        try:
            session = await _registry(request).start_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}") from exc
        return model_dump(session)

    @router.post("/sessions/{session_id}/disconnect")
    async def disconnect_session(request: Request, session_id: str) -> dict[str, Any]:
        try:
            session = await _registry(request).stop_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}") from exc
        return model_dump(session)

    @router.post("/sessions/{session_id}/restart")
    async def restart_session(request: Request, session_id: str) -> dict[str, Any]:
        try:
            session = await _registry(request).restart_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}") from exc
        return model_dump(session)

    @router.post("/sessions/{session_id}/mode")
    async def set_mode(
        request: Request, session_id: str, payload: Annotated[dict[str, str], Body(...)]
    ) -> dict[str, Any]:
        mode = str(payload.get("input_mode", "")).strip()
        if mode not in {"open", "hijack"}:
            raise HTTPException(status_code=400, detail="input_mode must be 'open' or 'hijack'")
        try:
            session = await _registry(request).set_mode(session_id, mode)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}") from exc
        return model_dump(session)

    @router.post("/sessions/{session_id}/clear")
    async def clear_session(request: Request, session_id: str) -> dict[str, Any]:
        try:
            session = await _registry(request).clear_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}") from exc
        return model_dump(session)

    @router.post("/sessions/{session_id}/analyze")
    async def analyze_session(request: Request, session_id: str) -> dict[str, Any]:
        try:
            analysis = await _registry(request).analyze_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}") from exc
        return {"session_id": session_id, "analysis": analysis}

    @router.get("/sessions/{session_id}/snapshot")
    async def snapshot(request: Request, session_id: str) -> dict[str, Any] | None:
        return await _registry(request).last_snapshot(session_id)

    @router.get("/sessions/{session_id}/events")
    async def events(request: Request, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        return await _registry(request).events(session_id, limit=limit)

    @router.get("/sessions/{session_id}/recording")
    async def recording(request: Request, session_id: str) -> dict[str, Any]:
        try:
            return await _registry(request).recording_meta(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}") from exc

    @router.get("/sessions/{session_id}/recording/entries")
    async def recording_entries(
        request: Request,
        session_id: str,
        limit: int = 200,
        offset: int | None = None,
        event: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            return await _registry(request).recording_entries(session_id, limit=limit, offset=offset, event=event)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}") from exc

    @router.get("/sessions/{session_id}/recording/download")
    async def recording_download(request: Request, session_id: str) -> FileResponse:
        try:
            path = await _registry(request).recording_path(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}") from exc
        if path is None or not path.exists():
            raise HTTPException(status_code=404, detail="recording not available")
        return FileResponse(path, filename=path.name, media_type="application/json")

    return router
