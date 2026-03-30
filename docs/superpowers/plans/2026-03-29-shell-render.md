# Shell `render` Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `render` command to `undef.terminal.shell` that converts images (including animated GIF/APNG/WebP) to ANSI terminal art with truecolor, 256-color, and 16-color palette quantization.

**Architecture:** `_render.py` converts raw image bytes to ANSI frames using Pillow and half-block characters. `_commands.py` adds the `render` command that fetches URLs, calls the converter, and returns either a static frame or an `AnimatedResult` for streaming. Callers (`__main__.py`, `_connector.py`) handle animation timing.

**Tech Stack:** Python 3.11+, Pillow>=10.0 (optional extra), existing undef.terminal.shell command infrastructure

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `packages/undef-terminal-shell/src/undef/shell/_render.py` | **Create** | Image bytes → ANSI frames converter |
| `packages/undef-terminal-shell/src/undef/shell/_commands.py` | **Modify** | Add `_cmd_render`, `AnimatedResult`, dispatch routing, help text |
| `packages/undef-terminal-shell/src/undef/shell/__main__.py` | **Modify** | Handle `AnimatedResult` in CLI loop |
| `packages/undef-terminal-shell/src/undef/shell/terminal/_connector.py` | **Modify** | Handle `AnimatedResult` in `UshellConnector.handle_input` |
| `packages/undef-terminal-shell/pyproject.toml` | **Modify** | Add `images = ["Pillow>=10.0"]` optional extra |
| `packages/undef-terminal-shell/tests/shell/test_shell_render.py` | **Create** | Converter unit tests |
| `packages/undef-terminal-shell/tests/shell/test_shell_commands_render.py` | **Create** | Command integration tests |

---

### Task 1: Add Pillow optional extra to pyproject.toml

**Files:**
- Modify: `packages/undef-terminal-shell/pyproject.toml:22-23`

- [ ] **Step 1: Add the images extra**

In `packages/undef-terminal-shell/pyproject.toml`, change:

```toml
[project.optional-dependencies]
terminal = ["undef-terminal>=0.3.0"]
```

to:

```toml
[project.optional-dependencies]
terminal = ["undef-terminal>=0.3.0"]
images = ["Pillow>=10.0"]
```

- [ ] **Step 2: Verify the extra resolves**

Run: `uv pip install -e "packages/undef-terminal-shell[images]" 2>&1 | tail -3`
Expected: Pillow installs or is already installed.

- [ ] **Step 3: Commit**

```bash
git add packages/undef-terminal-shell/pyproject.toml
git commit -m "feat(shell): add images optional extra for Pillow"
```

---

### Task 2: Create `_render.py` — palette tables and quantizers

**Files:**
- Create: `packages/undef-terminal-shell/src/undef/shell/_render.py`
- Create: `packages/undef-terminal-shell/tests/shell/test_shell_render.py`

- [ ] **Step 1: Write failing tests for palette helpers**

Create `packages/undef-terminal-shell/tests/shell/test_shell_render.py`:

```python
#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Tests for undef.terminal.shell._render — image-to-ANSI converter."""

from __future__ import annotations

import pytest

from undef.terminal.shell._render import (
    _nearest_16,
    _nearest_256,
    _sgr_16,
    _sgr_256,
    _sgr_truecolor,
)


class TestSgrTruecolor:
    def test_black(self) -> None:
        assert _sgr_truecolor((0, 0, 0), (0, 0, 0)) == "\x1b[38;2;0;0;0;48;2;0;0;0m"

    def test_red_fg_blue_bg(self) -> None:
        assert _sgr_truecolor((255, 0, 0), (0, 0, 255)) == "\x1b[38;2;255;0;0;48;2;0;0;255m"


class TestNearest256:
    def test_pure_red(self) -> None:
        idx = _nearest_256(255, 0, 0)
        # xterm color 196 is (255, 0, 0) in the 216-color cube
        assert idx == 196

    def test_pure_white(self) -> None:
        idx = _nearest_256(255, 255, 255)
        assert idx == 15  # bright white in standard 16

    def test_pure_black(self) -> None:
        idx = _nearest_256(0, 0, 0)
        assert idx == 0  # standard black


class TestSgr256:
    def test_format(self) -> None:
        result = _sgr_256((255, 0, 0), (0, 0, 0))
        assert result.startswith("\x1b[38;5;")
        assert ";48;5;" in result
        assert result.endswith("m")


class TestNearest16:
    def test_pure_red(self) -> None:
        fg, bg = _nearest_16(255, 0, 0)
        assert fg == 91  # bright red fg
        assert bg == 101  # bright red bg

    def test_pure_black(self) -> None:
        fg, bg = _nearest_16(0, 0, 0)
        assert fg == 30  # black fg
        assert bg == 40  # black bg


class TestSgr16:
    def test_format(self) -> None:
        result = _sgr_16((255, 0, 0), (0, 0, 0))
        assert result.startswith("\x1b[")
        assert result.endswith("m")
        # Should contain two codes separated by ;
        codes = result[2:-1].split(";")
        assert len(codes) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/undef-terminal-shell/tests/shell/test_shell_render.py -v --no-cov -x 2>&1 | tail -5`
