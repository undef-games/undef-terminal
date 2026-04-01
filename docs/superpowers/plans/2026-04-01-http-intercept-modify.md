# HTTP Intercept/Modify Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add pause/edit/forward/drop capability to `uterm inspect`, with browser-togglable intercept mode and proxy on/off control.

**Architecture:** An `InterceptGate` class manages pending requests as `asyncio.Future` objects. The CLI proxy pauses after sending `http_req` when intercept is enabled, awaiting a browser `http_action` response via the tunnel WS. The browser toggle and action buttons send messages on CHANNEL_HTTP (0x03) back through the CF Worker relay. A separate inspection toggle controls whether `http_req`/`http_res` frames are sent at all — when off, the proxy forwards silently (pure passthrough).

**Tech Stack:** Python (asyncio, httpx, uvicorn, websockets), TypeScript (vanilla DOM), existing tunnel protocol on channel 0x03.

---

## File Structure

| File | Responsibility | Action |
|------|---------------|--------|
| `packages/undef-terminal/src/undef/terminal/tunnel/intercept.py` | `InterceptGate` class + `InterceptDecision` TypedDict | **Create** (~80 LOC) |
| `packages/undef-terminal/src/undef/terminal/cli/inspect.py` | CLI flags, proxy gate integration, WS action receiver | **Modify** (+60 LOC) |
| `packages/undef-terminal-frontend/src/app/types.ts` | New TS types for intercept messages | **Modify** (+25 LOC) |
| `packages/undef-terminal-frontend/src/app/views/inspect-view.ts` | Toggle, action bar, editor panel | **Modify** (+130 LOC) |
| `packages/undef-terminal-cloudflare/src/undef/terminal/cloudflare/api/ws_routes.py` | Relay `http_action`/`http_intercept_toggle` browser→worker | **Modify** (+5 LOC) |
| `packages/undef-terminal/tests/tunnel/test_intercept_gate.py` | Unit tests for InterceptGate | **Create** (~200 LOC) |
| `packages/undef-terminal-cloudflare/tests/test_ws_routes.py` | CF relay tests for new message types | **Modify** (+40 LOC) |
| `packages/undef-terminal-frontend/tests/inspect-intercept.test.ts` | Frontend vitest for intercept UI | **Create** (~100 LOC) |

---

### Task 1: InterceptGate — Core State Machine

**Files:**
- Create: `packages/undef-terminal/src/undef/terminal/tunnel/intercept.py`
- Create: `packages/undef-terminal/tests/tunnel/test_intercept_gate.py`

- [ ] **Step 1: Write InterceptDecision TypedDict and InterceptGate skeleton test**

```python
# packages/undef-terminal/tests/tunnel/test_intercept_gate.py
#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Unit tests for InterceptGate — pause/resume/timeout state machine."""

from __future__ import annotations

import asyncio

import pytest

from undef.terminal.tunnel.intercept import InterceptDecision, InterceptGate


class TestInterceptGateBasics:
    def test_initial_state_disabled(self) -> None:
        gate = InterceptGate(timeout_s=5.0, timeout_action="forward")
        assert gate.enabled is False
        assert gate.inspect_enabled is True
        assert gate.pending_count == 0

    def test_enable_disable(self) -> None:
        gate = InterceptGate(timeout_s=5.0, timeout_action="forward")
        gate.enabled = True
        assert gate.enabled is True
        gate.enabled = False
        assert gate.enabled is False

    def test_inspect_toggle(self) -> None:
        gate = InterceptGate(timeout_s=5.0, timeout_action="forward")
        assert gate.inspect_enabled is True
        gate.inspect_enabled = False
        assert gate.inspect_enabled is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/undef-terminal/tests/tunnel/test_intercept_gate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'undef.terminal.tunnel.intercept'`

- [ ] **Step 3: Write InterceptGate implementation**

