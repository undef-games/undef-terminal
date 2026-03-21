from __future__ import annotations

from typing import Any

import pytest

from undef.terminal.detection.engine import DetectionEngine
from undef.terminal.detection.rules import RuleSet


def test_engine_init_from_path(simple_rules_file) -> None:
    engine = DetectionEngine(simple_rules_file)
    assert engine.pattern_count == 1
    assert engine.enabled is True


def test_engine_init_from_ruleset() -> None:
    rs = RuleSet(version="1.0", game="t", prompts=[])
    engine = DetectionEngine(rs)
    assert engine.pattern_count == 0


def test_engine_init_raises_on_bad_rules(tmp_path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    with pytest.raises(ValueError):
        DetectionEngine(bad)


def test_process_screen_returns_detection(simple_rules_file, snap_factory) -> None:
    engine = DetectionEngine(simple_rules_file)
    result = engine._sync_process_screen(snap_factory("Hello there"))
    assert result is not None
    assert result.prompt_id == "prompt.hello"


def test_process_screen_returns_none_on_no_match(simple_rules_file, snap_factory) -> None:
    engine = DetectionEngine(simple_rules_file)
    assert engine._sync_process_screen(snap_factory("Goodbye")) is None


def test_disabled_engine_returns_none(simple_rules_file, snap_factory) -> None:
    engine = DetectionEngine(simple_rules_file)
    engine.enabled = False
    assert engine._sync_process_screen(snap_factory("Hello there")) is None


def test_enabled_setter(simple_rules_file) -> None:
    engine = DetectionEngine(simple_rules_file)
    assert engine.enabled is True
    engine.enabled = False
    assert engine.enabled is False
    engine.enabled = True
    assert engine.enabled is True


def test_fingerprint_cache_skips_redetection(simple_rules_file, snap_factory) -> None:
    engine = DetectionEngine(simple_rules_file)
    snap = snap_factory("Hello there")
    r1 = engine._sync_process_screen(snap)
    r2 = engine._sync_process_screen(snap)
    assert r1 is not None and r2 is not None
    assert r1.prompt_id == r2.prompt_id


def test_fingerprint_cache_invalidated_on_new_screen(simple_rules_file, snap_factory) -> None:
    engine = DetectionEngine(simple_rules_file)
    r1 = engine._sync_process_screen(snap_factory("Hello there"))
    r2 = engine._sync_process_screen(snap_factory("Something else"))
    assert r1 is not None
    assert r2 is None


def test_reload_rules_success(simple_rules_file, rules_file_factory, snap_factory) -> None:
    engine = DetectionEngine(simple_rules_file)
    assert engine.pattern_count == 1
    new = rules_file_factory(
        [
            {"id": "p.a", "match": {"pattern": "A", "match_mode": "contains"}, "input_type": "single_key"},
            {"id": "p.b", "match": {"pattern": "B", "match_mode": "contains"}, "input_type": "single_key"},
        ]
    )
    engine.reload_rules(new)
    assert engine.pattern_count == 2


def test_reload_rules_transactional(simple_rules_file, tmp_path) -> None:
    engine = DetectionEngine(simple_rules_file)
    assert engine.pattern_count == 1
    bad = tmp_path / "bad.json"
    bad.write_text("invalid")
    with pytest.raises(ValueError):
        engine.reload_rules(bad)
    assert engine.pattern_count == 1  # old rules preserved


def test_reload_clears_fingerprint_cache(simple_rules_file, rules_file_factory, snap_factory) -> None:
    engine = DetectionEngine(simple_rules_file)
    engine._sync_process_screen(snap_factory("Hello there"))
    new = rules_file_factory(
        [
            {"id": "p.bye", "match": {"pattern": "Goodbye", "match_mode": "contains"}, "input_type": "single_key"},
        ]
    )
    engine.reload_rules(new)
    # Cache was cleared, so new rules apply even to same screen hash
    assert engine._sync_process_screen(snap_factory("Goodbye")) is not None


def test_normalizer_passed_to_detector(simple_rules_file) -> None:
    engine = DetectionEngine(simple_rules_file, normalizer=lambda t: t.upper())
    assert engine.detector is not None


def test_detector_property(simple_rules_file) -> None:
    engine = DetectionEngine(simple_rules_file)
    assert hasattr(engine.detector, "detect_prompt")
    assert hasattr(engine.detector, "detect_prompt_with_diagnostics")


def test_detect_with_diagnostics(simple_rules_file, snap_factory) -> None:
    engine = DetectionEngine(simple_rules_file)
    diag = engine.detect_with_diagnostics(snap_factory("Hello there"))
    assert diag.match is not None
    assert diag.match.prompt_id == "prompt.hello"


def test_kv_extraction_populates_kv_data(kv_rules_file, snap_factory) -> None:
    engine = DetectionEngine(kv_rules_file)
    result = engine._sync_process_screen(snap_factory("Sector 42 : Credits: 15,000"))
    assert result is not None
    assert result.kv_data.get("sector") == 42
    assert result.kv_data.get("credits") == 15000


def test_kv_extraction_empty_when_no_kv_config(simple_rules_file, snap_factory) -> None:
    engine = DetectionEngine(simple_rules_file)
    result = engine._sync_process_screen(snap_factory("Hello there"))
    assert result is not None
    assert result.kv_data == {}


# ---------------------------------------------------------------------------
# Async process_screen tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_process_screen_detection(simple_rules_file, snap_factory) -> None:
    engine = DetectionEngine(simple_rules_file)
    result = await engine.process_screen(snap_factory("Hello there"))
    assert result is not None
    assert result.prompt_id == "prompt.hello"


@pytest.mark.asyncio
async def test_async_process_screen_populates_is_idle_and_buffer(simple_rules_file, snap_factory) -> None:
    engine = DetectionEngine(simple_rules_file)
    result = await engine.process_screen(snap_factory("Hello there"))
    assert result is not None
    assert result.is_idle is not None
    assert isinstance(result.is_idle, bool)
    assert result.buffer is not None


@pytest.mark.asyncio
async def test_add_hook_called_after_detection(simple_rules_file, snap_factory) -> None:
    engine = DetectionEngine(simple_rules_file)
    calls: list[Any] = []

    async def hook(snapshot: Any, detection: Any, buffer: Any, is_idle: bool) -> None:
        calls.append((snapshot, detection, buffer, is_idle))

    engine.add_hook(hook)
    await engine.process_screen(snap_factory("Hello there"))
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_hook_receives_correct_args(simple_rules_file, snap_factory) -> None:
    engine = DetectionEngine(simple_rules_file)
    received: list[Any] = []

    async def hook(snapshot: Any, detection: Any, buffer: Any, is_idle: bool) -> None:
        received.append({"detection": detection, "is_idle": is_idle, "buffer": buffer})

    engine.add_hook(hook)
    snap = snap_factory("Hello there")
    await engine.process_screen(snap)

    assert len(received) == 1
    assert received[0]["detection"] is not None
    assert received[0]["detection"].prompt_id == "prompt.hello"
    assert isinstance(received[0]["is_idle"], bool)
    assert received[0]["buffer"] is not None


@pytest.mark.asyncio
async def test_screen_saver_called_on_match(simple_rules_file, snap_factory, tmp_path) -> None:
    from undef.terminal.detection.saver import ScreenSaver

    saver = ScreenSaver(base_dir=tmp_path, enabled=True)
    engine = DetectionEngine(simple_rules_file, screen_saver=saver)
    await engine.process_screen(snap_factory("Hello there"))
    assert saver.get_saved_count() > 0


@pytest.mark.asyncio
async def test_set_namespace_updates_screen_saver(simple_rules_file, tmp_path) -> None:
    from undef.terminal.detection.saver import ScreenSaver

    saver = ScreenSaver(base_dir=tmp_path, namespace="old")
    engine = DetectionEngine(simple_rules_file, screen_saver=saver, namespace="old")
    engine.set_namespace("new_game")
    assert engine.namespace == "new_game"
    assert saver._namespace == "new_game"


def test_debug_state_returns_dict(simple_rules_file) -> None:
    engine = DetectionEngine(simple_rules_file)
    state = engine.debug_state()
    assert isinstance(state, dict)
    assert "screen_buffer" in state
    assert "idle_threshold_s" in state
