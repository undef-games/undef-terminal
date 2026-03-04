from __future__ import annotations

import json
import time
from typing import Any

try:
    from undef_terminal_cloudflare.api.http_routes import route_http
    from undef_terminal_cloudflare.api.ws_routes import handle_socket_message
    from undef_terminal_cloudflare.bridge.hijack import HijackCoordinator, HijackSession
    from undef_terminal_cloudflare.cf_types import DurableObject, Response
    from undef_terminal_cloudflare.config import CloudflareConfig
    from undef_terminal_cloudflare.state.store import LeaseRecord, SqliteStateStore
except Exception:
    from api.http_routes import route_http
    from api.ws_routes import handle_socket_message
    from bridge.hijack import HijackCoordinator, HijackSession
    from cf_types import DurableObject, Response
    from config import CloudflareConfig
    from state.store import LeaseRecord, SqliteStateStore


class SessionRuntime(DurableObject):
    """Durable Object runtime for one worker/session channel."""

    def __init__(self, ctx: Any, env: Any):
        super().__init__(ctx, env)
        self.config = CloudflareConfig.from_env(env)
        sql_exec = getattr(getattr(ctx, "storage", object()), "sql", None)
        if sql_exec is None or not hasattr(sql_exec, "exec"):
            raise RuntimeError("Durable Object sqlite storage is required")
        self.store = SqliteStateStore(sql_exec.exec)
        self.store.migrate()

        self.worker_id = self._derive_worker_id()
        self.hijack = HijackCoordinator()
        self.worker_ws: Any | None = None
        self.browser_sockets: set[Any] = set()
        self.browser_hijack_owner: dict[Any, str] = {}
        self.last_snapshot: dict[str, Any] | None = None

        self._restore_state()

    def _derive_worker_id(self) -> str:
        name = getattr(getattr(self.ctx, "id", object()), "name", None)
        if callable(name):
            try:
                return str(name())
            except Exception:
                return "default"
        return "default"

    def _restore_state(self) -> None:
        row = self.store.load_session(self.worker_id)
        if row is None:
            return
        hijack_id = row.get("hijack_id")
        owner = row.get("owner")
        lease_expires_at = row.get("lease_expires_at")
        if isinstance(hijack_id, str) and isinstance(owner, str) and isinstance(lease_expires_at, (float, int)):
            if float(lease_expires_at) > time.time():
                self.hijack._session = HijackSession(
                    hijack_id=hijack_id,
                    owner=owner,
                    lease_expires_at=float(lease_expires_at),
                )
        snapshot = row.get("last_snapshot")
        if isinstance(snapshot, dict):
            self.last_snapshot = snapshot

    async def fetch(self, request: object) -> Response:
        return await route_http(self, request)

    async def webSocketOpen(self, ws: Any) -> None:  # noqa: N802
        role = self._socket_role(ws)
        if role == "worker":
            self.worker_ws = ws
            await self.broadcast_to_browsers(
                {"type": "worker_connected", "worker_id": self.worker_id, "ts": time.time()}
            )
        else:
            self.browser_sockets.add(ws)
            await self.send_ws(
                ws,
                {
                    "type": "hello",
                    "worker_id": self.worker_id,
                    "worker_online": self.worker_ws is not None,
                    "ts": time.time(),
                },
            )
            await self.send_hijack_state(ws)
            if self.last_snapshot is not None:
                await self.send_ws(ws, self.last_snapshot)

    async def webSocketMessage(self, ws: Any, message: Any) -> None:  # noqa: N802
        raw = message if isinstance(message, str) else str(message)
        await handle_socket_message(self, ws, raw, is_worker=(self._socket_role(ws) == "worker"))

    async def webSocketClose(self, ws: Any, code: int, reason: str, was_clean: bool = True) -> None:  # noqa: N802
        _ = (code, reason, was_clean)
        if ws is self.worker_ws:
            self.worker_ws = None
            await self.broadcast_to_browsers(
                {"type": "worker_disconnected", "worker_id": self.worker_id, "ts": time.time()}
            )
        self.browser_sockets.discard(ws)
        self.browser_hijack_owner.pop(ws, None)

    def _socket_role(self, ws: Any) -> str:
        try:
            role = ws.deserializeAttachment().get("role")
            if isinstance(role, str):
                return role
        except Exception:
            pass
        return "browser"

    async def request_json(self, request: object) -> dict[str, Any]:
        body = await request.text()  # type: ignore[attr-defined]
        if not body:
            return {}
        value = json.loads(body)
        if not isinstance(value, dict):
            return {}
        return value

    def persist_lease(self, session: HijackSession | None) -> None:
        if session is None:
            return
        self.store.save_lease(
            LeaseRecord(
                worker_id=self.worker_id,
                hijack_id=session.hijack_id,
                owner=session.owner,
                lease_expires_at=session.lease_expires_at,
            )
        )

    def clear_lease(self) -> None:
        self.store.clear_lease(self.worker_id)

    async def send_ws(self, ws: Any, payload: dict[str, Any]) -> None:
        await ws.send(json.dumps(payload, ensure_ascii=True))

    async def send_hijack_state(self, ws: Any) -> None:
        session = self.hijack.session
        owner = None
        if session is not None:
            owner = "me" if self.browser_hijack_owner.get(ws) == session.hijack_id else "other"
        await self.send_ws(
            ws,
            {
                "type": "hijack_state",
                "hijacked": session is not None,
                "owner": owner,
                "lease_expires_at": (session.lease_expires_at if session is not None else None),
                "ts": time.time(),
            },
        )

    async def broadcast_hijack_state(self) -> None:
        for ws in list(self.browser_sockets):
            try:
                await self.send_hijack_state(ws)
            except Exception:
                self.browser_sockets.discard(ws)
                self.browser_hijack_owner.pop(ws, None)

    async def push_worker_control(self, action: str, *, owner: str, lease_s: int) -> bool:
        if self.worker_ws is None:
            return False
        await self.send_ws(
            self.worker_ws,
            {"type": "control", "action": action, "owner": owner, "lease_s": lease_s, "ts": time.time()},
        )
        return True

    async def push_worker_input(self, data: str) -> bool:
        if self.worker_ws is None:
            return False
        await self.send_ws(self.worker_ws, {"type": "input", "data": data, "ts": time.time()})
        return True

    async def broadcast_to_browsers(self, payload: dict[str, Any]) -> None:
        evt = self.store.append_event(self.worker_id, str(payload.get("type") or "event"), payload)
        _ = evt
        for ws in list(self.browser_sockets):
            try:
                await self.send_ws(ws, payload)
            except Exception:
                self.browser_sockets.discard(ws)
                self.browser_hijack_owner.pop(ws, None)