```python
# packages/undef-terminal/src/undef/terminal/tunnel/intercept.py
#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""InterceptGate — pause/resume state machine for HTTP request interception."""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any, TypedDict

logger = logging.getLogger(__name__)


class InterceptDecision(TypedDict):
    """Browser's decision for a paused request."""

    action: str  # "forward" | "drop" | "modify"
    headers: dict[str, str] | None
    body: bytes | None


def _default_decision(action: str) -> InterceptDecision:
    return InterceptDecision(action=action, headers=None, body=None)


def parse_action_message(msg: dict[str, Any]) -> InterceptDecision:
    """Parse an http_action message from the browser into an InterceptDecision."""
    action = str(msg.get("action", "forward"))
    if action not in ("forward", "drop", "modify"):
        action = "forward"
    headers: dict[str, str] | None = None
    body: bytes | None = None
    if action == "modify":
        raw_headers = msg.get("headers")
        if isinstance(raw_headers, dict):
            headers = {str(k): str(v) for k, v in raw_headers.items()}
        body_b64 = msg.get("body_b64")
        if isinstance(body_b64, str):
            try:
                body = base64.b64decode(body_b64)
            except Exception:
                logger.warning("intercept_invalid_body_b64 id=%s", msg.get("id"))
    return InterceptDecision(action=action, headers=headers, body=body)


class InterceptGate:
    """Manages pending intercepted HTTP requests as asyncio Futures."""

    def __init__(self, timeout_s: float = 30.0, timeout_action: str = "forward") -> None:
        self.enabled: bool = False
        self.inspect_enabled: bool = True  # when False, proxy is silent passthrough
        self.timeout_s: float = max(1.0, timeout_s)
        self.timeout_action: str = timeout_action if timeout_action in ("forward", "drop") else "forward"
        self._pending: dict[str, asyncio.Future[InterceptDecision]] = {}

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    async def await_decision(self, rid: str) -> InterceptDecision:
        """Block until browser sends http_action or timeout expires."""
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[InterceptDecision] = loop.create_future()
        self._pending[rid] = fut
        try:
            return await asyncio.wait_for(fut, timeout=self.timeout_s)
        except TimeoutError:
            return _default_decision(self.timeout_action)
        finally:
            self._pending.pop(rid, None)

    def resolve(self, rid: str, decision: InterceptDecision) -> bool:
        """Resolve a pending request. Returns True if the request was found."""
        fut = self._pending.get(rid)
        if fut is None or fut.done():
            return False
        fut.set_result(decision)
        return True

    def cancel_all(self, action: str = "forward") -> int:
        """Resolve all pending requests. Returns count resolved."""
        decision = _default_decision(action)
        count = 0
        for fut in self._pending.values():
            if not fut.done():
                fut.set_result(decision)
                count += 1
        self._pending.clear()
        return count
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/undef-terminal/tests/tunnel/test_intercept_gate.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add packages/undef-terminal/src/undef/terminal/tunnel/intercept.py packages/undef-terminal/tests/tunnel/test_intercept_gate.py
git commit -m "feat(tunnel): add InterceptGate skeleton with basic state tests"
```

---

### Task 2: InterceptGate — Resolve and Timeout Tests

**Files:**
- Modify: `packages/undef-terminal/tests/tunnel/test_intercept_gate.py`

- [ ] **Step 1: Add resolve, timeout, and cancel tests**

Append to `test_intercept_gate.py`:

