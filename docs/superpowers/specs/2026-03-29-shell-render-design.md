# Shell `render` Command — URL/File to ANSI Art

## Goal

Add a `render` command to `undef.terminal.shell` that fetches an image from a URL or local file and displays it as ANSI art in the terminal. Supports all Pillow image formats, animated playback (GIF, APNG, WebP), three color modes (truecolor, 256, 16), and configurable output dimensions.

## Scope

- **Images only** — no HTML/web page rendering
- **CLI and FastAPI** — not available in Pyodide/CF Workers (Pillow unavailable)
- **Optional extra** — `undef-terminal-shell[images]` installs Pillow

## Command Interface

```
render [--mode truecolor|256|16] [--cols N] [--rows N] [--fps N] [--loop] <url>
```

**Arguments:**

| Flag | Default | Description |
|------|---------|-------------|
| `--mode` | `truecolor` | Color quantization: `truecolor` (24-bit), `256` (xterm), `16` (classic ANSI) |
| `--cols` | `80` | Output width in terminal columns |
| `--rows` | `24` | Output height in terminal rows (each row = 2 pixel rows via half-blocks) |
| `--fps` | from source | Override animation frame rate |
| `--loop` | off | Loop animated images until Ctrl+C |
| `<url>` | required | `http://`, `https://`, or `file://` source |

**Behavior:**

- **Static images** (JPEG, PNG, BMP, TIFF, etc.) — render once, return single frame + PROMPT
- **Animated images** (GIF, APNG, animated WebP) — stream frames at source FPS (overridable), play once by default, `--loop` repeats until interrupted
- **Missing Pillow** — returns error: `"error: missing dependency — Pillow\ninstall the images extra: pip install 'undef-terminal-shell[images]'"`

## Architecture

```
_commands.py  — _cmd_render(): parse flags, fetch bytes, call converter, return result
_render.py    — image_to_ansi_frames(): bytes → list[str] frames + fps
_output.py    — existing ANSI formatting helpers (unchanged)
```

### `_render.py` — Image Converter

Single public function:

```python
def image_to_ansi_frames(
    data: bytes,
    cols: int = 80,
    rows: int = 24,
    mode: Literal["truecolor", "256", "16"] = "truecolor",
) -> tuple[list[str], float]:
```

- **Input:** raw image bytes (caller handles fetching)
- **Output:** `(frames, fps)` — list of ANSI strings and source FPS (0.0 for static images)
- **Rendering:** half-block character (`▄`) with fg=bottom pixel, bg=top pixel, giving 2 vertical pixels per terminal row
- **Resize:** Pillow `Image.LANCZOS` always (best quality for downscaling, which is the common case — source images are typically larger than 80x48 pixels)
- **Alpha:** blend against black background (alpha < 128 → black)
- **Optimization:** only emit SGR escape when color changes from previous cell

Internal helpers:

- `_nearest_16(r, g, b) -> (fg_code, bg_code)` — nearest 16-color match by Euclidean RGB distance
- `_nearest_256(r, g, b) -> int` — nearest xterm 256-color palette index
- `_sgr_truecolor(fg, bg) -> str` — `ESC[38;2;R;G;B;48;2;R;G;Bm`
- `_sgr_256(fg, bg) -> str` — `ESC[38;5;N;48;5;Nm`
- `_sgr_16(fg, bg) -> str` — `ESC[FG;BGm`
- `_render_frame(pixels, px_w, px_h, sgr_fn) -> str` — single frame with cursor-home prefix
- xterm 256-color palette table (16 standard + 216 cube + 24 grayscale)
- ANSI 16-color palette table with approximate RGB values

### `_commands.py` — Command Handler

```python
async def _cmd_render(self, arg: str) -> list[str] | AnimatedResult:
```

1. Parse flags (`--mode`, `--cols`, `--rows`, `--fps`, `--loop`) and URL from `arg`
2. Validate URL scheme (`http://`, `https://`, `file://`)
3. Fetch bytes: `urllib.request.urlopen` for http(s), `Path.read_bytes()` for file
4. Call `image_to_ansi_frames(data, cols, rows, mode)`
5. Static (fps == 0): return `[frame + PROMPT]`
6. Animated: return `AnimatedResult(frames, fps, loop)`

### `AnimatedResult` — Streaming Protocol

```python
@dataclass
class AnimatedResult:
    frames: list[str]
    fps: float
    loop: bool
```