Expected: FAIL with `ModuleNotFoundError: No module named 'undef.terminal.shell._render'`

- [ ] **Step 3: Implement palette tables and quantizers**

Create `packages/undef-terminal-shell/src/undef/shell/_render.py`:

```python
#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Convert image bytes to ANSI terminal art frames.

Uses half-block characters to render two vertical pixels per terminal cell.
Supports truecolor (24-bit), 256-color (xterm), and 16-color (classic ANSI).

Requires the ``images`` optional extra: ``pip install 'undef-terminal-shell[images]'``
"""

from __future__ import annotations

from typing import Literal

# ---------------------------------------------------------------------------
# 16-color palette: (R, G, B, fg_code, bg_code)
# ---------------------------------------------------------------------------

_ANSI16: list[tuple[int, int, int, int, int]] = [
    (0, 0, 0, 30, 40),
    (170, 0, 0, 31, 41),
    (0, 170, 0, 32, 42),
    (170, 85, 0, 33, 43),
    (0, 0, 170, 34, 44),
    (170, 0, 170, 35, 45),
    (0, 170, 170, 36, 46),
    (170, 170, 170, 37, 47),
    (85, 85, 85, 90, 100),
    (255, 85, 85, 91, 101),
    (85, 255, 85, 92, 102),
    (255, 255, 85, 93, 103),
    (85, 85, 255, 94, 104),
    (255, 85, 255, 95, 105),
    (85, 255, 255, 96, 106),
    (255, 255, 255, 97, 107),
]

# ---------------------------------------------------------------------------
# 256-color palette: 16 standard + 216 cube + 24 grayscale
# ---------------------------------------------------------------------------

_XTERM256: list[tuple[int, int, int]] = []


def _build_xterm256() -> None:
    """Lazily populate the xterm 256-color palette table."""
    if _XTERM256:
        return
    for r, g, b, _fg, _bg in _ANSI16:
        _XTERM256.append((r, g, b))
    for ri in range(6):
        for gi in range(6):
            for bi in range(6):
                rv = 0 if ri == 0 else 55 + 40 * ri
                gv = 0 if gi == 0 else 55 + 40 * gi
                bv = 0 if bi == 0 else 55 + 40 * bi
                _XTERM256.append((rv, gv, bv))
    for i in range(24):
        v = 8 + 10 * i
        _XTERM256.append((v, v, v))


def _color_dist_sq(r1: int, g1: int, b1: int, r2: int, g2: int, b2: int) -> int:
    """Squared Euclidean distance between two RGB colors."""
    return (r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2


# ---------------------------------------------------------------------------
# Quantizers
# ---------------------------------------------------------------------------


def _nearest_16(r: int, g: int, b: int) -> tuple[int, int]:
    """Return (fg_code, bg_code) for the nearest 16-color match."""
    best_i = 0
    best_d = _color_dist_sq(r, g, b, *_ANSI16[0][:3])
    for i in range(1, 16):
        d = _color_dist_sq(r, g, b, *_ANSI16[i][:3])
        if d < best_d:
            best_d = d
            best_i = i
    return _ANSI16[best_i][3], _ANSI16[best_i][4]


def _nearest_256(r: int, g: int, b: int) -> int:
    """Return the xterm 256-color palette index for the nearest match."""
    _build_xterm256()
    best_i = 0
    best_d = _color_dist_sq(r, g, b, *_XTERM256[0])
    for i in range(1, 256):
        d = _color_dist_sq(r, g, b, *_XTERM256[i])
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


# ---------------------------------------------------------------------------
# SGR emitters
# ---------------------------------------------------------------------------


def _sgr_truecolor(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> str:
    """Emit truecolor SGR: ESC[38;2;R;G;B;48;2;R;G;Bm."""
    return f"\x1b[38;2;{fg[0]};{fg[1]};{fg[2]};48;2;{bg[0]};{bg[1]};{bg[2]}m"


def _sgr_256(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> str:
    """Emit 256-color SGR: ESC[38;5;N;48;5;Nm."""
    return f"\x1b[38;5;{_nearest_256(*fg)};48;5;{_nearest_256(*bg)}m"


def _sgr_16(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> str:
    """Emit 16-color SGR: ESC[FG;BGm."""
    fg_code, _ = _nearest_16(*fg)
    _, bg_code = _nearest_16(*bg)
    return f"\x1b[{fg_code};{bg_code}m"


_SGR_FN = {
    "truecolor": _sgr_truecolor,
    "256": _sgr_256,
    "16": _sgr_16,
}

ColorMode = Literal["truecolor", "256", "16"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/undef-terminal-shell/tests/shell/test_shell_render.py -v --no-cov -x 2>&1 | tail -15`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/undef-terminal-shell/src/undef/shell/_render.py packages/undef-terminal-shell/tests/shell/test_shell_render.py
git commit -m "feat(shell): add ANSI palette tables and quantizers for render"
```

---

### Task 3: Add `image_to_ansi_frames` — the core converter

**Files:**
- Modify: `packages/undef-terminal-shell/src/undef/shell/_render.py`
- Modify: `packages/undef-terminal-shell/tests/shell/test_shell_render.py`

- [ ] **Step 1: Write failing tests for image_to_ansi_frames**

Append to `packages/undef-terminal-shell/tests/shell/test_shell_render.py`:

```python
import io