```python
class TestInterceptGateResolve:
    async def test_resolve_pending_request(self) -> None:
        gate = InterceptGate(timeout_s=5.0, timeout_action="forward")
        decision: InterceptDecision = {"action": "drop", "headers": None, "body": None}

        async def _resolve_after_delay() -> None:
            await asyncio.sleep(0.05)
            assert gate.resolve("r1", decision)

        task = asyncio.create_task(_resolve_after_delay())
        result = await gate.await_decision("r1")
        await task
        assert result["action"] == "drop"
        assert gate.pending_count == 0

    async def test_resolve_unknown_id_returns_false(self) -> None:
        gate = InterceptGate(timeout_s=5.0, timeout_action="forward")
        decision: InterceptDecision = {"action": "forward", "headers": None, "body": None}
        assert gate.resolve("unknown", decision) is False

    async def test_resolve_already_done_returns_false(self) -> None:
        gate = InterceptGate(timeout_s=0.01, timeout_action="forward")
        # Let it timeout
        result = await gate.await_decision("r1")
        assert result["action"] == "forward"
        # Now try to resolve the same id — should return False (already cleaned up)
        decision: InterceptDecision = {"action": "drop", "headers": None, "body": None}
        assert gate.resolve("r1", decision) is False


class TestInterceptGateTimeout:
    async def test_timeout_uses_forward_action(self) -> None:
        gate = InterceptGate(timeout_s=0.01, timeout_action="forward")
        result = await gate.await_decision("r1")
        assert result["action"] == "forward"
        assert gate.pending_count == 0

    async def test_timeout_uses_drop_action(self) -> None:
        gate = InterceptGate(timeout_s=0.01, timeout_action="drop")
        result = await gate.await_decision("r1")
        assert result["action"] == "drop"

    async def test_timeout_clamps_minimum(self) -> None:
        gate = InterceptGate(timeout_s=0.0, timeout_action="forward")
        assert gate.timeout_s == 1.0

    def test_invalid_timeout_action_defaults_to_forward(self) -> None:
        gate = InterceptGate(timeout_s=5.0, timeout_action="invalid")
        assert gate.timeout_action == "forward"


class TestInterceptGateCancelAll:
    async def test_cancel_all_resolves_pending(self) -> None:
        gate = InterceptGate(timeout_s=30.0, timeout_action="forward")
        results: list[InterceptDecision] = []

        async def _await(rid: str) -> None:
            results.append(await gate.await_decision(rid))

        tasks = [asyncio.create_task(_await(f"r{i}")) for i in range(5)]
        await asyncio.sleep(0.05)  # let futures register
        assert gate.pending_count == 5

        count = gate.cancel_all("drop")
        assert count == 5

        await asyncio.gather(*tasks)
        assert all(r["action"] == "drop" for r in results)
        assert gate.pending_count == 0

    async def test_cancel_all_empty_returns_zero(self) -> None:
        gate = InterceptGate(timeout_s=5.0, timeout_action="forward")
        assert gate.cancel_all() == 0


class TestParseActionMessage:
    def test_forward_action(self) -> None:
        from undef.terminal.tunnel.intercept import parse_action_message

        result = parse_action_message({"action": "forward", "id": "r1"})
        assert result["action"] == "forward"
        assert result["headers"] is None
        assert result["body"] is None

    def test_modify_with_headers_and_body(self) -> None:
        import base64

        from undef.terminal.tunnel.intercept import parse_action_message

        body = base64.b64encode(b'{"key": "val"}').decode()
        result = parse_action_message({
            "action": "modify",
            "headers": {"Content-Type": "application/json"},
            "body_b64": body,
        })
        assert result["action"] == "modify"
        assert result["headers"] == {"Content-Type": "application/json"}
        assert result["body"] == b'{"key": "val"}'

    def test_modify_with_invalid_b64_keeps_body_none(self) -> None:
        from undef.terminal.tunnel.intercept import parse_action_message

        result = parse_action_message({"action": "modify", "body_b64": "!!!invalid!!!"})
        assert result["action"] == "modify"
        assert result["body"] is None

    def test_unknown_action_defaults_to_forward(self) -> None:
        from undef.terminal.tunnel.intercept import parse_action_message

        result = parse_action_message({"action": "explode"})
        assert result["action"] == "forward"

    def test_missing_action_defaults_to_forward(self) -> None:
        from undef.terminal.tunnel.intercept import parse_action_message

        result = parse_action_message({})
        assert result["action"] == "forward"

    def test_modify_with_non_dict_headers_ignored(self) -> None:
        from undef.terminal.tunnel.intercept import parse_action_message

        result = parse_action_message({"action": "modify", "headers": "bad"})
        assert result["headers"] is None


class TestConcurrentRequests:
    async def test_multiple_concurrent_requests(self) -> None:
        gate = InterceptGate(timeout_s=5.0, timeout_action="forward")
        results: dict[str, str] = {}

        async def _await(rid: str) -> None:
            r = await gate.await_decision(rid)
            results[rid] = r["action"]

        tasks = [asyncio.create_task(_await(f"r{i}")) for i in range(10)]
        await asyncio.sleep(0.05)
        assert gate.pending_count == 10

        for i in range(10):
            action = "forward" if i % 2 == 0 else "drop"
            gate.resolve(f"r{i}", {"action": action, "headers": None, "body": None})

        await asyncio.gather(*tasks)
        assert len(results) == 10
        assert results["r0"] == "forward"
        assert results["r1"] == "drop"
```

- [ ] **Step 2: Run all tests**

Run: `uv run pytest packages/undef-terminal/tests/tunnel/test_intercept_gate.py -v`
Expected: 18 PASS

- [ ] **Step 3: Verify 100% coverage**

Run: `uv run pytest packages/undef-terminal/tests/tunnel/test_intercept_gate.py --cov=undef.terminal.tunnel.intercept --cov-branch --cov-report=term-missing`
Expected: 100%

- [ ] **Step 4: Commit**

```bash
git add packages/undef-terminal/tests/tunnel/test_intercept_gate.py
git commit -m "test(tunnel): add full InterceptGate unit tests — resolve, timeout, cancel, parse"
```

---

### Task 3: CLI Flags + Proxy Integration

**Files:**
- Modify: `packages/undef-terminal/src/undef/terminal/cli/inspect.py`

- [ ] **Step 1: Add CLI flags to `add_inspect_subcommand()`**

Add after the `--display-name` argument (before `inspect_p.set_defaults`):

```python
    inspect_p.add_argument(
        "--intercept",
        action="store_true",
        default=False,
        help="enable HTTP request interception (pause before forwarding)",
    )
    inspect_p.add_argument(
        "--intercept-timeout",
        type=float,
        metavar="SECONDS",
        default=30.0,
        help="seconds to wait for browser action before auto-resolving (default: 30)",
    )
    inspect_p.add_argument(
        "--intercept-timeout-action",
        choices=["forward", "drop"],
        default="forward",
        help="action on timeout: forward (default) or drop",
    )
```

- [ ] **Step 2: Wire InterceptGate into `_cmd_inspect` and `_run_inspect`**

In `_cmd_inspect`, after `token = _read_token(args)`, add:

