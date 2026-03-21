from __future__ import annotations

import time

from undef.terminal.detection.buffer import BufferManager, ScreenBuffer


def test_screen_buffer_creation() -> None:
    sb = ScreenBuffer(screen="hi", screen_hash="h1", snapshot={"screen": "hi"}, captured_at=1.0)
    assert sb.screen == "hi"
    assert sb.matched_prompt_id is None


def test_buffer_manager_add_and_get_recent() -> None:
    mgr = BufferManager(max_size=5)
    for i in range(3):
        mgr.add_screen({"screen": f"s{i}", "screen_hash": f"h{i}", "captured_at": time.time()})
    recent = mgr.get_recent(2)
    assert len(recent) == 2


def test_buffer_manager_max_size_overflow() -> None:
    mgr = BufferManager(max_size=3)
    for i in range(5):
        mgr.add_screen({"screen": f"s{i}", "screen_hash": f"h{i}", "captured_at": time.time()})
    assert len(mgr.get_recent(10)) == 3


def test_buffer_manager_detects_idle() -> None:
    mgr = BufferManager(max_size=5)
    now = time.time()
    mgr.add_screen({"screen": "s", "screen_hash": "same", "captured_at": now - 5})
    mgr.add_screen({"screen": "s", "screen_hash": "same", "captured_at": now})
    assert mgr.detect_idle_state(threshold_seconds=2.0) is True


def test_buffer_manager_not_idle_with_changes() -> None:
    mgr = BufferManager(max_size=5)
    now = time.time()
    mgr.add_screen({"screen": "s1", "screen_hash": "h1", "captured_at": now - 1})
    mgr.add_screen({"screen": "s2", "screen_hash": "h2", "captured_at": now})
    assert mgr.detect_idle_state(threshold_seconds=2.0) is False


def test_buffer_manager_clear() -> None:
    mgr = BufferManager(max_size=5)
    mgr.add_screen({"screen": "s", "screen_hash": "h", "captured_at": time.time()})
    mgr.clear()
    assert mgr.get_recent(5) == []