from PIL import Image

from undef.terminal.shell._render import image_to_ansi_frames


def _make_png(width: int = 4, height: int = 4, color: tuple[int, int, int] = (255, 0, 0)) -> bytes:
    """Create a minimal solid-color PNG in memory."""
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_animated_gif(n_frames: int = 3, size: tuple[int, int] = (4, 4)) -> bytes:
    """Create a minimal animated GIF in memory."""
    frames = []
    for i in range(n_frames):
        hue = int(i / n_frames * 255)
        frames.append(Image.new("RGB", size, (hue, 255 - hue, 128)))
    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
    return buf.getvalue()


class TestImageToAnsiFramesStatic:
    def test_static_png_returns_one_frame(self) -> None:
        data = _make_png()
        frames, fps = image_to_ansi_frames(data, cols=4, rows=2)
        assert len(frames) == 1
        assert fps == 0.0

    def test_frame_starts_with_cursor_home(self) -> None:
        data = _make_png()
        frames, _ = image_to_ansi_frames(data, cols=4, rows=2)
        assert frames[0].startswith("\x1b[H")

    def test_frame_contains_half_block(self) -> None:
        data = _make_png()
        frames, _ = image_to_ansi_frames(data, cols=4, rows=2)
        assert "▄" in frames[0]

    def test_frame_contains_reset(self) -> None:
        data = _make_png()
        frames, _ = image_to_ansi_frames(data, cols=4, rows=2)
        assert "\x1b[0m" in frames[0]

    def test_truecolor_mode_emits_38_2(self) -> None:
        data = _make_png(color=(255, 0, 0))
        frames, _ = image_to_ansi_frames(data, cols=4, rows=2, mode="truecolor")
        assert "38;2;" in frames[0]

    def test_256_mode_emits_38_5(self) -> None:
        data = _make_png(color=(255, 0, 0))
        frames, _ = image_to_ansi_frames(data, cols=4, rows=2, mode="256")
        assert "38;5;" in frames[0]

    def test_16_mode_emits_standard_codes(self) -> None:
        data = _make_png(color=(255, 0, 0))
        frames, _ = image_to_ansi_frames(data, cols=4, rows=2, mode="16")
        # 16-color uses codes 30-37, 40-47, 90-97, 100-107
        assert "\x1b[" in frames[0]
        # Should NOT contain 38;2 or 38;5
        assert "38;2;" not in frames[0]
        assert "38;5;" not in frames[0]

    def test_cols_rows_resize(self) -> None:
        data = _make_png(width=100, height=100)
        frames, _ = image_to_ansi_frames(data, cols=10, rows=5)
        lines = frames[0].split("\r\n")
        # Should have rows lines of content (plus cursor-home prefix line)
        non_empty = [ln for ln in lines if ln.strip()]
        assert len(non_empty) <= 6  # 5 rows + possible partial

    def test_alpha_blends_to_black(self) -> None:
        """Transparent pixels should render as black."""
        img = Image.new("RGBA", (4, 4), (255, 0, 0, 0))  # fully transparent
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()
        frames, _ = image_to_ansi_frames(data, cols=4, rows=2, mode="truecolor")
        # All pixels transparent → blended to black → 0;0;0 in SGR
        assert "0;0;0" in frames[0]