```python
    intercept = getattr(args, "intercept", False)
    intercept_timeout = getattr(args, "intercept_timeout", 30.0)
    intercept_timeout_action = getattr(args, "intercept_timeout_action", "forward")
```

Pass these to `_run_inspect`:

```python
    asyncio.run(_run_inspect(
        ws_endpoint, worker_token, target_port, listen_port,
        intercept=intercept,
        intercept_timeout=intercept_timeout,
        intercept_timeout_action=intercept_timeout_action,
    ))
```

Update `_run_inspect` signature:

```python
async def _run_inspect(
    ws_endpoint: str, worker_token: str, target_port: int, listen_port: int,
    *, intercept: bool = False, intercept_timeout: float = 30.0,
    intercept_timeout_action: str = "forward",
) -> None:
```

Inside `_run_inspect`, after `req_counter = 0`:

```python
    from undef.terminal.tunnel.intercept import InterceptGate, parse_action_message

    gate = InterceptGate(timeout_s=intercept_timeout, timeout_action=intercept_timeout_action)
    gate.enabled = intercept
```

- [ ] **Step 3: Add intercept gate to `_proxy_app`**

In `_proxy_app`, after sending `http_req` frame (line ~196), add the intercept gate logic. Replace the current forwarding block with:

```python
        # Add intercepted flag to the request event
        req_event["intercepted"] = gate.enabled

        # Only send inspection frames when inspect is enabled (not silent passthrough)
        if gate.inspect_enabled:
            with suppress(Exception):
                await ws.send(encode_frame(CHANNEL_HTTP, json.dumps(req_event, separators=(",", ":")).encode()))

            print(format_log_line(method, path, None, None, len(req_body)), file=sys.stderr)
            await ws.send(
                encode_frame(CHANNEL_DATA, (format_log_line(method, path, None, None, len(req_body)) + "\n").encode())
            )

        # Intercept gate: wait for browser decision if enabled (requires inspect to be on)
        fwd_headers = {k: v for k, v in req_headers.items() if k.lower() not in ("host", "transfer-encoding")}
        fwd_body = req_body

        if gate.enabled and gate.inspect_enabled:
            decision = await gate.await_decision(rid)
            if decision["action"] == "drop":
                await send({"type": "http.response.start", "status": 502, "headers": [(b"content-type", b"text/plain")]})
                await send({"type": "http.response.body", "body": b"Request dropped by interceptor"})
                # Send a synthetic http_res so the browser shows the drop
                drop_event: dict[str, Any] = {
                    "type": "http_res", "id": rid, "ts": time.time(),
                    "status": 502, "status_text": "Dropped",
                    "headers": {}, "body_size": 0, "duration_ms": 0,
                }
                with suppress(Exception):
                    await ws.send(encode_frame(CHANNEL_HTTP, json.dumps(drop_event, separators=(",", ":")).encode()))
                return
            if decision["action"] == "modify":
                if decision["headers"] is not None:
                    fwd_headers = decision["headers"]
                if decision["body"] is not None:
                    fwd_body = decision["body"]

        # Forward to target
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient() as client:
                upstream = await client.request(method, target_url, headers=fwd_headers, content=fwd_body)
                # ... rest of existing forwarding code unchanged ...
```

- [ ] **Step 4: Add WS receive loop for http_action messages**

In `_run_inspect`, after starting uvicorn, add a background task that reads from the WS and dispatches `http_action` and `http_intercept_toggle` messages:

```python
    async def _ws_action_receiver() -> None:
        """Read http_action/toggle messages from the tunnel WS."""
        from undef.terminal.tunnel.protocol import CHANNEL_HTTP, decode_frame

        try:
            async for raw in ws:
                if isinstance(raw, bytes) and len(raw) > 2:
                    frame = decode_frame(raw)
                    if frame.channel == CHANNEL_HTTP:
                        try:
                            msg = json.loads(frame.payload)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            continue
                        msg_type = msg.get("type")
                        if msg_type == "http_action":
                            decision = parse_action_message(msg)
                            rid = str(msg.get("id", ""))
                            if not gate.resolve(rid, decision):
                                log.warning("intercept_unknown_id id=%s", rid)
                        elif msg_type == "http_intercept_toggle":
                            gate.enabled = bool(msg.get("enabled", False))
                            if not gate.enabled:
                                gate.cancel_all("forward")
                            # Broadcast state back
                            state_msg = {
                                "type": "http_intercept_state",
                                "enabled": gate.enabled,
                                "inspect_enabled": gate.inspect_enabled,
                                "timeout_s": gate.timeout_s,
                                "timeout_action": gate.timeout_action,
                            }
                            with suppress(Exception):
                                await ws.send(encode_frame(CHANNEL_HTTP, json.dumps(state_msg).encode()))
                        elif msg_type == "http_inspect_toggle":
                            gate.inspect_enabled = bool(msg.get("enabled", True))
                            if not gate.inspect_enabled:
                                gate.cancel_all("forward")  # can't intercept without inspect
                                gate.enabled = False
                            state_msg = {
                                "type": "http_intercept_state",
                                "enabled": gate.enabled,
                                "inspect_enabled": gate.inspect_enabled,
                                "timeout_s": gate.timeout_s,
                                "timeout_action": gate.timeout_action,
                            }
                            with suppress(Exception):
                                await ws.send(encode_frame(CHANNEL_HTTP, json.dumps(state_msg).encode()))
        except Exception:
            gate.cancel_all("forward")

    receiver_task = asyncio.create_task(_ws_action_receiver())
```

