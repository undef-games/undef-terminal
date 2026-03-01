#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""REST hijack routes for the hijack hub.

Registers:
- ``POST /bot/{id}/hijack/acquire``
- ``POST /bot/{id}/hijack/{hid}/heartbeat``
- ``GET  /bot/{id}/hijack/{hid}/snapshot``
- ``GET  /bot/{id}/hijack/{hid}/events``
- ``POST /bot/{id}/hijack/{hid}/send``
- ``POST /bot/{id}/hijack/{hid}/step``
- ``POST /bot/{id}/hijack/{hid}/release``
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Any

try:
    from fastapi import APIRouter, Body, Path, Query
    from fastapi.responses import JSONResponse
except ImportError as _e:  # pragma: no cover
    raise ImportError("fastapi is required for hijack routes: pip install 'undef-terminal[websocket]'") from _e

import logging

from undef.terminal.hijack.models import (
    HijackAcquireRequest,
    HijackHeartbeatRequest,
    HijackSendRequest,
    extract_prompt_id,
)

if TYPE_CHECKING:
    from undef.terminal.hijack.hub import TermHub

logger = logging.getLogger(__name__)


def register_rest_routes(hub: TermHub, router: APIRouter) -> None:
    """Attach REST hijack routes to *router*."""

    @router.post("/bot/{bot_id}/hijack/acquire")
    async def hijack_acquire(
        bot_id: str = Path(pattern=r"^[\w\-]+$"),
        request: HijackAcquireRequest | None = None,
    ) -> Any:
        if request is None:
            request = HijackAcquireRequest()
        await hub._cleanup_expired_hijack(bot_id)

        # Quick worker check before acquiring the lock (avoids waiting on I/O).
        st_pre = await hub._get(bot_id)
        if st_pre.worker_ws is None:
            return JSONResponse({"error": "No worker connected for this bot."}, status_code=409)

        lease_s = hub._clamp_lease(request.lease_s)
        hijack_id = str(uuid.uuid4())
        now = time.time()
        ok = await hub._send_worker(
            bot_id,
            {
                "type": "control",
                "action": "pause",
                "owner": request.owner,
                "lease_s": lease_s,
                "hijack_id": hijack_id,
                "ts": now,
            },
        )
        if not ok:
            return JSONResponse({"error": "No worker connected for this bot."}, status_code=409)

        # Atomically check for concurrent hijackers and write the session.
        acquired, err = await hub._try_acquire_rest_hijack(
            bot_id,
            owner=request.owner,
            lease_s=lease_s,
            hijack_id=hijack_id,
            now=now,
        )
        if not acquired:
            # Another request raced in and acquired the hijack; send resume to undo our pause.
            # Include hijack_id so the worker can correlate it with our pause message.
            await hub._send_worker(
                bot_id,
                {
                    "type": "control",
                    "action": "resume",
                    "owner": request.owner,
                    "lease_s": 0,
                    "hijack_id": hijack_id,
                    "ts": now,
                },
            )
            return JSONResponse({"error": "Bot is already hijacked."}, status_code=409)
        hub._notify_hijack_changed(bot_id, enabled=True, owner=request.owner)
        await hub._append_event(
            bot_id, "hijack_acquired", {"hijack_id": hijack_id, "owner": request.owner, "lease_s": lease_s}
        )
        await hub._broadcast_hijack_state(bot_id)
        return {
            "ok": True,
            "bot_id": bot_id,
            "hijack_id": hijack_id,
            "lease_expires_at": now + lease_s,
            "owner": request.owner,
        }

    @router.post("/bot/{bot_id}/hijack/{hijack_id}/heartbeat")
    async def hijack_heartbeat(
        bot_id: str = Path(pattern=r"^[\w\-]+$"),
        hijack_id: str = Path(),
        request: HijackHeartbeatRequest | None = None,
    ) -> Any:
        if request is None:
            request = HijackHeartbeatRequest()
        hs = await hub._get_rest_session(bot_id, hijack_id)
        if hs is None:
            return JSONResponse({"error": "Invalid or expired hijack session."}, status_code=404)
        lease_s = hub._clamp_lease(request.lease_s)
        now = time.time()
        async with hub._lock:
            st = hub._bots.get(bot_id)
            if st is None or st.hijack_session is None or st.hijack_session.hijack_id != hijack_id:  # pragma: no cover
                return JSONResponse({"error": "Invalid or expired hijack session."}, status_code=404)
            st.hijack_session.last_heartbeat = now
            st.hijack_session.lease_expires_at = now + lease_s
        await hub._append_event(bot_id, "hijack_heartbeat", {"hijack_id": hijack_id, "lease_s": lease_s})
        await hub._broadcast_hijack_state(bot_id)
        return {"ok": True, "hijack_id": hijack_id, "lease_expires_at": now + lease_s}

    @router.get("/bot/{bot_id}/hijack/{hijack_id}/snapshot")
    async def hijack_snapshot(
        bot_id: str = Path(pattern=r"^[\w\-]+$"),
        hijack_id: str = Path(),
        wait_ms: int = Query(default=1500, ge=0, le=10000),
    ) -> Any:
        hs = await hub._get_rest_session(bot_id, hijack_id)
        if hs is None:
            return JSONResponse({"error": "Invalid or expired hijack session."}, status_code=404)
        snapshot = await hub._wait_for_snapshot(bot_id, timeout_ms=wait_ms)
        return {
            "ok": True,
            "bot_id": bot_id,
            "hijack_id": hijack_id,
            "snapshot": snapshot,
            "prompt_id": extract_prompt_id(snapshot),
            "lease_expires_at": hs.lease_expires_at,
        }

    @router.get("/bot/{bot_id}/hijack/{hijack_id}/events")
    async def hijack_events(
        bot_id: str = Path(pattern=r"^[\w\-]+$"),
        hijack_id: str = Path(),
        after_seq: int = Query(default=0, ge=0),
        limit: int = Query(default=200, ge=1, le=2000),
    ) -> Any:
        hs = await hub._get_rest_session(bot_id, hijack_id)
        if hs is None:
            return JSONResponse({"error": "Invalid or expired hijack session."}, status_code=404)
        async with hub._lock:
            st = hub._bots.get(bot_id)
            if st is None:  # pragma: no cover
                rows: list[dict[str, Any]] = []
                latest_seq = 0
            else:
                rows = [evt for evt in list(st.events) if int(evt.get("seq", 0)) > after_seq][:limit]
                latest_seq = st.event_seq
        return {
            "ok": True,
            "bot_id": bot_id,
            "hijack_id": hijack_id,
            "after_seq": after_seq,
            "latest_seq": latest_seq,
            "events": rows,
            "lease_expires_at": hs.lease_expires_at,
        }

    @router.post("/bot/{bot_id}/hijack/{hijack_id}/send")
    async def hijack_send(
        bot_id: str = Path(pattern=r"^[\w\-]+$"),
        hijack_id: str = Path(),
        request: HijackSendRequest = Body(...),  # noqa: B008
    ) -> Any:
        hs = await hub._get_rest_session(bot_id, hijack_id)
        if hs is None:
            return JSONResponse({"error": "Invalid or expired hijack session."}, status_code=404)
        if not request.keys:
            return JSONResponse({"error": "keys must not be empty."}, status_code=400)
        matched, snapshot, reason = await hub._wait_for_guard(
            bot_id,
            expect_prompt_id=request.expect_prompt_id,
            expect_regex=request.expect_regex,
            timeout_ms=request.timeout_ms,
            poll_interval_ms=request.poll_interval_ms,
        )
        if not matched:
            return JSONResponse(
                {"error": reason or "prompt_guard_not_satisfied", "current_prompt_id": extract_prompt_id(snapshot)},
                status_code=409,
            )
        ok = await hub._send_worker(bot_id, {"type": "input", "data": request.keys, "ts": time.time()})
        if not ok:
            return JSONResponse({"error": "No worker connected for this bot."}, status_code=409)
        await hub._append_event(
            bot_id,
            "hijack_send",
            {
                "hijack_id": hijack_id,
                "keys": request.keys[:120],
                "expect_prompt_id": request.expect_prompt_id,
                "expect_regex": request.expect_regex,
            },
        )
        return {
            "ok": True,
            "bot_id": bot_id,
            "hijack_id": hijack_id,
            "sent": request.keys,
            "matched_prompt_id": extract_prompt_id(snapshot),
            "lease_expires_at": hs.lease_expires_at,
        }

    @router.post("/bot/{bot_id}/hijack/{hijack_id}/step")
    async def hijack_step(bot_id: str = Path(pattern=r"^[\w\-]+$"), hijack_id: str = Path()) -> Any:
        hs = await hub._get_rest_session(bot_id, hijack_id)
        if hs is None:
            return JSONResponse({"error": "Invalid or expired hijack session."}, status_code=404)
        ok = await hub._send_worker(
            bot_id, {"type": "control", "action": "step", "owner": hs.owner, "lease_s": 0, "ts": time.time()}
        )
        if not ok:
            return JSONResponse({"error": "No worker connected for this bot."}, status_code=409)
        await hub._append_event(bot_id, "hijack_step", {"hijack_id": hijack_id})
        return {"ok": True, "bot_id": bot_id, "hijack_id": hijack_id, "lease_expires_at": hs.lease_expires_at}

    @router.post("/bot/{bot_id}/hijack/{hijack_id}/release")
    async def hijack_release(bot_id: str = Path(pattern=r"^[\w\-]+$"), hijack_id: str = Path()) -> Any:
        hs = await hub._get_rest_session(bot_id, hijack_id)
        if hs is None:
            return JSONResponse({"error": "Invalid or expired hijack session."}, status_code=404)
        should_resume = False
        async with hub._lock:
            st = hub._bots.get(bot_id)
            if st is None or st.hijack_session is None or st.hijack_session.hijack_id != hijack_id:  # pragma: no cover
                return JSONResponse({"error": "Invalid or expired hijack session."}, status_code=404)
            st.hijack_session = None
            should_resume = st.hijack_owner is None
        if should_resume:
            await hub._send_worker(
                bot_id, {"type": "control", "action": "resume", "owner": hs.owner, "lease_s": 0, "ts": time.time()}
            )
            hub._notify_hijack_changed(bot_id, enabled=False, owner=None)
        await hub._append_event(bot_id, "hijack_released", {"hijack_id": hijack_id, "owner": hs.owner})
        await hub._broadcast_hijack_state(bot_id)
        return {"ok": True, "bot_id": bot_id, "hijack_id": hijack_id}