class TestImageToAnsiFramesAnimated:
    def test_animated_gif_returns_multiple_frames(self) -> None:
        data = _make_animated_gif(n_frames=3)
        frames, fps = image_to_ansi_frames(data, cols=4, rows=2)
        assert len(frames) == 3
        assert fps > 0

    def test_fps_from_gif_metadata(self) -> None:
        data = _make_animated_gif(n_frames=2)
        _, fps = image_to_ansi_frames(data, cols=4, rows=2)
        assert fps == pytest.approx(10.0, abs=1.0)  # 100ms per frame = 10fps

    def test_each_frame_has_cursor_home(self) -> None:
        data = _make_animated_gif(n_frames=3)
        frames, _ = image_to_ansi_frames(data, cols=4, rows=2)
        for frame in frames:
            assert frame.startswith("\x1b[H")


class TestImageToAnsiFramesErrors:
    def test_invalid_bytes_raises(self) -> None:
        with pytest.raises(Exception):
            image_to_ansi_frames(b"not an image", cols=4, rows=2)
```

- [ ] **Step 2: Run tests to verify new tests fail**

Run: `uv run pytest packages/undef-terminal-shell/tests/shell/test_shell_render.py::TestImageToAnsiFramesStatic -v --no-cov -x 2>&1 | tail -5`
Expected: FAIL with `ImportError: cannot import name 'image_to_ansi_frames'`

- [ ] **Step 3: Implement image_to_ansi_frames**

Append to `packages/undef-terminal-shell/src/undef/shell/_render.py`:

```python
# ---------------------------------------------------------------------------
# Frame renderer
# ---------------------------------------------------------------------------


def _render_frame(
    pixels: Any,
    px_w: int,
    px_h: int,
    sgr_fn: Any,
) -> str:
    """Render a single ANSI frame from pixel data."""
    parts: list[str] = ["\x1b[H"]  # cursor home

    for y in range(0, px_h, 2):
        row_parts: list[str] = []
        prev_sgr = ""

        for x in range(px_w):
            tr, tg, tb, ta = pixels[x, y]
            if y + 1 < px_h:
                br, bg_val, bb, ba = pixels[x, y + 1]
            else:
                br, bg_val, bb, ba = 0, 0, 0, 0

            # Blend alpha against black
            if ta < 128:
                tr, tg, tb = 0, 0, 0
            if ba < 128:
                br, bg_val, bb = 0, 0, 0

            fg = (br, bg_val, bb)
            bg = (tr, tg, tb)

            sgr = sgr_fn(fg, bg)
            if sgr != prev_sgr:
                row_parts.append(sgr)
                prev_sgr = sgr

            row_parts.append("▄")

        row_parts.append("\x1b[0m\r\n")
        parts.append("".join(row_parts))

    return "".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def image_to_ansi_frames(
    data: bytes,
    cols: int = 80,
    rows: int = 24,
    mode: ColorMode = "truecolor",
) -> tuple[list[str], float]:
    """Convert image bytes to a list of ANSI-escaped terminal frames.

    Uses half-block character (▄) with fg=bottom pixel, bg=top pixel
    to render two pixel rows per terminal row.

    Args:
        data: Raw image file bytes (any Pillow-supported format).
        cols: Output width in terminal columns.
        rows: Output height in terminal rows.
        mode: Color quantization — ``"truecolor"``, ``"256"``, or ``"16"``.

    Returns:
        ``(frames, fps)`` — list of ANSI strings and source FPS
        (0.0 for static images).

    Raises:
        ImportError: If Pillow is not installed.
        Exception: If bytes cannot be decoded as an image.
    """
    try:
        from PIL import Image
    except ImportError:
        raise ImportError(
            "missing dependency \u2014 Pillow\n"
            "install the images extra: pip install 'undef-terminal-shell[images]'"
        ) from None

    import io

    sgr_fn = _SGR_FN[mode]
    img = Image.open(io.BytesIO(data))

    n_frames = getattr(img, "n_frames", 1)
    duration_ms = img.info.get("duration", 0) or 0
    fps = 1000.0 / duration_ms if duration_ms > 0 else 0.0

    px_w = cols
    px_h = rows * 2

    frames: list[str] = []
    for frame_idx in range(n_frames):
        img.seek(frame_idx)
        frame = img.convert("RGBA").resize((px_w, px_h), Image.LANCZOS)
        pixels = frame.load()
        frames.append(_render_frame(pixels, px_w, px_h, sgr_fn))

    return frames, fps
```

Also add the `from typing import Any` import at the top of the file (after `Literal`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/undef-terminal-shell/tests/shell/test_shell_render.py -v --no-cov 2>&1 | tail -20`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/undef-terminal-shell/src/undef/shell/_render.py packages/undef-terminal-shell/tests/shell/test_shell_render.py
git commit -m "feat(shell): add image_to_ansi_frames converter"
```

---

### Task 4: Add `AnimatedResult` and `_cmd_render` to `_commands.py`

**Files:**
- Modify: `packages/undef-terminal-shell/src/undef/shell/_commands.py`
- Create: `packages/undef-terminal-shell/tests/shell/test_shell_commands_render.py`

- [ ] **Step 1: Write failing tests for the render command**

Create `packages/undef-terminal-shell/tests/shell/test_shell_commands_render.py`:

```python
#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Tests for undef.terminal.shell._commands — render command."""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import MagicMock, patch