And before `await server.serve()`, send the initial intercept state:

```python
    state_msg = {
        "type": "http_intercept_state",
        "enabled": gate.enabled,
        "timeout_s": gate.timeout_s,
        "timeout_action": gate.timeout_action,
    }
    with suppress(Exception):
        await ws.send(encode_frame(CHANNEL_HTTP, json.dumps(state_msg).encode()))
```

- [ ] **Step 5: Commit**

```bash
git add packages/undef-terminal/src/undef/terminal/cli/inspect.py
git commit -m "feat(cli): wire InterceptGate into uterm inspect with CLI flags"
```

---

### Task 4: CF Worker — Relay http_action from Browser to Worker

**Files:**
- Modify: `packages/undef-terminal-cloudflare/src/undef/terminal/cloudflare/api/ws_routes.py`
- Modify: `packages/undef-terminal-cloudflare/tests/test_ws_routes.py`

- [ ] **Step 1: Write failing test**

Append to `packages/undef-terminal-cloudflare/tests/test_ws_routes.py`:

```python
# ---------------------------------------------------------------------------
# Intercept — http_action / http_intercept_toggle relay
# ---------------------------------------------------------------------------


async def test_http_action_relayed_to_worker() -> None:
    """http_action from browser is forwarded to the worker WS."""
    runtime = _Runtime(input_mode="open")
    runtime.worker_ws = _Ws()
    browser = _Ws()
    await handle_socket_message(runtime, browser, _raw("http_action", id="r1", action="forward"), is_worker=False)
    assert len(runtime._sent) == 1
    assert runtime._sent[0]["type"] == "http_action"


async def test_http_intercept_toggle_relayed_to_worker() -> None:
    """http_intercept_toggle from browser is forwarded to the worker WS."""
    runtime = _Runtime(input_mode="open")
    runtime.worker_ws = _Ws()
    browser = _Ws()
    await handle_socket_message(runtime, browser, _raw("http_intercept_toggle", enabled=True), is_worker=False)
    assert len(runtime._sent) == 1
    assert runtime._sent[0]["type"] == "http_intercept_toggle"


async def test_http_inspect_toggle_relayed_to_worker() -> None:
    """http_inspect_toggle from browser is forwarded to the worker WS."""
    runtime = _Runtime(input_mode="open")
    runtime.worker_ws = _Ws()
    browser = _Ws()
    await handle_socket_message(runtime, browser, _raw("http_inspect_toggle", enabled=False), is_worker=False)
    assert len(runtime._sent) == 1
    assert runtime._sent[0]["type"] == "http_inspect_toggle"


async def test_http_action_dropped_when_no_worker() -> None:
    """http_action silently dropped when worker is not connected."""
    runtime = _Runtime(input_mode="open")
    runtime.worker_ws = None
    browser = _Ws()
    await handle_socket_message(runtime, browser, _raw("http_action", id="r1", action="drop"), is_worker=False)
    assert not runtime._sent
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/undef-terminal-cloudflare/tests/test_ws_routes.py -k "http_action or http_intercept_toggle" -v`
Expected: FAIL — http_action not handled

- [ ] **Step 3: Add relay to ws_routes.py**

In `handle_socket_message`, add before the `# heartbeat / ping` comment (after the presence_update elif):

```python
        elif frame_type in {"http_action", "http_intercept_toggle", "http_inspect_toggle"}:
            # Relay intercept/inspect commands from browser back to the worker (tunnel agent)
            if runtime.worker_ws is not None:
                await runtime.send_ws(runtime.worker_ws, frame)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest packages/undef-terminal-cloudflare/tests/test_ws_routes.py -v`
Expected: ALL PASS (including new 3)

- [ ] **Step 5: Verify CF coverage still 100%**

Run: `uv run pytest packages/undef-terminal-cloudflare/tests/ --cov=undef.terminal.cloudflare.api.ws_routes --cov-branch --cov-report=term-missing -q`
Expected: 100%

- [ ] **Step 6: Commit**

