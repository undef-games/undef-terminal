#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#

"""TermHub: in-memory registry for terminal WebSocket connections.

Requires the ``websocket`` extra::

    pip install 'undef-terminal[websocket]'
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

try:
    from fastapi import WebSocket
except ImportError as _e:
    raise ImportError("fastapi is required for TermHub: pip install 'undef-terminal[websocket]'") from _e

import logging

from undef.terminal.hijack.models import BotTermState, HijackSession, extract_prompt_id

logger = logging.getLogger(__name__)

# Callback: (bot_id, is_hijacked, owner_or_None)
HijackStateCallback = Callable[[str, bool, str | None], Awaitable[None] | None]


class TermHub:
    """In-memory registry for terminal WebSocket connections.

    Manages the lifecycle of worker ↔ browser terminal streams and hijack leases.

    Args:
        on_hijack_changed: Optional async or sync callback invoked whenever hijack
            state changes for any bot. Signature: ``(bot_id, hijacked, owner) -> None``.
        dashboard_hijack_lease_s: Default dashboard WS hijack lease duration in seconds.
    """

    def __init__(
        self,
        on_hijack_changed: HijackStateCallback | None = None,
        dashboard_hijack_lease_s: int = 45,
    ) -> None:
        self._lock = asyncio.Lock()
        self._bots: dict[str, BotTermState] = {}
        self._on_hijack_changed = on_hijack_changed
        self._dashboard_hijack_lease_s = max(1, min(int(dashboard_hijack_lease_s), 600))

    @staticmethod
    def _clamp_lease(lease_s: int) -> int:
        return max(1, min(int(lease_s), 3600))

    @staticmethod
    def _is_rest_session_active(st: BotTermState) -> bool:
        hs = st.hijack_session
        return hs is not None and hs.lease_expires_at > time.time()

    @staticmethod
    def _is_dashboard_hijack_active(st: BotTermState) -> bool:
        if st.hijack_owner is None:
            return False
        if st.hijack_owner_expires_at is None:
            return True
        return st.hijack_owner_expires_at > time.time()

    def _is_hijacked(self, st: BotTermState) -> bool:
        return self._is_dashboard_hijack_active(st) or self._is_rest_session_active(st)

    async def _get(self, bot_id: str) -> BotTermState:
        async with self._lock:
            st = self._bots.get(bot_id)
            if st is None:
                st = BotTermState()
                self._bots[bot_id] = st
            return st

    def _notify_hijack_changed(self, bot_id: str, *, enabled: bool, owner: str | None = None) -> None:
        cb = self._on_hijack_changed
        if cb is None:
            return
        import inspect

        result = cb(bot_id, enabled, owner)
        if inspect.isawaitable(result):
            asyncio.create_task(result)  # type: ignore[arg-type]

    async def _append_event(self, bot_id: str, event_type: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = data or {}
        async with self._lock:
            st = self._bots.setdefault(bot_id, BotTermState())
            st.event_seq += 1
            evt: dict[str, Any] = {"seq": st.event_seq, "ts": time.time(), "type": event_type, "data": payload}
            st.events.append(evt)
            return evt

    async def _cleanup_expired_hijack(self, bot_id: str) -> bool:
        now = time.time()
        rest_expired = False
        dashboard_expired = False
        should_resume = False

        async with self._lock:
            st = self._bots.get(bot_id)
            if st is None:
                return False

            if st.hijack_session is not None and st.hijack_session.lease_expires_at <= now:
                st.hijack_session = None
                rest_expired = True

            if (
                st.hijack_owner is not None
                and st.hijack_owner_expires_at is not None
                and st.hijack_owner_expires_at <= now
            ):
                st.hijack_owner = None
                st.hijack_owner_expires_at = None
                dashboard_expired = True

            should_resume = (
                (rest_expired or dashboard_expired) and st.hijack_owner is None and st.hijack_session is None
            )

        if not rest_expired and not dashboard_expired:
            return False

        if should_resume:
            await self._send_worker(
                bot_id,
                {"type": "control", "action": "resume", "owner": "lease-expired", "lease_s": 0, "ts": now},
            )
            self._notify_hijack_changed(bot_id, enabled=False, owner=None)

        if rest_expired:
            await self._append_event(bot_id, "hijack_lease_expired")
        if dashboard_expired:
            await self._append_event(bot_id, "hijack_owner_expired")
        await self._broadcast_hijack_state(bot_id)
        return True

    async def _get_rest_session(self, bot_id: str, hijack_id: str) -> HijackSession | None:
        await self._cleanup_expired_hijack(bot_id)
        st = await self._get(bot_id)
        hs = st.hijack_session
        if hs is None or hs.lease_expires_at <= time.time() or hs.hijack_id != hijack_id:
            return None
        return hs

    @staticmethod
    def _snapshot_matches(
        snapshot: dict[str, Any] | None,
        *,
        expect_prompt_id: str | None,
        expect_regex: re.Pattern[str] | None,
    ) -> bool:
        if snapshot is None:
            return False
        if expect_prompt_id and extract_prompt_id(snapshot) != expect_prompt_id:
            return False
        return not (expect_regex is not None and not expect_regex.search(str(snapshot.get("screen", ""))))

    async def _wait_for_snapshot(self, bot_id: str, timeout_ms: int = 1500) -> dict[str, Any] | None:
        end = time.time() + max(50, timeout_ms) / 1000.0
        while time.time() < end:
            st = await self._get(bot_id)
            if st.last_snapshot is not None:
                return st.last_snapshot
            await self._request_snapshot(bot_id)
            await asyncio.sleep(0.08)
        return (await self._get(bot_id)).last_snapshot

    async def _wait_for_guard(
        self,
        bot_id: str,
        *,
        expect_prompt_id: str | None,
        expect_regex: str | None,
        timeout_ms: int,
        poll_interval_ms: int,
    ) -> tuple[bool, dict[str, Any] | None, str | None]:
        regex_obj: re.Pattern[str] | None = None
        if expect_regex:
            try:
                regex_obj = re.compile(expect_regex, re.IGNORECASE | re.MULTILINE)
            except re.error as exc:
                return False, None, f"invalid expect_regex: {exc}"

        if not expect_prompt_id and regex_obj is None:
            return True, (await self._get(bot_id)).last_snapshot, None

        end = time.time() + max(50, timeout_ms) / 1000.0
        interval = max(20, poll_interval_ms) / 1000.0
        last_snapshot: dict[str, Any] | None = None
        while time.time() < end:
            st = await self._get(bot_id)
            last_snapshot = st.last_snapshot
            if self._snapshot_matches(last_snapshot, expect_prompt_id=expect_prompt_id, expect_regex=regex_obj):
                return True, last_snapshot, None
            await self._request_snapshot(bot_id)
            await asyncio.sleep(interval)

        return False, last_snapshot, "prompt_guard_not_satisfied"

    async def _broadcast(self, bot_id: str, msg: dict[str, Any]) -> None:
        st = await self._get(bot_id)
        dead: set[WebSocket] = set()
        payload = json.dumps(msg, ensure_ascii=True)
        for ws in list(st.browsers):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        if dead:
            async with self._lock:
                st2 = self._bots.get(bot_id)
                if st2 is not None:
                    for ws in dead:
                        st2.browsers.discard(ws)

    async def _broadcast_hijack_state(self, bot_id: str) -> None:
        st = await self._get(bot_id)
        dead: set[WebSocket] = set()
        lease_expires_at = (
            st.hijack_session.lease_expires_at
            if self._is_rest_session_active(st) and st.hijack_session is not None
            else st.hijack_owner_expires_at
        )
        for ws in list(st.browsers):
            try:
                if self._is_dashboard_hijack_active(st) and st.hijack_owner is ws:
                    owner = "me"
                elif self._is_dashboard_hijack_active(st) or self._is_rest_session_active(st):
                    owner = "other"
                else:
                    owner = None
                await ws.send_text(
                    json.dumps(
                        {
                            "type": "hijack_state",
                            "hijacked": self._is_hijacked(st),
                            "owner": owner,
                            "lease_expires_at": lease_expires_at,
                        },
                        ensure_ascii=True,
                    )
                )
            except Exception:
                dead.add(ws)
        if dead:
            async with self._lock:
                st2 = self._bots.get(bot_id)
                if st2 is not None:
                    for ws in dead:
                        st2.browsers.discard(ws)

    async def _send_worker(self, bot_id: str, msg: dict[str, Any]) -> bool:
        st = await self._get(bot_id)
        if st.worker_ws is None:
            return False
        try:
            await st.worker_ws.send_text(json.dumps(msg, ensure_ascii=True))
            return True
        except Exception:
            async with self._lock:
                st2 = self._bots.get(bot_id)
                if st2 is not None and st2.worker_ws is st.worker_ws:
                    st2.worker_ws = None
            return False

    async def _set_hijack_owner(self, bot_id: str, owner: WebSocket | None, lease_s: int | None = None) -> None:
        async with self._lock:
            st = self._bots.setdefault(bot_id, BotTermState())
            st.hijack_owner = owner
            if owner is None:
                st.hijack_owner_expires_at = None
            else:
                ttl = self._dashboard_hijack_lease_s if lease_s is None else max(1, min(int(lease_s), 600))
                st.hijack_owner_expires_at = time.time() + ttl

    async def _touch_hijack_owner(self, bot_id: str, lease_s: int | None = None) -> float | None:
        async with self._lock:
            st = self._bots.get(bot_id)
            if st is None or st.hijack_owner is None:
                return None
            ttl = self._dashboard_hijack_lease_s if lease_s is None else max(1, min(int(lease_s), 600))
            st.hijack_owner_expires_at = time.time() + ttl
            return st.hijack_owner_expires_at

    async def _is_owner(self, bot_id: str, ws: WebSocket) -> bool:
        st = await self._get(bot_id)
        return self._is_dashboard_hijack_active(st) and st.hijack_owner is ws

    async def _hijack_state_msg_for(self, bot_id: str, ws: WebSocket) -> dict[str, Any]:
        st = await self._get(bot_id)
        lease_expires_at = (
            st.hijack_session.lease_expires_at
            if self._is_rest_session_active(st) and st.hijack_session is not None
            else st.hijack_owner_expires_at
        )
        if self._is_dashboard_hijack_active(st) and st.hijack_owner is ws:
            owner: str | None = "me"
        elif self._is_dashboard_hijack_active(st) or self._is_rest_session_active(st):
            owner = "other"
        else:
            owner = None
        return {
            "type": "hijack_state",
            "hijacked": self._is_hijacked(st),
            "owner": owner,
            "lease_expires_at": lease_expires_at,
        }

    async def _request_snapshot(self, bot_id: str) -> None:
        await self._send_worker(bot_id, {"type": "snapshot_req", "req_id": str(uuid.uuid4()), "ts": time.time()})

    async def _request_analysis(self, bot_id: str) -> None:
        await self._send_worker(bot_id, {"type": "analyze_req", "req_id": str(uuid.uuid4()), "ts": time.time()})

    def create_router(self) -> Any:
        """Create and return a FastAPI ``APIRouter`` with all terminal routes registered."""
        from fastapi import APIRouter

        from undef.terminal.hijack.routes import register_rest_routes, register_ws_routes

        router = APIRouter()
        register_rest_routes(self, router)
        register_ws_routes(self, router)
        return router