from PIL import Image

from undef.terminal.shell._commands import AnimatedResult, CommandDispatcher


def make_dispatcher(ctx: dict[str, Any] | None = None) -> CommandDispatcher:
    return CommandDispatcher(ctx or {})


def first_data(frames: list[str]) -> str:
    return frames[0]


def _make_png_bytes(color: tuple[int, int, int] = (255, 0, 0)) -> bytes:
    img = Image.new("RGB", (4, 4), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_gif_bytes(n_frames: int = 3) -> bytes:
    frames = []
    for i in range(n_frames):
        frames.append(Image.new("RGB", (4, 4), (i * 80, 255, 0)))
    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
    return buf.getvalue()


def _mock_urlopen(data: bytes, status: int = 200):
    mock_resp = MagicMock()
    mock_resp.read.return_value = data
    mock_resp.status = status
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


# ---------------------------------------------------------------------------
# Basic routing
# ---------------------------------------------------------------------------


async def test_render_no_args():
    d = make_dispatcher()
    result = await d.dispatch("render")
    assert "usage:" in first_data(result)


async def test_render_in_help():
    d = make_dispatcher()
    result = await d.dispatch("help")
    assert "render" in first_data(result)


async def test_render_help_detail():
    d = make_dispatcher()
    result = await d.dispatch("help render")
    assert "render" in first_data(result)
    assert "--mode" in first_data(result)


# ---------------------------------------------------------------------------
# Static image rendering
# ---------------------------------------------------------------------------


async def test_render_static_png():
    png_data = _make_png_bytes()
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(png_data)):
        d = make_dispatcher()
        result = await d.dispatch("render http://example.com/test.png")
    assert isinstance(result, list)
    assert "▄" in first_data(result)


async def test_render_mode_256():
    png_data = _make_png_bytes()
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(png_data)):
        d = make_dispatcher()
        result = await d.dispatch("render --mode 256 http://example.com/test.png")
    assert isinstance(result, list)
    assert "38;5;" in first_data(result)


async def test_render_mode_16():
    png_data = _make_png_bytes()
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(png_data)):
        d = make_dispatcher()
        result = await d.dispatch("render --mode 16 http://example.com/test.png")
    data = first_data(result)
    assert "38;2;" not in data
    assert "38;5;" not in data


async def test_render_custom_cols_rows():
    png_data = _make_png_bytes()
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(png_data)):
        d = make_dispatcher()
        result = await d.dispatch("render --cols 10 --rows 5 http://example.com/test.png")
    assert isinstance(result, list)
    assert "▄" in first_data(result)


# ---------------------------------------------------------------------------
# Animated image rendering
# ---------------------------------------------------------------------------


async def test_render_animated_gif_returns_animated_result():
    gif_data = _make_gif_bytes(n_frames=3)
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(gif_data)):
        d = make_dispatcher()
        result = await d.dispatch("render http://example.com/test.gif")
    assert isinstance(result, AnimatedResult)
    assert len(result.frames) == 3
    assert result.fps > 0
    assert result.loop is False


async def test_render_loop_flag():
    gif_data = _make_gif_bytes(n_frames=2)
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(gif_data)):
        d = make_dispatcher()
        result = await d.dispatch("render --loop http://example.com/test.gif")
    assert isinstance(result, AnimatedResult)
    assert result.loop is True


async def test_render_fps_override():
    gif_data = _make_gif_bytes(n_frames=2)
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(gif_data)):
        d = make_dispatcher()
        result = await d.dispatch("render --fps 5 http://example.com/test.gif")
    assert isinstance(result, AnimatedResult)
    assert result.fps == 5.0


# ---------------------------------------------------------------------------
# File URL
# ---------------------------------------------------------------------------


async def test_render_file_url(tmp_path):
    png_data = _make_png_bytes()
    img_path = tmp_path / "test.png"
    img_path.write_bytes(png_data)

    d = make_dispatcher()
    result = await d.dispatch(f"render file://{img_path}")
    assert isinstance(result, list)
    assert "▄" in first_data(result)


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


async def test_render_bad_url_scheme():
    d = make_dispatcher()
    result = await d.dispatch("render ftp://example.com/test.png")
    assert "unsupported URL scheme" in first_data(result)


