# undef-terminal

Shared terminal I/O primitives and WebSocket proxy infrastructure for the undef ecosystem.

## Installation

```bash
pip install undef-terminal
```

### Extras

| Extra | Installs | Required for |
|---|---|---|
| `[websocket]` | `fastapi` | `WsTerminalProxy`, `create_ws_terminal_router`, hijack hub |
| `[emulator]` | `pyte` | `TerminalEmulator` (screen state tracking) |
| `[ssh]` | `asyncssh` | SSH transport, `undefterm proxy --transport ssh` |
| `[cli]` | `fastapi`, `uvicorn`, `websockets` | `undefterm` command-line tool |
| `[all]` | everything above | Full feature set |

```bash
pip install 'undef-terminal[all]'
```

---

## Quick Start

### Serve the built-in terminal UI

Mount the bundled `terminal.html` + `terminal.js` frontend into any FastAPI app:

```python
from fastapi import FastAPI
from undef.terminal.fastapi import mount_terminal_ui

app = FastAPI()
mount_terminal_ui(app)           # serves UndefTerminal at /terminal
mount_terminal_ui(app, path="/t")  # custom path
```

### Browser WebSocket → remote telnet proxy

Accept browser WebSocket connections and proxy them to a remote BBS:

```python
from undef.terminal.fastapi import WsTerminalProxy

proxy = WsTerminalProxy("bbs.example.com", 23)
app.include_router(proxy.create_router("/ws/terminal"))
```

The browser connects to `ws://yourhost/ws/terminal`; the proxy opens a raw TCP
connection to the BBS for each session.

### In-process session handler

Handle terminal sessions in your own async code:

```python
from undef.terminal.fastapi import create_ws_terminal_router

async def my_handler(reader, writer, ws):
    writer.write(b"Welcome!\r\n")
    await writer.drain()
    async for line in reader:
        writer.write(line)
        await writer.drain()

app.include_router(create_ws_terminal_router(my_handler))
```

---

## Hijack Widget

The hijack system lets a human operator observe and take over a worker's terminal
session in real time.

### Backend — TermHub

```python
from undef.terminal.hijack.hub import TermHub

def resolve_browser_role(ws, worker_id):
    user = getattr(ws.state, "user", None)
    if getattr(user, "is_admin", False):
        return "admin"
    if getattr(user, "can_operate_terminals", False):
        return "operator"
    return "viewer"

hub = TermHub(
    on_hijack_changed=lambda worker_id, enabled, owner: print(worker_id, enabled),
    resolve_browser_role=resolve_browser_role,
)
app.include_router(hub.create_router())
```

This adds:
- `GET  /ws/browser/{worker_id}/term` — browser observer/hijack WebSocket
- `GET  /ws/worker/{worker_id}/term` — worker WebSocket
- REST endpoints for session management

Browser roles are resolved on the server. The browser WebSocket does not accept
a client-selected role parameter; without a resolver, browser sessions default
to read-only (`viewer`).

If `resolve_browser_role` raises an exception, the browser WebSocket is rejected
and closed. Resolver failures do not fall back to `viewer`.

### Frontend — UndefHijack

Embed the hijack control widget in any HTML page:

```html
<div id="hijack-container"></div>
<script src="/static/hijack.js"></script>
<script>
  new UndefHijack(document.getElementById('hijack-container'), {
    workerId: 'myworker',     // connects to /ws/browser/myworker/term
    mobileKeys: true,         // show collapsible special-key toolbar when hijacked
    heartbeatInterval: 5000,  // ms between heartbeats while owner
  });
</script>
```

Mount the bundled frontend files via FastAPI's `StaticFiles` or use
`mount_terminal_ui()` which includes `hijack.html`, `hijack.js`, and `hijack.css`.

### Interactive Demo Server

The repo also includes an interactive demo server for manual testing:

```bash
uv run python scripts/demo_server.py
```

Then open:

- `http://127.0.0.1:8742/hijack/hijack.html?worker=demo-session`

The built-in demo session is a general-purpose interactive worker rather than a
static screen. It supports:

- exclusive hijack mode (one browser owns input)
- shared input mode (multiple browsers can type)
- free-form text that appends to a live transcript
- built-in commands: `/help`, `/mode open`, `/mode hijack`, `/clear`, `/status`, `/nick <name>`, `/say <text>`, `/demo`, `/reset`

The demo page includes mode and reset controls backed by example-only HTTP
endpoints:

- `GET /demo/session/{worker_id}`
- `POST /demo/session/{worker_id}/mode`
- `POST /demo/session/{worker_id}/reset`

These demo endpoints exist only for the example server and are not part of the
library's public API.

### Reference Server

The repo now also includes a standalone reference server application:

```bash
undefterm-server --config scripts/undefterm-server.example.toml
```

This is the canonical hosted-app example for the library. It demonstrates:

- named sessions above `TermHub`
- browser session pages and operator pages
- server-side role resolution and policy
- hosted connectors (`demo`, `telnet`, `ssh`)
- session APIs, mode switching, and optional file-backed recording

Key endpoints:

- `GET /api/health`
- `GET /api/sessions`
- `GET /app/` (operator dashboard)
- `GET /app/session/{session_id}` (end-user page)
- `GET /app/operator/{session_id}` (operator console)

The example TOML config in [scripts/undefterm-server.example.toml](/Users/tim/code/gh/undef-games/undef-terminal/scripts/undefterm-server.example.toml)
shows the intended reference-implementation structure for server config.

For `connector_type = "ssh"`, the session entry can use these auth fields:

- `password` for password authentication
- `client_key_path` for a private key file path
- `client_key_data` for inline PEM private key text
- `client_key` for a single AsyncSSH-compatible key value
- `client_keys` for multiple keys
- `known_hosts` to override host-key verification behavior (`null` disables checks for local/dev use)

The SSH connector intentionally skips user SSH config discovery so startup stays
predictable and fast in the hosted server. If you need key-based auth in config
without a file path, prefer `client_key_data`.

### Frontend — UndefTerminal

Standalone terminal widget (no hijack controls):

```html
<div id="term"></div>
<script src="/static/terminal.js"></script>
<script>
  new UndefTerminal(document.getElementById('term'), {
    wsUrl: '/ws/terminal',
    theme: 'crt',             // 'crt' | 'bbs' | 'glass'
    heartbeatMs: 25000,       // keepalive ping interval (ms). 0 disables.
  });
</script>
```

---

## CLI

Install the `[cli]` extra, then:

### `undefterm proxy` — browser WS → telnet/SSH

Accepts browser WebSocket connections and proxies to a remote BBS.

```bash
# Basic telnet proxy
undefterm proxy bbs.example.com 23

# Custom port and WS path
undefterm proxy bbs.example.com 23 --port 9000 --path /ws/term

# SSH proxy (requires [ssh] extra)
undefterm proxy bbs.example.com 22 --transport ssh
```

### `undefterm listen` — telnet/SSH client → WebSocket server

Accepts traditional telnet and/or SSH clients and proxies to a remote WebSocket
terminal endpoint.

```bash
# Telnet listener
undefterm listen wss://warp.undef.games/ws/terminal

# With custom ports
undefterm listen wss://warp.undef.games/ws/terminal --port 2112 --ssh-port 2222

# With host key (SSH)
undefterm listen wss://warp.undef.games/ws/terminal --server-key /etc/host_key
```

---

## License

AGPL-3.0-or-later. Copyright (c) 2025-2026 MindTenet LLC.