```bash
git add packages/undef-terminal-cloudflare/src/undef/terminal/cloudflare/api/ws_routes.py packages/undef-terminal-cloudflare/tests/test_ws_routes.py
git commit -m "feat(cf): relay http_action and http_intercept_toggle from browser to worker"
```

---

### Task 5: Frontend Types

**Files:**
- Modify: `packages/undef-terminal-frontend/src/app/types.ts`

- [ ] **Step 1: Extend types**

Add after `HttpExchangeEntry`:

```typescript
export interface HttpActionMessage {
  type: "http_action";
  id: string;
  action: "forward" | "drop" | "modify";
  headers?: Record<string, string>;
  body_b64?: string;
}

export interface HttpInterceptToggle {
  type: "http_intercept_toggle";
  enabled: boolean;
}

export interface HttpInterceptState {
  type: "http_intercept_state";
  enabled: boolean;
  timeout_s: number;
  timeout_action: string;
}
```

Extend `HttpRequestEntry` with optional `intercepted`:

```typescript
export interface HttpRequestEntry {
  type: "http_req";
  id: string;
  ts: number;
  method: string;
  url: string;
  headers: Record<string, string>;
  body_size: number;
  body_b64?: string;
  body_truncated?: boolean;
  body_binary?: boolean;
  intercepted?: boolean;  // new
}
```

Extend `HttpExchangeEntry`:

```typescript
export interface HttpExchangeEntry {
  id: string;
  request: HttpRequestEntry;
  response: HttpResponseEntry | null;
  intercepted: boolean;         // new
  interceptResolved: boolean;   // new
  interceptAction: string | null; // new
}
```

- [ ] **Step 2: Build to verify types compile**

Run: `cd packages/undef-terminal-frontend && npx tsc --noEmit`
Expected: no errors (existing code may need minor updates to pass new required fields)

- [ ] **Step 3: Update inspect-view.ts exchange creation to include new fields**

In `inspect-view.ts`, update the `http_req` handler:

```typescript
      if (type === "http_req") {
        const req = frame as unknown as HttpRequestEntry;
        state.exchanges.push({
          id: req.id,
          request: req,
          response: null,
          intercepted: req.intercepted ?? false,
          interceptResolved: false,
          interceptAction: null,
        });
```

- [ ] **Step 4: Build and run tests**

Run: `cd packages/undef-terminal-frontend && npx vitest run`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add packages/undef-terminal-frontend/src/app/types.ts packages/undef-terminal-frontend/src/app/views/inspect-view.ts
git commit -m "feat(frontend): add intercept types and extend HttpExchangeEntry"
```

---

### Task 6: Frontend — Intercept Toggle + Action Bar

**Files:**
- Modify: `packages/undef-terminal-frontend/src/app/views/inspect-view.ts`

- [ ] **Step 1: Add intercept state to InspectState**

```typescript
interface InspectState {
  exchanges: HttpExchangeEntry[];
  selected: string | null;
  ws: WebSocket | null;
  interceptEnabled: boolean;
  interceptTimeout: number;
  interceptTimeoutAction: string;
}
```

Update initial state:

```typescript
const state: InspectState = {
  exchanges: [], selected: null, ws: null,
  interceptEnabled: false, interceptTimeout: 30, interceptTimeoutAction: "forward",
};
```

- [ ] **Step 2: Add intercept toggle button to toolbar**

In the toolbar HTML (after `inspect-status` span):

```html
<button id="inspect-inspect-toggle" class="btn-toggle active">Inspect: ON</button>
<button id="inspect-intercept-toggle" class="btn-toggle">Intercept: OFF</button>
```

Wire up both toggles after element queries:

```typescript
const inspectToggle = requireElement<HTMLButtonElement>("#inspect-inspect-toggle", root);
const interceptToggle = requireElement<HTMLButtonElement>("#inspect-intercept-toggle", root);

inspectToggle.addEventListener("click", () => {
  const newEnabled = !state.interceptEnabled || !state.interceptEnabled; // toggle inspect
  // Use a separate state field
  const inspectOn = inspectToggle.classList.contains("active");
  const newInspect = !inspectOn;
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify({ type: "http_inspect_toggle", enabled: newInspect }));
  }
  inspectToggle.textContent = `Inspect: ${newInspect ? "ON" : "OFF"}`;
  inspectToggle.classList.toggle("active", newInspect);
  if (!newInspect) {
    // Disable intercept too — can't intercept without inspect
    state.interceptEnabled = false;
    interceptToggle.textContent = "Intercept: OFF";
    interceptToggle.classList.remove("active");
  }
});

