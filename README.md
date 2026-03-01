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

The hijack system lets a human operator observe and take over a bot's terminal
session in real time.

### Backend — TermHub

```python
from undef.terminal.hijack.hub import TermHub

hub = TermHub(on_hijack_changed=lambda bot_id, enabled, owner: print(bot_id, enabled))
app.include_router(hub.create_router())
```

This adds:
- `GET  /ws/bot/{bot_id}/term` — browser observer/hijack WebSocket
- `GET  /ws/worker/{bot_id}/term` — bot worker WebSocket
- REST endpoints for session management

### Frontend — UndefHijack

Embed the hijack control widget in any HTML page:

```html
<div id="hijack-container"></div>
<script src="/static/hijack.js"></script>
<script>
  new UndefHijack(document.getElementById('hijack-container'), {
    botId: 'mybot',           // connects to /ws/bot/mybot/term
    mobileKeys: true,         // show collapsible special-key toolbar when hijacked
    heartbeatInterval: 5000,  // ms between heartbeats while owner
  });
</script>
```

Mount the bundled frontend files via FastAPI's `StaticFiles` or use
`mount_terminal_ui()` which includes `hijack.html`, `hijack.js`, and `hijack.css`.

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