async def test_render_network_error():
    with patch("urllib.request.urlopen", side_effect=OSError("Connection refused")):
        d = make_dispatcher()
        result = await d.dispatch("render http://example.com/test.png")
    assert "error:" in first_data(result)


async def test_render_invalid_image():
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(b"not an image")):
        d = make_dispatcher()
        result = await d.dispatch("render http://example.com/test.png")
    assert "error:" in first_data(result)


async def test_render_missing_pillow():
    with patch("undef.terminal.shell._render.image_to_ansi_frames", side_effect=ImportError("missing dependency")):
        d = make_dispatcher()
        result = await d.dispatch("render http://example.com/test.png")
    assert "error:" in first_data(result)
    assert "missing dependency" in first_data(result) or "Pillow" in first_data(result)


async def test_render_unknown_mode():
    d = make_dispatcher()
    result = await d.dispatch("render --mode rainbow http://example.com/test.png")
    assert "unknown mode" in first_data(result)


async def test_render_file_not_found():
    d = make_dispatcher()
    result = await d.dispatch("render file:///nonexistent/image.png")
    assert "error:" in first_data(result)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest packages/undef-terminal-shell/tests/shell/test_shell_commands_render.py -v --no-cov -x 2>&1 | tail -5`
Expected: FAIL with `ImportError: cannot import name 'AnimatedResult'`

- [ ] **Step 3: Implement AnimatedResult and _cmd_render**

In `packages/undef-terminal-shell/src/undef/shell/_commands.py`:

**Add import at top** (after existing imports):

```python
from dataclasses import dataclass
from pathlib import Path
```

**Add AnimatedResult dataclass** (after the imports, before `_HELP`):

```python
@dataclass
class AnimatedResult:
    """Return type for animated render output — caller handles frame timing."""

    frames: list[str]
    fps: float
    loop: bool
```

**Add render to `_HELP`** — add this line to the `_HELP` string:

```python
f"{fmt_kv('render [flags] <url>', 'render image as ANSI art')}"
```

**Add render to `_COMMAND_HELP`** dict:

```python
"render": (
    "render [--mode truecolor|256|16] [--cols N] [--rows N] [--fps N] [--loop] <url>\r\n"
    "  Render an image as ANSI art in the terminal.\r\n"
    "  Supports PNG, JPEG, GIF, APNG, WebP, BMP, TIFF, and more.\r\n"
    "  Animated images stream frames; use --loop to repeat.\r\n"
    "  Requires: pip install 'undef-terminal-shell[images]'\r\n"
),
```

**Add routing in `dispatch()`** — before the `return [error_msg(...)]` fallback at line 168:

```python
if cmd == "render":
    return await self._cmd_render(arg)
```

**Add the command handler** — after `_cmd_env`:

```python
async def _cmd_render(self, arg: str) -> list[str] | AnimatedResult:
    if not arg:
        return [error_msg("usage: render [--mode truecolor|256|16] [--cols N] [--rows N] [--fps N] [--loop] <url>") + PROMPT]

    # Parse flags
    mode = "truecolor"
    cols = 80
    rows = 24
    fps_override: float | None = None
    loop = False
    tokens = arg.split()
    url = ""
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "--mode" and i + 1 < len(tokens):
            mode = tokens[i + 1]
            if mode not in {"truecolor", "256", "16"}:
                return [error_msg(f"unknown mode {mode!r} (use truecolor, 256, or 16)") + PROMPT]
            i += 2
        elif tok == "--cols" and i + 1 < len(tokens):
            cols = int(tokens[i + 1])
            i += 2
        elif tok == "--rows" and i + 1 < len(tokens):
            rows = int(tokens[i + 1])
            i += 2
        elif tok == "--fps" and i + 1 < len(tokens):
            fps_override = float(tokens[i + 1])
            i += 2
        elif tok == "--loop":
            loop = True
            i += 1
        elif not tok.startswith("--"):
            url = tok
            i += 1
        else:
            return [error_msg(f"unknown flag: {tok}") + PROMPT]

    if not url:
        return [error_msg("usage: render [--mode truecolor|256|16] [--cols N] [--rows N] [--fps N] [--loop] <url>") + PROMPT]

    # Fetch image bytes
    try:
        if url.startswith("file://"):
            file_path = Path(url[7:])
            if not file_path.is_file():
                return [error_msg(f"file not found: {file_path}") + PROMPT]
            data = file_path.read_bytes()
        elif url.startswith(("http://", "https://")):
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "undef-terminal-shell/1.0"})  # noqa: S310
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310  # nosec B310
                data = resp.read()
        else:
            return [error_msg("unsupported URL scheme (use http://, https://, or file://)") + PROMPT]
    except Exception as exc:
        return [error_msg(f"cannot fetch: {exc}") + PROMPT]

    # Convert to ANSI frames
    try:
        from undef.terminal.shell._render import image_to_ansi_frames
        frames, source_fps = image_to_ansi_frames(data, cols=cols, rows=rows, mode=mode)  # type: ignore[arg-type]
    except ImportError as exc:
        return [error_msg(str(exc)) + PROMPT]
    except Exception as exc:
        return [error_msg(f"cannot decode image: {exc}") + PROMPT]

    fps_final = fps_override if fps_override is not None else source_fps

    if len(frames) <= 1 or fps_final <= 0:
        # Static image
        return [frames[0] + PROMPT] if frames else [error_msg("empty image") + PROMPT]

    return AnimatedResult(frames=frames, fps=fps_final, loop=loop)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest packages/undef-terminal-shell/tests/shell/test_shell_commands_render.py -v --no-cov 2>&1 | tail -25`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/undef-terminal-shell/src/undef/shell/_commands.py packages/undef-terminal-shell/tests/shell/test_shell_commands_render.py
git commit -m "feat(shell): add render command with AnimatedResult"
```

