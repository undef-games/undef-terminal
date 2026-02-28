# undef-terminal: Design & Implementation Plan

## Context

`undef-terminal` will be a reusable Python library that extracts terminal I/O infrastructure from `undef-warp` and makes it available to the broader undef-games ecosystem. Currently, `undef-warp` contains transport adapters, ANSI utilities, and an xterm.js frontend that are generic enough to live in a shared package. `undef-engine` could use the frontend assets and ANSI helpers, but its JSON WebSocket architecture is incompatible with the stream-based transport layer.

**This is a library, not a service.** No CLI entrypoints, no port binding, no uvicorn startup.

---

## What to Extract (from undef-warp)

| Source file in undef-warp | Target in undef-terminal | Notes |
|---|---|---|
| `runtime/api/ws_transport.py` | `transports/websocket.py` | Direct move |
| `runtime/terminal/transports/telnet.py` | `transports/telnet.py` | Refactor: callback-based instead of GameState |
| `runtime/terminal/ansi.py` | `ansi.py` | Direct move |
| `_consume_iac`/`_consume_escape` in `session.py` | `stream.py` | Extract as standalone async functions |
| `frontend/web/static/terminal.html` + `terminal.js` | `frontend/static/` | Make title/storageKey configurable |

## What Stays in undef-warp

- `session.py`, `game_loop.py`, `login.py` — game-specific session/state logic
- `input_utils.py` — game color tag helpers
- `ws_terminal.py` — becomes a thin wrapper calling library functions
- `app.py` — specific endpoint wiring; `mount_terminal_ui()` replaces manual StaticFiles mounting

## undef-engine Fit

undef-engine's WebSocket layer uses `{action, payload}` JSON — incompatible with stream-based transport. **undef-engine should NOT use the transport layer.** It can optionally use:
- `undef.terminal.fastapi.mount_terminal_ui()` — for a future admin terminal
- `undef.terminal.ansi` — for ANSI text rendering if needed

---

## Package Structure

```
src/undef/terminal/
├── __init__.py          # Public re-exports
├── defaults.py          # Port/host constants (TerminalDefaults class)
├── protocols.py         # TerminalReader, TerminalWriter Protocol types
├── ansi.py              # colorize(), strip_colors(), ANSI constants
├── stream.py            # consume_iac(), consume_escape() standalone async fns
├── transports/
│   ├── __init__.py
│   ├── websocket.py     # WebSocketStreamReader, WebSocketStreamWriter
│   ├── telnet.py        # start_telnet_server(handler, host, port), IAC constants
│   └── ssh.py           # start_ssh_server(), SSHStreamReader/Writer (asyncssh)
├── fastapi.py           # mount_terminal_ui(app), create_ws_terminal_router(handler)
└── frontend/
    ├── __init__.py      # get_static_dir() -> Path
    └── static/
        ├── terminal.html
        └── terminal.js
```

---

## Key Interface Definitions

**`protocols.py`** — common contract that all transports satisfy:
```python
class TerminalReader(Protocol):
    async def read(self, n: int) -> bytes: ...

class TerminalWriter(Protocol):
    def write(self, data: bytes) -> None: ...
    async def drain(self) -> None: ...
    def get_extra_info(self, key: str, default: object = None) -> object: ...
    def close(self) -> None: ...
    async def wait_closed(self) -> None: ...
```

**`transports/telnet.py`** — callback-based (not GameState-coupled):
```python
async def start_telnet_server(
    connection_handler: Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]],
    host: str = TerminalDefaults.TELNET_HOST,
    port: int = TerminalDefaults.TELNET_PORT,
) -> asyncio.Server: ...
```

**`fastapi.py`**:
```python
def mount_terminal_ui(app: FastAPI, *, path: str = "/terminal") -> None: ...
def create_ws_terminal_router(
    connection_handler: Callable[[WebSocket], Awaitable[None]],
    path: str = "/ws/terminal",
) -> APIRouter: ...
```

---

## pyproject.toml Changes

```toml
[project]
dependencies = ["fastapi>=0.110"]

[project.optional-dependencies]
ssh = ["asyncssh>=2.14"]

[tool.hatch.build.targets.wheel]
packages = ["src/undef"]
include = ["src/undef/terminal/frontend/static/**"]
```

Note: needs `hatchling` added as build backend (currently default uv setup).

---

## Frontend Changes Before Moving

`terminal.js` has hardcoded strings that must be made configurable:
- `"Warp Agent Runtime Platform"` — title text
- `'tw2002-terminal-settings'` — localStorage key

These should read from a `window.TERMINAL_CONFIG` object that the host page sets before loading the script, with sensible defaults.

---

## Migration Steps for undef-warp

1. Add `undef-terminal` to `pyproject.toml` deps
2. Replace `from uwarp.runtime.terminal.ansi import ...` → `from undef.terminal.ansi import ...`
3. Replace `from uwarp.runtime.api.ws_transport import ...` → `from undef.terminal.transports.websocket import ...`
4. Replace `Session._consume_iac`/`_consume_escape` with calls to `undef.terminal.stream` functions
5. Refactor uwarp's `start_telnet_server` to wrap library version with game-specific `_handle_connection` callback
6. Replace manual `StaticFiles` mount with `mount_terminal_ui(app, path="/ui")`
7. Delete the now-redundant source files from uwarp

---

## Verification

- `undef-warp` starts and serves terminal (telnet + WebSocket) after migration
- Browser terminal connects, renders ANSI colors, persists settings
- `from undef.terminal import ...` works in a fresh venv with only `undef-terminal` installed
- SSH transport: `asyncssh`-based server accepts connection with same game loop as telnet
- xterm.js frontend loads from package data (not from uwarp source tree)
- undef-engine can `from undef.terminal.ansi import colorize` without breaking anything

---

## Critical Source Files

- `/Users/tim/code/gh/undef-games/undef-warp/src/uwarp/runtime/api/ws_transport.py`
- `/Users/tim/code/gh/undef-games/undef-warp/src/uwarp/runtime/terminal/transports/telnet.py`
- `/Users/tim/code/gh/undef-games/undef-warp/src/uwarp/runtime/session/session.py` (IAC helpers)
- `/Users/tim/code/gh/undef-games/undef-warp/src/uwarp/runtime/terminal/ansi.py`
- `/Users/tim/code/gh/undef-games/undef-warp/src/uwarp/frontend/web/static/terminal.js`
- `/Users/tim/code/gh/undef-games/undef-terminal/pyproject.toml`
