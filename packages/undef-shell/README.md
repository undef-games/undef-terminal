# undef-shell

Standalone Python REPL shell — usable independently of `undef-terminal`.

## Installation

```bash
pip install undef-shell
```

## CLI

```bash
python -m undef.shell
```

Starts an interactive terminal REPL. Type `help` to see available commands.

## Commands

| Command | Description |
|---------|-------------|
| `help [cmd]` | List commands, or show detail for a specific command |
| `clear` | Clear the terminal screen |
| `py <expr>` | Evaluate a Python expression (namespace persists across calls) |
| `sessions [kill <id>]` | List active sessions, or force-terminate one |
| `kv list` | List session registry KV entries |
| `kv get <key>` | Read a KV value |
| `kv set <key> <value>` | Write a KV value |
| `kv delete <key>` | Delete a KV entry |
| `storage list` | List Durable Object storage keys |
| `storage get <key>` | Read a Durable Object storage value |
| `fetch [-X METHOD] <url> [body]` | Make an HTTP request |
| `render [flags] <url>` | Render image as ANSI art (requires `images` extra) |
| `env` | Show available context bindings |
| `exit` / `quit` | Close the shell |

The `py` sandbox pre-imports `json`, `datetime`, `re`, `hashlib`, and `base64`.

### Image rendering

The `render` command converts images (PNG, JPEG, GIF, APNG, WebP, BMP, TIFF) to
ANSI terminal art using half-block characters. Animated images stream as video.

```bash
pip install 'undef-shell[images]'   # installs Pillow
```

```
render https://example.com/photo.png
render --mode 256 --cols 60 --rows 20 file:///path/to/image.png
render --loop --fps 15 https://example.com/animation.gif
```

| Flag | Default | Description |
|------|---------|-------------|
| `--mode` | `truecolor` | Color mode: `truecolor`, `256`, or `16` |
| `--cols` | `80` | Output width in columns |
| `--rows` | `24` | Output height in rows |
| `--fps` | from source | Override animation frame rate |
| `--loop` | off | Loop animated images until Ctrl+C |

## Use with undef-terminal

`undef-shell` is the engine behind the `ushell` connector type in
[`undef-terminal`](../../README.md). When a session is created with
`connector_type="ushell"`, the server wires up an `UshellConnector` — no external
process or network connection required.

```python
# Via undef-terminal hosted server config
{"session_id": "repl", "connector_type": "ushell", "display_name": "Python REPL"}

# Or via the quick-connect API
POST /api/connect  {"connector_type": "ushell"}
```

On Cloudflare Workers, `undef-terminal-cloudflare` vendors `undef-shell` into the
Pyodide runtime and injects CF bindings (`env`, `list_kv_sessions`, `storage`) into
the sandbox context automatically.

## Version

0.1.0 — AGPL-3.0-or-later · [undef-games/undef-terminal](https://github.com/undef-games/undef-terminal)