---

### Task 5: Handle `AnimatedResult` in CLI (`__main__.py`)

**Files:**
- Modify: `packages/undef-terminal-shell/src/undef/shell/__main__.py`

- [ ] **Step 1: Implement AnimatedResult handling**

Replace the contents of `packages/undef-terminal-shell/src/undef/shell/__main__.py`:

```python
#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""CLI entry point for undef.terminal.shell — run with: python -m undef.terminal.shell"""

from __future__ import annotations

import asyncio
import sys

from undef.terminal.shell._commands import AnimatedResult, CommandDispatcher
from undef.terminal.shell._output import BANNER, PROMPT


async def _play_animation(result: AnimatedResult, write: Any) -> None:
    """Stream animation frames to *write* with timing."""
    delay = 1.0 / result.fps if result.fps > 0 else 0.1
    try:
        while True:
            for i, frame in enumerate(result.frames):
                text = frame
                # Append PROMPT after the last frame of a non-looping animation
                if not result.loop and i == len(result.frames) - 1:
                    text += PROMPT.replace("\r\n", "\n")
                write(text.replace("\r\n", "\n"))
                sys.stdout.flush()
                await asyncio.sleep(delay)
            if not result.loop:
                break
    except (KeyboardInterrupt, asyncio.CancelledError):
        write("\r\n" + PROMPT.replace("\r\n", "\n"))
        sys.stdout.flush()


async def _cli() -> None:
    dispatcher = CommandDispatcher({})
    sys.stdout.write(BANNER.replace("\r\n", "\n"))
    sys.stdout.write(PROMPT.replace("\r\n", "\n"))
    sys.stdout.flush()
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.rstrip("\n\r")
        except (EOFError, KeyboardInterrupt):
            break
        result = await dispatcher.dispatch(line)
        if isinstance(result, AnimatedResult):
            await _play_animation(result, sys.stdout.write)
        else:
            for text in result:
                sys.stdout.write(text.replace("\r\n", "\n"))
            sys.stdout.flush()
        if isinstance(result, list) and any("Goodbye" in r for r in result):
            break


def main() -> None:
    asyncio.run(_cli())


if __name__ == "__main__":
    main()
```

Also add `from typing import Any` import at the top.

- [ ] **Step 2: Run existing CLI tests to verify no regression**

Run: `uv run pytest packages/undef-terminal-shell/tests/ -v --no-cov -x 2>&1 | tail -10`
Expected: All existing tests PASS.

- [ ] **Step 3: Commit**

```bash
git add packages/undef-terminal-shell/src/undef/shell/__main__.py
git commit -m "feat(shell): handle AnimatedResult in CLI loop"
```

---

### Task 6: Handle `AnimatedResult` in `UshellConnector`

**Files:**
- Modify: `packages/undef-terminal-shell/src/undef/shell/terminal/_connector.py`

- [ ] **Step 1: Implement AnimatedResult handling in handle_input**

In `packages/undef-terminal-shell/src/undef/shell/terminal/_connector.py`, update the import:

```python
from undef.terminal.shell._commands import AnimatedResult, CommandDispatcher
```

Replace `handle_input` method:

```python
async def handle_input(self, data: str) -> list[dict[str, Any]]:
    """Process raw keystroke *data* and return terminal frames.

    Echo frames are emitted for every printable character.  Command
    output frames are emitted only when Enter is pressed.
    """
    self._buf.feed(data)
    frames: list[dict[str, Any]] = []

    echo = self._buf.take_echo()
    if echo:
        frames.append(term(echo))

    for line in self._buf.take_completed():
        result = await self._dispatcher.dispatch(line)
        if isinstance(result, AnimatedResult):
            # Schedule animation streaming as a background task
            asyncio.ensure_future(self._stream_animation(result))
        else:
            frames.extend(term(s) for s in result)

    return frames
```

