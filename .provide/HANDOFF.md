# undef-terminal: Handoff

## Current State
536 tests passing. Package fully implemented and documented.

---

## Completed This Session — Post-sshwifty Cleanup (07ccc97, 6656310)

### JSDoc additions
- `frontend/terminal.js`: added `@param {number} [config.heartbeatMs=25000]` to constructor docs
- `frontend/hijack.js`: added `@param {boolean} [config.mobileKeys=true]` to constructor docs

### New test: ping guard (`tests/test_hijack_ws.py`)
- `test_ping_is_silently_ignored`: sends `{"type": "ping"}` then `snapshot_req`, asserts only the `snapshot_req` response arrives — proves the ping produces no reply

### Playwright smoke tests (`tests/test_playwright_hijack.py`)
- `test_mobile_keys_toolbar_button_present`: asserts `⌨` button is in the hijack toolbar
- `test_mobile_keys_row_hidden_before_hijack`: clicks `⌨`, asserts `.mobile-keys` row stays hidden until hijack acquired
- `pytest-playwright` added to dev dependencies; chromium installed

### README.md
- Written from scratch: install + extras table, quick-start (proxy/in-process/mount), hijack widget (backend TermHub + frontend UndefHijack/UndefTerminal), CLI (`proxy`/`listen`)

---

## Previously Completed

### Package restructure
- `pyproject.toml`: `fastapi` moved to optional `websocket` extra; added `ssh`, `emulator`, `cli`, `all` extras

### Core modules
- `screen.py`, `emulator.py`, `io.py`, `session_logger.py`
- `replay/raw.py`, `replay/viewer.py`
- `transports/base.py`, `telnet.py`, `ssh.py`, `chaos.py`
- `fastapi.py` — `mount_terminal_ui`, `WsTerminalProxy`, `TelnetWsGateway`, `create_ws_terminal_router`
- `cli.py` — `undefterm proxy` and `undefterm listen`

### Hijack infrastructure
- `hijack/base.py` — `HijackBase` mixin
- `hijack/models.py` — `HijackSession`, `BotTermState`, pydantic request models
- `hijack/hub.py` — `TermHub` with `on_hijack_changed` callback
- `hijack/routes_ws.py`, `hijack/routes_rest.py`
- `hijack/bridge.py` — `TermBridge` with duck-typed `WorkerBot`/`WorkerSession` Protocol

### Frontend
- `frontend/terminal.html`, `terminal.js`, `terminal.css`
- `frontend/hijack.html`, `hijack.js`, `hijack.css`
- Heartbeat (`heartbeatMs`), backoff reconnect, mobile key toolbar (`mobileKeys`), stale guards (db6a89e)

---

## Remaining Work
- Import migration in downstream consumers (explicitly deferred by user — do not suggest)

## Key Architecture Decisions
- `HijackBase` has zero optional deps
- `TermHub` `on_hijack_changed` callback accepts sync or async
- `BotTermState`/`HijackSession` are dataclasses; only FastAPI request bodies use pydantic
- `TermBridge` duck-typed — no import of game classes