The dispatcher checks `isinstance(result, AnimatedResult)`. If true, it streams frames with `asyncio.sleep(1/fps)` between them. If `loop` is true, it repeats until the dispatcher is interrupted. The final frame gets PROMPT appended.

This is the only change to the dispatcher's return handling. All existing commands continue returning `list[str]` unchanged.

### Dispatcher Changes

In `CommandDispatcher.dispatch()`:

```python
result = await self._cmd_render(arg)
if isinstance(result, AnimatedResult):
    return result  # caller handles streaming
return result  # list[str] as usual
```

The caller (CLI `__main__.py` or `UshellConnector`) is responsible for the timing loop. This keeps the dispatcher simple.

### `__main__.py` CLI Changes

The CLI loop checks for `AnimatedResult`:

```python
result = await dispatcher.dispatch(line)
if isinstance(result, AnimatedResult):
    await _play_animation(result, sys.stdout)
else:
    for frame in result:
        sys.stdout.write(frame.replace("\r\n", "\n"))
```

### `UshellConnector` Changes

Same pattern — `handle_input` checks for `AnimatedResult` and schedules frame streaming via the terminal frame protocol.

## Dependencies

**pyproject.toml:**

```toml
[project.optional-dependencies]
images = ["Pillow>=10.0"]
```

**Runtime check in `_render.py`:**

```python
try:
    from PIL import Image
except ImportError as exc:
    raise ImportError(
        "missing dependency — Pillow\n"
        "install the images extra: pip install 'undef-terminal-shell[images]'"
    ) from exc
```

The `_cmd_render` handler catches this ImportError and returns a user-friendly error message.

## Error Handling

| Condition | Response |
|-----------|----------|
| No URL provided | `error: usage: render [flags] <url>` |
| Pillow not installed | `error: missing dependency — Pillow ...` |
| Invalid URL scheme | `error: unsupported URL scheme (use http://, https://, or file://)` |
| Network error | `error: cannot fetch <url>: <reason>` |
| File not found | `error: file not found: <path>` |
| Invalid/corrupt image | `error: cannot decode image: <reason>` |
| Invalid --mode value | `error: unknown mode '<val>' (use truecolor, 256, or 16)` |

## Testing

### Unit Tests (`test_shell_render.py`)

- Static PNG → 1 frame, fps=0
- Animated GIF → N frames, fps from metadata
- Animated APNG → N frames
- Animated WebP → N frames
- All 3 color modes produce valid SGR sequences
- `--cols`/`--rows` resize works
- Alpha transparency blends to black
- Invalid bytes raises error
- Missing Pillow import raises ImportError with message

### Command Tests (`test_shell_commands_render.py`)

- `render` with no args → usage error
- `render <url>` with mocked urllib → static image renders
- `render --mode 256 <url>` → 256-color output
- `render --fps 5 <url>` → AnimatedResult with fps=5
- `render --loop <url>` → AnimatedResult with loop=True
- `render file:///path/to/image.png` → reads from disk
- `render <bad-url>` → network error message
- `render <url>` without Pillow → install suggestion
- Flag parsing edge cases (flags after URL rejected, unknown flags)

### E2E (already exists)

The existing Playwright tests in `test_color_palette.py` prove the full ANSI rendering pipeline works through TermHub/telnet → xterm.js for all three color modes, including animated GIF playback. No new E2E tests needed — the `_render.py` converter is a direct port of the proven `_gif_to_ansi.py` test helper.

## Files Changed

| File | Action |
|------|--------|
| `packages/undef-terminal-shell/src/undef/shell/_render.py` | **Create** — image converter |
| `packages/undef-terminal-shell/src/undef/shell/_commands.py` | **Modify** — add `_cmd_render`, AnimatedResult, routing |
| `packages/undef-terminal-shell/src/undef/shell/__main__.py` | **Modify** — handle AnimatedResult in CLI loop |
| `packages/undef-terminal-shell/src/undef/shell/terminal/_connector.py` | **Modify** — handle AnimatedResult in UshellConnector |
| `packages/undef-terminal-shell/pyproject.toml` | **Modify** — add `[images]` optional extra |
| `packages/undef-terminal-shell/tests/shell/test_shell_render.py` | **Create** — converter unit tests |
| `packages/undef-terminal-shell/tests/shell/test_shell_commands_render.py` | **Create** — command integration tests |
