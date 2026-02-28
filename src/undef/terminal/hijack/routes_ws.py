#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""WebSocket terminal routes for the hijack hub.

Registers:
- ``/ws/worker/{bot_id}/term``  — worker → hub (terminal output, snapshots)
- ``/ws/bot/{bot_id}/term``     — browser → hub (dashboard viewer + hijack control)
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

try:
    from fastapi import APIRouter, WebSocket, WebSocketDisconnect
except ImportError as _e:  # pragma: no cover
    raise ImportError("fastapi is required for hijack routes: pip install 'undef-terminal[websocket]'") from _e

import logging

from undef.terminal.hijack.models import BotTermState, extract_prompt_id

if TYPE_CHECKING:
    from undef.terminal.hijack.hub import TermHub

logger = logging.getLogger(__name__)


def register_ws_routes(hub: TermHub, router: APIRouter) -> None:
    """Attach WebSocket terminal routes to *router*."""

    @router.websocket("/ws/worker/{bot_id}/term")
    async def ws_worker_term(websocket: WebSocket, bot_id: str) -> None:
        await websocket.accept()
        async with hub._lock:
            st = hub._bots.setdefault(bot_id, BotTermState())
            st.worker_ws = websocket
        logger.info("term_worker_connected bot_id=%s", bot_id)
        await hub._request_snapshot(bot_id)

        try:
            while True:
                await hub._cleanup_expired_hijack(bot_id)
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except Exception:  # noqa: S112
                    continue
                mtype = msg.get("type")
                if mtype == "term":
                    data = msg.get("data", "")
                    if data:
                        await hub._broadcast(bot_id, {"type": "term", "data": data, "ts": msg.get("ts", time.time())})
                elif mtype == "snapshot":
                    snapshot: dict[str, Any] = {
                        "type": "snapshot",
                        "screen": msg.get("screen", ""),
                        "cursor": msg.get("cursor", {"x": 0, "y": 0}),
                        "cols": int(msg.get("cols", 80) or 80),
                        "rows": int(msg.get("rows", 25) or 25),
                        "screen_hash": msg.get("screen_hash", ""),
                        "cursor_at_end": bool(msg.get("cursor_at_end", True)),
                        "has_trailing_space": bool(msg.get("has_trailing_space", False)),
                        "prompt_detected": msg.get("prompt_detected"),
                        "ts": msg.get("ts", time.time()),
                    }
                    async with hub._lock:
                        st2 = hub._bots.get(bot_id)
                        if st2 is not None:
                            st2.last_snapshot = snapshot
                    await hub._broadcast(bot_id, snapshot)
                    await hub._append_event(
                        bot_id,
                        "snapshot",
                        {"prompt_id": extract_prompt_id(snapshot), "screen_hash": snapshot.get("screen_hash")},
                    )
                elif mtype == "analysis":
                    await hub._broadcast(
                        bot_id,
                        {
                            "type": "analysis",
                            "formatted": msg.get("formatted", ""),
                            "raw": msg.get("raw"),
                            "ts": msg.get("ts", time.time()),
                        },
                    )
                elif mtype == "status":
                    await hub._broadcast(bot_id, msg)
                    await hub._append_event(bot_id, "worker_status", {"status": msg})
        except WebSocketDisconnect:
            pass
        except Exception as exc:  # pragma: no cover
            logger.warning("term_worker_ws_error bot_id=%s error=%s", bot_id, exc)
        finally:
            async with hub._lock:
                st3 = hub._bots.get(bot_id)
                if st3 is not None and st3.worker_ws is websocket:
                    st3.worker_ws = None
            logger.info("term_worker_disconnected bot_id=%s", bot_id)

    @router.websocket("/ws/bot/{bot_id}/term")
    async def ws_browser_term(websocket: WebSocket, bot_id: str) -> None:
        await websocket.accept()
        st = await hub._get(bot_id)
        async with hub._lock:
            st2 = hub._bots.setdefault(bot_id, BotTermState())
            st2.browsers.add(websocket)

        await websocket.send_text(
            json.dumps(
                {
                    "type": "hello",
                    "bot_id": bot_id,
                    "can_hijack": True,
                    "hijacked": hub._is_hijacked(st),
                    "hijacked_by_me": hub._is_dashboard_hijack_active(st) and st.hijack_owner is websocket,
                },
                ensure_ascii=True,
            )
        )
        await websocket.send_text(json.dumps(await hub._hijack_state_msg_for(bot_id, websocket), ensure_ascii=True))

        if st.last_snapshot is not None:
            await websocket.send_text(json.dumps(st.last_snapshot, ensure_ascii=True))
        else:
            await hub._request_snapshot(bot_id)

        try:
            while True:
                await hub._cleanup_expired_hijack(bot_id)
                raw = await websocket.receive_text()
                try:
                    msg_b: dict[str, Any] = json.loads(raw)
                except Exception:  # noqa: S112
                    continue
                mtype = msg_b.get("type")

                if mtype == "snapshot_req":
                    if await hub._is_owner(bot_id, websocket):
                        await hub._touch_hijack_owner(bot_id)
                    await hub._request_snapshot(bot_id)

                elif mtype == "analyze_req":
                    if await hub._is_owner(bot_id, websocket):
                        await hub._touch_hijack_owner(bot_id)
                    await hub._request_analysis(bot_id)

                elif mtype == "heartbeat":
                    if await hub._is_owner(bot_id, websocket):
                        lease_expires_at = await hub._touch_hijack_owner(bot_id)
                        await websocket.send_text(
                            json.dumps(
                                {"type": "heartbeat_ack", "lease_expires_at": lease_expires_at, "ts": time.time()},
                                ensure_ascii=True,
                            )
                        )
                        await hub._broadcast_hijack_state(bot_id)

                elif mtype == "hijack_request":
                    st_now = await hub._get(bot_id)
                    if st_now.hijack_owner is None and not hub._is_rest_session_active(st_now):
                        await hub._set_hijack_owner(bot_id, websocket)
                        ok = await hub._send_worker(
                            bot_id,
                            {
                                "type": "control",
                                "action": "pause",
                                "owner": "dashboard",
                                "lease_s": 0,
                                "ts": time.time(),
                            },
                        )
                        if not ok:
                            await hub._set_hijack_owner(bot_id, None)
                            hub._notify_hijack_changed(bot_id, enabled=False, owner=None)
                            await websocket.send_text(
                                json.dumps(
                                    {"type": "error", "message": "No worker connected for this bot."}, ensure_ascii=True
                                )
                            )
                            await hub._broadcast_hijack_state(bot_id)
                            continue
                        await hub._broadcast_hijack_state(bot_id)
                        hub._notify_hijack_changed(bot_id, enabled=True, owner="dashboard")
                        await hub._append_event(bot_id, "hijack_acquired", {"owner": "dashboard_ws"})
                    else:
                        await websocket.send_text(
                            json.dumps(
                                {"type": "error", "message": "Already hijacked by another client."}, ensure_ascii=True
                            )
                        )
                        await websocket.send_text(
                            json.dumps(await hub._hijack_state_msg_for(bot_id, websocket), ensure_ascii=True)
                        )

                elif mtype == "hijack_step":
                    if await hub._is_owner(bot_id, websocket):
                        await hub._touch_hijack_owner(bot_id)
                        ok = await hub._send_worker(
                            bot_id,
                            {
                                "type": "control",
                                "action": "step",
                                "owner": "dashboard",
                                "lease_s": 0,
                                "ts": time.time(),
                            },
                        )
                        if not ok:
                            await websocket.send_text(
                                json.dumps(
                                    {"type": "error", "message": "No worker connected for this bot."}, ensure_ascii=True
                                )
                            )
                        else:
                            await hub._append_event(bot_id, "hijack_step", {"owner": "dashboard_ws"})

                elif mtype == "hijack_release":
                    if await hub._is_owner(bot_id, websocket):
                        await hub._set_hijack_owner(bot_id, None)
                        await hub._send_worker(
                            bot_id,
                            {
                                "type": "control",
                                "action": "resume",
                                "owner": "dashboard",
                                "lease_s": 0,
                                "ts": time.time(),
                            },
                        )
                        await hub._broadcast_hijack_state(bot_id)
                        st_after = await hub._get(bot_id)
                        if not hub._is_rest_session_active(st_after):
                            hub._notify_hijack_changed(bot_id, enabled=False, owner=None)
                        await hub._append_event(bot_id, "hijack_released", {"owner": "dashboard_ws"})

                elif mtype == "input":
                    if await hub._is_owner(bot_id, websocket):
                        await hub._touch_hijack_owner(bot_id)
                        data = msg_b.get("data", "")
                        if data:
                            ok = await hub._send_worker(bot_id, {"type": "input", "data": data, "ts": time.time()})
                            if not ok:
                                await websocket.send_text(
                                    json.dumps(
                                        {"type": "error", "message": "Worker connection lost."}, ensure_ascii=True
                                    )
                                )
                            else:
                                await hub._append_event(
                                    bot_id, "hijack_send", {"owner": "dashboard_ws", "keys": data[:120]}
                                )

        except WebSocketDisconnect:
            pass
        except Exception as exc:  # pragma: no cover
            logger.warning("term_browser_ws_error bot_id=%s error=%s", bot_id, exc)
        finally:
            was_owner = await hub._is_owner(bot_id, websocket)
            async with hub._lock:
                st3 = hub._bots.get(bot_id)
                if st3 is not None:
                    st3.browsers.discard(websocket)
                    if was_owner and st3.hijack_owner is websocket:
                        st3.hijack_owner = None
            if was_owner:
                await hub._send_worker(
                    bot_id,
                    {"type": "control", "action": "resume", "owner": "dashboard", "lease_s": 0, "ts": time.time()},
                )
                await hub._broadcast_hijack_state(bot_id)
                st_after2 = await hub._get(bot_id)
                if not hub._is_rest_session_active(st_after2):
                    hub._notify_hijack_changed(bot_id, enabled=False, owner=None)
                await hub._append_event(bot_id, "hijack_released", {"owner": "dashboard_ws_disconnect"})