interceptToggle.addEventListener("click", () => {
  const newEnabled = !state.interceptEnabled;
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    const msg: HttpInterceptToggle = { type: "http_intercept_toggle", enabled: newEnabled };
    state.ws.send(JSON.stringify(msg));
  }
  state.interceptEnabled = newEnabled;
  interceptToggle.textContent = `Intercept: ${newEnabled ? "ON" : "OFF"}`;
  interceptToggle.classList.toggle("active", newEnabled);
});
```

- [ ] **Step 3: Add action buttons to detail view for intercepted requests**

In `renderDetail()`, after the request headers section, add:

```typescript
  // Intercept action bar
  let actionBar = "";
  if (ex.intercepted && !ex.interceptResolved && !ex.response) {
    actionBar = `
      <div class="inspect-action-bar">
        <span class="badge paused">PAUSED</span>
        <button class="btn-action btn-forward" data-action="forward" data-id="${r.id}">Forward</button>
        <button class="btn-action btn-drop" data-action="drop" data-id="${r.id}">Drop</button>
        <button class="btn-action btn-modify" data-action="modify" data-id="${r.id}">Modify & Forward</button>
      </div>
    `;
  } else if (ex.interceptAction) {
    const label = ex.interceptAction.replace("-", " ");
    actionBar = `<div class="inspect-action-bar"><span class="badge resolved">${label}</span></div>`;
  }
```

Insert `actionBar` into the returned HTML after the status line.

- [ ] **Step 4: Wire action button click handlers**

In `showDetail()`, after rendering, add:

```typescript
    // Wire action buttons
    detailEl.querySelectorAll(".btn-action").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const el = e.target as HTMLElement;
        const action = el.dataset.action ?? "forward";
        const id = el.dataset.id ?? "";
        if (action === "modify") {
          showModifyEditor(id);
          return;
        }
        sendAction(id, action);
      });
    });
```

Add helper functions:

```typescript
  function sendAction(id: string, action: string, headers?: Record<string, string>, bodyB64?: string): void {
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return;
    const msg: Record<string, unknown> = { type: "http_action", id, action };
    if (headers) msg.headers = headers;
    if (bodyB64) msg.body_b64 = bodyB64;
    state.ws.send(JSON.stringify(msg));
    // Mark as resolved
    const ex = state.exchanges.find((e) => e.id === id);
    if (ex) {
      ex.interceptResolved = true;
      ex.interceptAction = action;
      showDetail(id);
    }
  }

  function showModifyEditor(id: string): void {
    const ex = state.exchanges.find((e) => e.id === id);
    if (!ex) return;
    const r = ex.request;
    const body = r.body_b64 ? atob(r.body_b64) : "";
    const headersHtml = Object.entries(r.headers)
      .map(([k, v], i) => `<div><input value="${k}" data-idx="${i}" class="hdr-key"/> <input value="${v}" data-idx="${i}" class="hdr-val"/></div>`)
      .join("");

    detailEl.innerHTML += `
      <div class="inspect-editor" id="inspect-editor">
        <h4>Modify Request</h4>
        <div class="editor-headers">${headersHtml}</div>
        <h4>Body</h4>
        <textarea id="editor-body" rows="8">${body}</textarea>
        <button id="editor-send" class="btn-action btn-forward">Send Modified</button>
      </div>
    `;

    requireElement<HTMLButtonElement>("#editor-send", root).addEventListener("click", () => {
      const newBody = requireElement<HTMLTextAreaElement>("#editor-body", root).value;
      const newHeaders: Record<string, string> = {};
      detailEl.querySelectorAll(".hdr-key").forEach((el) => {
        const keyEl = el as HTMLInputElement;
        const valEl = detailEl.querySelector(`.hdr-val[data-idx="${keyEl.dataset.idx}"]`) as HTMLInputElement;
        if (keyEl.value && valEl) newHeaders[keyEl.value] = valEl.value;
      });
      sendAction(id, "modify", newHeaders, btoa(newBody));
    });
  }
