# Phase 4: HTTP Intercept/Modify Mode

## Overview

Add pause/edit/forward/drop capability to `uterm inspect`. Requests pause before forwarding to the target server. A browser-connected operator can inspect the request, edit headers/body, then forward, modify, or drop it. Builds on the existing Phase 3 read-only HTTP inspection system.

## Requirements

- **Intercept toggle**: CLI flag `--intercept` enables intercept mode at startup. Browser UI toggle switches it on/off live during a session.
- **Timeout**: Configurable via `--intercept-timeout=30` (seconds). Action on timeout configurable via `--intercept-timeout-action=forward|drop`. Default: 30s, auto-forward.
- **Edit scope**: Headers and body. Method and URL are read-only (keeps the proxy routing predictable).
- **Filtering**: All requests intercepted when enabled. No path filtering (YAGNI).
- **Coverage**: 100% branch+line coverage. All mutants killed or equivalent.

## Protocol Extension

One new message type on CHANNEL_HTTP (0x03). No new channel.

### Browser → Proxy: `http_action`

Sent by the browser to resolve a paused request.

```json
{
  "type": "http_action",
  "id": "r1",
  "action": "forward" | "drop" | "modify",
  "headers": { "Content-Type": "application/json" },
  "body_b64": "eyJ0ZXN0IjogdHJ1ZX0="
}
```

- `action: "forward"` — forward original request unchanged.
- `action: "drop"` — return 502 to the client. Request never reaches the target.
- `action: "modify"` — forward with replaced headers and/or body. `headers` and `body_b64` are optional; omitted fields keep their original values.

### Proxy → Browser: `http_req` extension

The existing `http_req` message gains one field:

```json
{
  "type": "http_req",
  "id": "r1",
  "intercepted": true,
  ...existing fields...
}
```

`intercepted: true` tells the browser to show action buttons instead of a spinner.

### Proxy → Browser: `http_intercept_state`

Sent when intercept mode changes (startup, toggle, or timeout config change).

```json
{
  "type": "http_intercept_state",
  "enabled": true,
  "timeout_s": 30,
  "timeout_action": "forward"
}
```

### Browser → Proxy: `http_intercept_toggle`

Sent when the browser toggle is clicked.

```json
{
  "type": "http_intercept_toggle",
  "enabled": true
}
```

## Architecture

### InterceptGate (new class in `cli/inspect.py`)

Manages pending intercepted requests as `asyncio.Future` objects.

```python
class InterceptGate:
    def __init__(self, timeout_s: float, timeout_action: str) -> None:
        self.enabled: bool = False
        self.timeout_s: float = timeout_s
        self.timeout_action: str = timeout_action  # "forward" | "drop"
        self._pending: dict[str, asyncio.Future[InterceptDecision]] = {}

    async def await_decision(self, rid: str) -> InterceptDecision:
        """Block until browser sends http_action or timeout expires."""

    def resolve(self, rid: str, decision: InterceptDecision) -> None:
        """Resolve a pending request's future with the browser's decision."""

    def cancel_all(self, action: str = "forward") -> None:
        """Resolve all pending with the given action (disconnect cleanup)."""
```

`InterceptDecision` is a TypedDict:
```python
class InterceptDecision(TypedDict):
    action: str  # "forward" | "drop" | "modify"
    headers: dict[str, str] | None
    body: bytes | None
```

### Proxy flow change (inspect.py `_proxy_app`)

Current:
```
send http_req → forward to target immediately
```

With intercept:
```
send http_req (intercepted=gate.enabled) → if gate.enabled: decision = await gate.await_decision(rid)
                                           → apply decision (forward/drop/modify)
                                           → if not gate.enabled: forward immediately (Phase 3 behavior)
```

### WS message receiver

The proxy's WS read loop (which currently only reads terminal data from the tunnel) must also handle incoming `http_action` and `http_intercept_toggle` messages on CHANNEL_HTTP. When received:

- `http_action`: call `gate.resolve(id, decision)`
- `http_intercept_toggle`: set `gate.enabled` and broadcast `http_intercept_state`

### CF Worker relay (tunnel_routes.py)

Currently CHANNEL_HTTP is one-way (worker → browsers). Phase 4 adds the reverse: browser → worker. The CF Worker must relay `http_action` and `http_intercept_toggle` frames from browser WebSockets back to the worker WebSocket.

Add to `handle_socket_message` in `ws_routes.py`:
```python
if frame_type == "http_action" or frame_type == "http_intercept_toggle":
    if runtime.worker_ws is not None:
        await runtime.send_ws(runtime.worker_ws, frame)
    continue
```

### Frontend (inspect-view.ts)

**New UI elements:**

