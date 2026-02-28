# Architectural Analysis: Shared `undef-terminal` Package (Hybrid Frontend/Backend)

## Context

Three projects have terminal-type behavior: `uwarp` (BBS game server), `undef-engine` (thin client TUI), and `bbsbot` (BBS automation bot). The goal is a shared `undef-terminal` package covering:
1. **Transport infrastructure** (backend): WebSocket adapters, SSH, Telnet server
2. **Terminal emulation helpers** (backend): pyte wrapper, ANSI normalization, CP437 decode
3. **Hijack machinery** (backend): pause/resume/step for human takeover of automated sessions
4. **Terminal UI assets** (frontend): xterm.js display + hijack controls

`undef-terminal` already exists at `/Users/tim/code/gh/undef-games/undef-terminal/` (empty shell). Prior design plan at `quizzical-dreaming-hearth.md` covered transport/ANSI only — this supersedes it.

---

## Consumer Map (Revised)

| Module | uwarp consumes | bbsbot consumes | undef-engine consumes |
|---|---|---|---|
| `transports/websocket` | Yes (stream adapter) | No | No |
| `transports/ssh` | Yes | No | No |
| `transports/telnet` | Yes (server-mode) | No (client-mode stays in bbsbot) | No |
| `ansi.py` | Yes | No | Maybe |
| `stream.py` (IAC/escape consume) | Yes | No | No |
| `emulator.py` (pyte wrapper) | No | Yes | No |
| `screen.py` (ANSI normalize, CP437) | No | Yes | No |
| `hijack/` | Yes (gains capability) | Yes (migrates from games/tw2002) | No |
| `fastapi.py` | Yes | Yes | No |
| `frontend/static/` | Yes | Yes | No |

---

## Package Structure

```
src/undef/terminal/
├── __init__.py
├── defaults.py              # Port constants (TELNET=2102, SSH=2222), lease defaults
├── protocols.py             # TerminalReader, TerminalWriter Protocol types
│
├── # ── Server-side transport ──────────────────────────────────────
├── ansi.py                  # colorize(), strip_colors(), COLOR_MAP, CLEAR_SCREEN (TW2002 tags→ANSI)
├── stream.py                # consume_iac(), consume_escape() standalone async fns
├── transports/
│   ├── __init__.py
│   ├── websocket.py         # WebSocketStreamReader, WebSocketStreamWriter
│   ├── telnet.py            # start_telnet_server(handler, host, port), IAC constants
│   └── ssh.py               # SSHStreamReader/Writer, start_ssh_server() [optional: asyncssh]
│
├── # ── Client-side emulation ──────────────────────────────────────
├── emulator.py              # TerminalEmulator: pyte.Screen+Stream wrapper, snapshot(), hash [optional: pyte]
├── screen.py                # normalize_terminal_text(), strip_ansi(), decode_cp437(), encode_cp437()
│
├── # ── Hijack infrastructure ──────────────────────────────────────
├── hijack/
│   ├── __init__.py
│   ├── base.py              # HijackBase mixin: await_if_hijacked(), set_hijacked(), step tokens, watchdog
│   ├── hub.py               # TermHub: per-bot state, dual-mode hijack (WS + REST), lease management
│   ├── bridge.py            # TermBridge: worker-side WS client, recv control/input, forward to session
│   └── routes.py            # FastAPI WS + REST routes (/ws/worker/{id}/term, /bot/{id}/hijack/*)
│
├── # ── FastAPI integration ─────────────────────────────────────────
├── fastapi.py               # mount_terminal_ui(), create_ws_terminal_router()
│
└── # ── Frontend assets ─────────────────────────────────────────────
    frontend/
    ├── __init__.py           # get_static_dir() -> Path
    └── static/
        ├── terminal.html     # xterm.js UI shell (TERMINAL_CONFIG-parameterized)
        ├── terminal.js       # xterm.js + WebSocket I/O, theming (CRT/BBS/Glass), settings
        └── hijack.js         # Embeddable hijack controls widget (acquire/step/release/input)
```

---

## Key Interfaces

