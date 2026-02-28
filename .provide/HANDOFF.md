# undef-terminal: Hijack Infrastructure Handoff

## Request
Implement the complete `undef-terminal` package plan, including hijack infrastructure (HijackBase mixin, TermHub, TermBridge, REST+WS routes).

## Completed

### Package restructure
- `pyproject.toml`: `fastapi` moved to optional `websocket` extra; added `ssh`, `emulator`, `all` extras
- `transports/websocket.py`: guarded import with clear `ImportError` message
- `uwarp-server/pyproject.toml`: dep updated to `undef-terminal[websocket]>=0.1.0`
- `bbsbot/pyproject.toml`: dep updated to `undef-terminal[emulator]>=0.1.0`

### New modules
- `screen.py` — added `extract_action_tags`, `clean_screen_for_display`, `extract_menu_options`, `extract_numbered_list`, `extract_key_value_pairs`
- `emulator.py` — `TerminalEmulator` (pyte wrapper, guarded import)
- `io.py` — `Session` Protocol, `PromptWaiter`, `InputSender`
- `session_logger.py` — async JSONL `SessionLogger`
- `replay/raw.py`, `replay/viewer.py` — session replay utilities
- `transports/base.py` — `ConnectionTransport` ABC
- `transports/telnet.py` — extended with `TelnetTransport` (full RFC 854 client, IAC escaping, NAWS)
- `transports/ssh.py` — `SSHStreamReader/Writer`, `TerminalSSHServer`, `start_ssh_server()`
- `transports/chaos.py` — `ChaosTransport` fault-injection wrapper
- `frontend/terminal.html`, `frontend/terminal.js` — copied from uwarp-space

### Hijack infrastructure
- `hijack/base.py` — `HijackBase` mixin: `await_if_hijacked`, `set_hijacked`, `request_step` (step tokens, capped at 100), `note_progress`, `start_watchdog`/`stop_watchdog`, `cleanup_hijack`
- `hijack/models.py` — `HijackSession` (dataclass), `BotTermState` (dataclass), pydantic request models
- `hijack/hub.py` — `TermHub` with optional `on_hijack_changed` callback (replaces bbsbot `_manager` coupling)
- `hijack/routes.py` — `register_ws_routes` + `register_rest_routes` (7 REST endpoints + 2 WS endpoints)
- `hijack/bridge.py` — `TermBridge` with `WorkerBot`/`WorkerSession` Protocol (duck-typed, decoupled from `TradingBot`)

### Tests
128 passing, 2 skipped (pyte/asyncssh not in dev env). All test files in `tests/`.

## Remaining Work

### `fastapi.py` integration module
Convenience functions for mounting terminal UI into a FastAPI app:
```python
from undef.terminal.fastapi import mount_terminal_ui, create_ws_terminal_router
```
Source: adapt from `uwarp-server/src/uwarp/frontend/web/routes.py` and bbsbot dashboard registration.

### `frontend/hijack.js`
Embeddable hijack controls widget (pause/resume/step/input form).
Source: extract hijack sections from `bbsbot/src/bbsbot/dashboard/static/dashboard.js`.

### Import migration
Once downstream consumers are ready:
- `uwarp-server`: replace `uwarp.swarm.term_bridge.TermBridge` with `undef.terminal.hijack.bridge.TermBridge`
- `bbsbot`: replace `bbsbot.api.term.*` with `undef.terminal.hijack.*`
- `bbsbot`: replace `bbsbot.bots.base.HijackBase` with `undef.terminal.hijack.base.HijackBase`

## Key Architecture Decisions
- `HijackBase` has zero optional deps — works in any context (not just websocket extra)
- `HijackBase` watchdog uses `on_stuck` callback instead of calling game-specific `report_error`/`disconnect`
- `TermHub` uses `on_hijack_changed: Callable[[str, bool, str|None], Awaitable|None]` callback — async or sync both work
- `BotTermState` and `HijackSession` are Python dataclasses (not pydantic) — no serialization overhead
- Pydantic kept only for FastAPI request-body models
- `TermBridge` uses duck-typed `WorkerBot`/`WorkerSession` Protocol — no import of game classes