1. **Intercept toggle** — button in the header bar. Sends `http_intercept_toggle` on click.
2. **Paused badge** — yellow "PAUSED" chip on intercepted requests in the list.
3. **Action bar** — appears in the detail panel for paused requests:
   - `[Forward]` — sends `http_action` with `action: "forward"`
   - `[Drop]` — sends `http_action` with `action: "drop"`
   - `[Modify & Forward]` — opens editor, then sends `http_action` with `action: "modify"`
4. **Editor panel** — textarea for body (pre-filled with decoded base64), editable header key-value rows. Only visible when "Modify & Forward" is clicked.
5. **Auto-resolved label** — "(auto-forwarded)" or "(timed out)" badge on requests that resolved via timeout.

**State changes to InspectState:**
```typescript
interface InspectState {
  exchanges: HttpExchangeEntry[];
  selected: string | null;
  ws: WebSocket | null;
  interceptEnabled: boolean;    // new
  interceptTimeout: number;     // new
  interceptTimeoutAction: string; // new
}
```

**HttpExchangeEntry extension:**
```typescript
interface HttpExchangeEntry {
  id: string;
  request: HttpRequestEntry;
  response: HttpResponseEntry | null;
  intercepted: boolean;         // new
  interceptResolved: boolean;   // new — true after action sent
  interceptAction: string | null; // new — "forward" | "drop" | "modify" | "auto-forward" | "auto-drop"
}
```

## Files Modified

| File | Change | Est. LOC |
|------|--------|----------|
| `cli/inspect.py` | InterceptGate class, CLI flags, proxy gate logic, WS action receiver | +100 |
| `tunnel/http_proxy.py` | InterceptDecision TypedDict | +10 |
| `app/views/inspect-view.ts` | Toggle, action bar, editor panel, state | +120 |
| `app/types.ts` | New types, extended interfaces | +20 |
| `api/ws_routes.py` (CF) | Relay http_action/toggle from browser to worker | +5 |
| `api/tunnel_routes.py` (CF) | No change (already relays CHANNEL_HTTP) | 0 |

**New test files:**

| File | Tests | Coverage target |
|------|-------|-----------------|
| `tests/tunnel/test_intercept_gate.py` | 12 | InterceptGate: create, resolve, timeout-forward, timeout-drop, cancel_all, unknown id, double resolve, concurrent |
| `tests/tunnel/test_inspect_intercept.py` | 10 | Integration: proxy + mock target, forward/drop/modify/timeout, toggle on/off, WS disconnect cleanup |
| `tests/test_ws_routes_intercept.py` (CF) | 4 | http_action relay, toggle relay, no worker connected, unknown type ignored |
| Frontend vitest | 8 | Toggle render, action bar, editor panel, state transitions, auto-resolve display |
| `tests/tunnel/test_intercept_stress.py` | 2 | 50 concurrent paused requests resolved, rapid toggle |

**Total: ~36 new tests. 100% branch+line coverage. All mutants killed.**

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Timeout with no browser response | Auto-forward or auto-drop per `--intercept-timeout-action` |
| Proxy WS disconnects while requests pending | `cancel_all("forward")` — all pending auto-forwarded |
| `http_action` for unknown request id | Ignored, logged as warning |
| Multiple browsers send action for same id | First wins, subsequent ignored |
| Modify with invalid base64 body | Forward original body, log warning |
| Intercept toggled off while requests pending | Resolve all pending as "forward" |
| Binary request body in modify | Body not editable (forward-only); UI disables editor |

## Verification

```bash
# Unit tests
uv run pytest packages/undef-terminal/tests/tunnel/test_intercept_gate.py -v
uv run pytest packages/undef-terminal/tests/tunnel/test_inspect_intercept.py -v

# CF relay tests
uv run pytest packages/undef-terminal-cloudflare/tests/test_ws_routes_intercept.py -v

# Frontend tests
cd packages/undef-terminal-frontend && npx vitest run

# Coverage — must be 100%
uv run pytest packages/undef-terminal/tests/tunnel/test_intercept_gate.py tests/tunnel/test_inspect_intercept.py --cov=undef.terminal.cli.inspect --cov=undef.terminal.tunnel.http_proxy --cov-branch

# Full regression
uv run pytest packages/undef-terminal/tests/ -q --no-cov --ignore=packages/undef-terminal/tests/memray --ignore=packages/undef-terminal/tests/playwright

# Mutation testing
uv run mutmut run --paths-to-mutate src/undef/terminal/tunnel/http_proxy.py

# Manual verification with Playwright
# 1. Start: uv run python -c "from undef.terminal.cli.inspect import _cmd_inspect; ..."
# 2. Open browser to inspect view
# 3. Send requests, verify pause/forward/drop/modify
```