### `emulator.py` — pyte wrapper (extracted from bbsbot `terminal/emulator.py`)
```python
class TerminalEmulator:
    def __init__(self, cols: int = 80, rows: int = 25, term: str = "ANSI"): ...
    def process(self, data: bytes) -> None: ...          # CP437 decode → pyte feed
    def snapshot(self) -> ScreenSnapshot: ...            # screen text, hash, cursor, metadata
    @property
    def screen_changed(self) -> bool: ...                # dirty flag

@dataclass
class ScreenSnapshot:
    screen: str
    screen_hash: str
    cursor: dict[str, int]
    cols: int
    rows: int
    cursor_at_end: bool
    captured_at: float
```

### `screen.py` — normalization utilities (extracted from bbsbot `terminal/screen_utils.py`)
```python
def normalize_terminal_text(text: str) -> str: ...      # CRLF + strip ANSI + bare SGR cleanup
def strip_ansi(text: str) -> str: ...                   # remove escape sequences only
def decode_cp437(data: bytes, errors: str = "replace") -> str: ...
def encode_cp437(text: str, errors: str = "replace") -> bytes: ...
```

### `hijack/base.py` — worker-side mixin (extracted from bbsbot `games/tw2002/worker/hijack_manager.py`)
```python
class HijackBase:
    async def await_if_hijacked(self) -> None: ...       # checkpoint in game/bot loop
    async def set_hijacked(self, enabled: bool) -> None: ...
    async def request_step(self, checkpoints: int = 2) -> None: ...
    def start_watchdog(self, *, stuck_timeout_s: float = 120.0) -> None: ...
```

### `hijack/hub.py` — manager-side registry (extracted from bbsbot `api/term/hub.py`)
```python
class TermHub:
    async def register_worker(self, bot_id: str, ws: WebSocket) -> None: ...
    async def register_browser(self, bot_id: str, ws: WebSocket) -> None: ...
    async def acquire_hijack(self, bot_id: str, owner: str, lease_s: int) -> HijackSession: ...
    async def release_hijack(self, bot_id: str, hijack_id: str) -> None: ...
    async def send_input(self, bot_id: str, keys: str) -> None: ...
    async def get_snapshot(self, bot_id: str) -> dict: ...
```

### `transports/telnet.py` — callback-based server
```python
async def start_telnet_server(
    connection_handler: Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]],
    host: str = TerminalDefaults.TELNET_HOST,
    port: int = TerminalDefaults.TELNET_PORT,
) -> asyncio.Server: ...
```

### `frontend/static/terminal.js` — configurable via
```javascript
window.TERMINAL_CONFIG = {
    title: "My Terminal",
    storageKey: "my-terminal-settings",
    wsPath: "/ws",
};
```

---

## Optional Dependencies

```toml
[project]
dependencies = ["fastapi>=0.110"]

[project.optional-dependencies]
ssh = ["asyncssh>=2.14"]
emulator = ["pyte>=0.8"]
all = ["asyncssh>=2.14", "pyte>=0.8"]
```

`pyte` only needed if using `undef.terminal.emulator` (bbsbot use case). Transport layer and hijack work without it.

---

## What Stays Project-Specific

**uwarp**: Session lifecycle, player state, game loop, corp notifications. `ws_terminal.py` becomes thin wrapper. Telnet/SSH startup wraps library with game-specific callback.

**bbsbot**: Client-mode Telnet transport (inverted semantics from server-mode), `SessionManager`, `PromptWaiter`/`InputSender`, screen pattern detection, MCP tool definitions (wrap `undef.terminal.hijack` APIs).

**undef-engine**: `ANSIParser` (Rich markup output — different output target than `screen.py`), Textual widgets, template engine.

---

## Refactoring Required Before Extraction

1. **`telnet.py` in uwarp**: Replace `game: GameState` param with `connection_handler: Callable`
2. **`_consume_iac`/`_consume_escape` in uwarp `_session_io.py`**: Extract mixin methods to standalone async functions
3. **`terminal.js`**: Make title (`"Warp Agent Runtime Platform"`) and storageKey (`'tw2002-terminal-settings'`) configurable via `window.TERMINAL_CONFIG`
4. **`HijackBase` in bbsbot**: Move from `games/tw2002/worker/hijack_manager.py` to `undef.terminal.hijack.base` — remove any TW2002-specific logging domain references