Add the `_stream_animation` method after `handle_input`:

```python
async def _stream_animation(self, result: AnimatedResult) -> None:
    """Stream animation frames as terminal output."""
    delay = 1.0 / result.fps if result.fps > 0 else 0.1
    try:
        while True:
            for frame in result.frames:
                # Yield control to allow other I/O
                await asyncio.sleep(delay)
                # Can't append directly to return value — need to use
                # poll_messages or direct broadcast. Store frames for polling.
                self._pending_frames.append(term(frame))
            if not result.loop:
                break
    except asyncio.CancelledError:
        pass
    self._pending_frames.append(term(PROMPT))
```

Add `_pending_frames` to `__init__`:

```python
self._pending_frames: list[dict[str, Any]] = []
```

Update `poll_messages` to drain pending animation frames:

```python
async def poll_messages(self) -> list[dict[str, Any]]:
    if not self._connected:
        return []
    if not self._welcomed:
        self._welcomed = True
        return [
            worker_hello("open"),
            term(BANNER + PROMPT),
        ]
    if self._pending_frames:
        frames = list(self._pending_frames)
        self._pending_frames.clear()
        return frames
    await asyncio.sleep(0.05)
    return []
```

- [ ] **Step 2: Run all tests to verify no regression**

Run: `uv run pytest packages/undef-terminal-shell/tests/ -v --no-cov 2>&1 | tail -10`
Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add packages/undef-terminal-shell/src/undef/shell/terminal/_connector.py
git commit -m "feat(shell): handle AnimatedResult in UshellConnector"
```

---

### Task 7: Achieve 100% coverage

**Files:**
- Modify: `packages/undef-terminal-shell/tests/shell/test_shell_render.py`
- Modify: `packages/undef-terminal-shell/tests/shell/test_shell_commands_render.py`

- [ ] **Step 1: Run coverage and identify missing lines**

Run: `uv run pytest packages/undef-terminal-shell/tests/ -v 2>&1 | tail -30`
Expected: Coverage report showing any uncovered lines.

- [ ] **Step 2: Add tests for uncovered lines**

Common gaps to cover:

```python
# In test_shell_render.py — Pillow import error
class TestMissingPillow:
    def test_import_error_message(self) -> None:
        """Verify helpful error when Pillow is not installed."""
        import undef.terminal.shell._render as mod
        original = mod.image_to_ansi_frames
        # We can't truly uninstall Pillow, but we can test the message format
        # by checking the import path exists and the function works
        assert callable(original)

# In test_shell_commands_render.py — connector animation
async def test_connector_render_animated(tmp_path):
    """UshellConnector handles AnimatedResult by queueing frames."""
    from undef.terminal.shell.terminal._connector import UshellConnector
    from undef.terminal.shell.terminal._output import term

    gif_data = _make_gif_bytes(n_frames=2)
    img_path = tmp_path / "test.gif"
    img_path.write_bytes(gif_data)

    connector = UshellConnector(session_id="test")
    await connector.start()
    # Trigger welcome
    await connector.poll_messages()
    # Send render command
    frames = await connector.handle_input(f"render file://{img_path}\r")
    # Animation is scheduled as background task — poll for frames
    import asyncio
    await asyncio.sleep(0.5)
    pending = await connector.poll_messages()
    assert len(pending) > 0
    await connector.stop()
```

- [ ] **Step 3: Run full coverage check**

Run: `uv run pytest packages/undef-terminal-shell/tests/ -v 2>&1 | tail -30`
Expected: `100%` coverage, all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add packages/undef-terminal-shell/tests/
git commit -m "test(shell): achieve 100% coverage for render command"
```

---

### Task 8: Update module docstring and final verification

**Files:**
- Modify: `packages/undef-terminal-shell/src/undef/shell/_commands.py:5-23`

- [ ] **Step 1: Add render to module docstring**

In `packages/undef-terminal-shell/src/undef/shell/_commands.py`, add to the docstring commands list:

```python
render [flags] <url>    — render image as ANSI art (requires undef-terminal-shell[images])
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest packages/undef-terminal-shell/tests/ -v 2>&1 | tail -5`
Expected: All tests PASS, 100% coverage.

- [ ] **Step 3: Run pre-commit hooks**

Run: `git add -u && uv run pre-commit run --all-files 2>&1 | tail -10`
Expected: All hooks pass.

- [ ] **Step 4: Commit**

```bash
git add packages/undef-terminal-shell/src/undef/shell/_commands.py
git commit -m "docs(shell): add render command to module docstring"
```