```

- [ ] **Step 5: Handle http_intercept_state in WS message handler**

In the WS message handler, add after the `http_res` case:

```typescript
      } else if (type === "http_intercept_state") {
        const inspectOn = frame.inspect_enabled !== false;
        state.interceptEnabled = Boolean(frame.enabled);
        state.interceptTimeout = Number(frame.timeout_s ?? 30);
        state.interceptTimeoutAction = String(frame.timeout_action ?? "forward");
        inspectToggle.textContent = `Inspect: ${inspectOn ? "ON" : "OFF"}`;
        inspectToggle.classList.toggle("active", inspectOn);
        interceptToggle.textContent = `Intercept: ${state.interceptEnabled ? "ON" : "OFF"}`;
        interceptToggle.classList.toggle("active", state.interceptEnabled);
```

- [ ] **Step 6: Add PAUSED indicator to request list rows**

In `renderRow()`, add after the status span:

```typescript
  const paused = ex.intercepted && !ex.interceptResolved && !ex.response
    ? '<span class="badge paused">PAUSED</span>'
    : "";
```

Update the function signature to accept `HttpExchangeEntry` (it already does) and insert `${paused}` into the row HTML.

- [ ] **Step 7: Build and test**

Run: `npm run build:frontend && cd packages/undef-terminal-frontend && npx vitest run`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add packages/undef-terminal-frontend/src/
git commit -m "feat(frontend): intercept toggle, action bar, modify editor in inspect view"
```

---

### Task 7: Frontend Tests

**Files:**
- Create: `packages/undef-terminal-frontend/tests/inspect-intercept.test.ts`

- [ ] **Step 1: Write vitest tests for intercept UI behavior**

Test the key behaviors: exchange creation with `intercepted` flag, action message format, toggle state, auto-resolve display. Follow existing vitest patterns in the project.

- [ ] **Step 2: Run tests**

Run: `cd packages/undef-terminal-frontend && npx vitest run`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add packages/undef-terminal-frontend/tests/
git commit -m "test(frontend): add intercept UI vitest tests"
```

---

### Task 8: Full Integration Test + Coverage Gate

**Files:**
- Modify: `packages/undef-terminal/tests/tunnel/test_intercept_gate.py` (add stress test)

- [ ] **Step 1: Add stress test for concurrent requests**

Append to `test_intercept_gate.py`:

```python
class TestInterceptGateStress:
    @pytest.mark.timeout(10)
    async def test_50_concurrent_requests_all_resolved(self) -> None:
        """50 concurrent paused requests all resolve correctly."""
        gate = InterceptGate(timeout_s=5.0, timeout_action="forward")
        results: dict[str, str] = {}

        async def _await(rid: str) -> None:
            r = await gate.await_decision(rid)
            results[rid] = r["action"]

        tasks = [asyncio.create_task(_await(f"r{i}")) for i in range(50)]
        await asyncio.sleep(0.05)
        assert gate.pending_count == 50

        for i in range(50):
            gate.resolve(f"r{i}", {"action": "forward" if i % 3 else "drop", "headers": None, "body": None})

        await asyncio.gather(*tasks)
        assert len(results) == 50
        assert results["r0"] == "drop"
        assert results["r1"] == "forward"

    @pytest.mark.timeout(10)
    async def test_rapid_toggle_resolves_pending(self) -> None:
        """Toggling intercept off resolves all pending as forward."""
        gate = InterceptGate(timeout_s=30.0, timeout_action="drop")
        gate.enabled = True
        results: list[InterceptDecision] = []

        async def _await(rid: str) -> None:
            results.append(await gate.await_decision(rid))

        tasks = [asyncio.create_task(_await(f"r{i}")) for i in range(10)]
        await asyncio.sleep(0.05)

        # Toggle off — should cancel all as "forward"
        gate.enabled = False
        gate.cancel_all("forward")
        await asyncio.gather(*tasks)
        assert all(r["action"] == "forward" for r in results)
```

- [ ] **Step 2: Run full test suite and verify coverage**

Run: `uv run pytest packages/undef-terminal/tests/tunnel/test_intercept_gate.py --cov=undef.terminal.tunnel.intercept --cov-branch --cov-report=term-missing -v`
Expected: 100% coverage, 20 PASS

- [ ] **Step 3: Run full regression**

Run: `uv run pytest packages/undef-terminal/tests/ -q --no-cov --ignore=packages/undef-terminal/tests/memray --ignore=packages/undef-terminal/tests/playwright`
Expected: ALL PASS

Run: `uv run pytest packages/undef-terminal-cloudflare/tests/ -q --no-cov`
Expected: ALL PASS (except pre-existing vendor guard)

Run: `npm run build:frontend && cd packages/undef-terminal-frontend && npx vitest run`
Expected: ALL PASS

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "test(tunnel): add intercept stress tests — 50 concurrent, rapid toggle"
git push origin main
```

---

## Verification Checklist

```bash
# InterceptGate unit tests + coverage
uv run pytest packages/undef-terminal/tests/tunnel/test_intercept_gate.py --cov=undef.terminal.tunnel.intercept --cov-branch --cov-report=term-missing -v

# CF relay tests
uv run pytest packages/undef-terminal-cloudflare/tests/test_ws_routes.py -v

# CF full coverage
uv run pytest packages/undef-terminal-cloudflare/tests/ --cov=undef.terminal.cloudflare --cov-branch -q | grep TOTAL

# Frontend
npm run build:frontend && cd packages/undef-terminal-frontend && npx vitest run

# Full regression
uv run pytest packages/undef-terminal/tests/ -q --no-cov --ignore=packages/undef-terminal/tests/memray --ignore=packages/undef-terminal/tests/playwright

# PTY Docker (100%)
docker build -t undef-pty-test packages/undef-terminal-pty/ -f packages/undef-terminal-pty/Dockerfile.test && docker run --rm undef-pty-test

# Pre-commit
pre-commit run --all-files
```