---

## Critical Source Files

**From uwarp:**
- `packages/uwarp-server/src/uwarp/runtime/api/ws_transport.py` → `transports/websocket.py`
- `packages/uwarp-server/src/uwarp/runtime/terminal/transports/ssh.py` → `transports/ssh.py`
- `packages/uwarp-server/src/uwarp/runtime/terminal/transports/telnet.py` → `transports/telnet.py` (after refactor)
- `packages/uwarp-server/src/uwarp/runtime/session/_session_io.py` → `stream.py` (IAC/escape helpers)
- `packages/uwarp-server/src/uwarp/runtime/terminal/ansi.py` → `ansi.py`
- `packages/uwarp-server/src/uwarp/frontend/web/static/terminal.js` → `frontend/static/terminal.js`
- `packages/uwarp-server/src/uwarp/frontend/web/static/terminal.html` → `frontend/static/terminal.html`

**From bbsbot:**
- `src/bbsbot/terminal/emulator.py` → `emulator.py`
- `src/bbsbot/terminal/screen_utils.py` → `screen.py`
- `src/bbsbot/games/tw2002/worker/hijack_manager.py` → `hijack/base.py`
- `src/bbsbot/api/term/hub.py` → `hijack/hub.py`
- `src/bbsbot/swarm/term_bridge.py` → `hijack/bridge.py`
- `src/bbsbot/api/term/ws_routes.py` + `rest_routes.py` → `hijack/routes.py`
- `src/bbsbot/web/static/dashboard.js` (hijack sections) → `frontend/static/hijack.js`

**Package shell:** `/Users/tim/code/gh/undef-games/undef-terminal/pyproject.toml`

---

## Step 0: Workspace Setup (Do First)

Before any extraction, wire `undef-terminal` into uwarp-space for cross-repo development.

### 1. Create symlink
```bash
cd /Users/tim/code/gh/undef-games/uwarp-space/packages
ln -s ../../../undef-terminal undef-terminal
```

### 2. Add to workspace — root `pyproject.toml`

**File**: `/Users/tim/code/gh/undef-games/uwarp-space/pyproject.toml`

Add to `[tool.uv.workspace]` members:
```toml
"packages/undef-terminal",
```

Add to `[tool.uv.sources]`:
```toml
undef-terminal = { workspace = true }
```

### 3. Add as dependency in uwarp-server
**File**: `/Users/tim/code/gh/undef-games/uwarp-space/packages/uwarp-server/pyproject.toml`
```toml
"undef-terminal>=0.1.0",
```

### 4. Fix undef-terminal's pyproject.toml
**File**: `/Users/tim/code/gh/undef-games/undef-terminal/pyproject.toml`

Needs:
- Build backend: `[build-system]` with `hatchling`
- Source layout: `[tool.hatch.build.targets.wheel] packages = ["src/undef"]`
- Runtime deps: `fastapi>=0.110`
- Optional extras: `ssh = ["asyncssh>=2.14"]`, `emulator = ["pyte>=0.8"]`

### 5. Sync workspace
```bash
cd /Users/tim/code/gh/undef-games/uwarp-space
uv sync
```

Verify: `from undef.terminal import __version__` in uwarp-space's venv.

---

## Verification

- `from undef.terminal import WebSocketStreamReader, colorize` works in fresh venv (no optional deps)
- `from undef.terminal.emulator import TerminalEmulator` works with `undef-terminal[emulator]`
- uwarp migrates `ws_transport.py`, `ansi.py`, `telnet.py` imports → no behavioral change; telnet/SSH still accept connections
- bbsbot migrates `TerminalEmulator`, `normalize_terminal_text`, `HijackBase`, `TermHub`, `TermBridge` → hijack round-trip: acquire → bot pauses → human sends input → bot resumes
- Browser terminal loads from package data, renders ANSI colors, `window.TERMINAL_CONFIG` overrides work
- SSH server accepts connection with `[ssh]` extra installed
