from __future__ import annotations

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
    result = engine.process_screen(snap_factory("Hello there"))
    assert result is not None
    assert result.prompt_id == "prompt.hello"


def test_process_screen_returns_none_on_no_match(simple_rules_file, snap_factory) -> None:
    engine = DetectionEngine(simple_rules_file)
    assert engine.process_screen(snap_factory("Goodbye")) is None


def test_disabled_engine_returns_none(simple_rules_file, snap_factory) -> None:
    engine = DetectionEngine(simple_rules_file)
    engine.enabled = False
    assert engine.process_screen(snap_factory("Hello there")) is None


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
    r1 = engine.process_screen(snap)
    r2 = engine.process_screen(snap)
    assert r1 is not None and r2 is not None
    assert r1.prompt_id == r2.prompt_id


def test_fingerprint_cache_invalidated_on_new_screen(simple_rules_file, snap_factory) -> None:
    engine = DetectionEngine(simple_rules_file)
    r1 = engine.process_screen(snap_factory("Hello there"))
    r2 = engine.process_screen(snap_factory("Something else"))
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
    engine.process_screen(snap_factory("Hello there"))
    new = rules_file_factory(
        [
            {"id": "p.bye", "match": {"pattern": "Goodbye", "match_mode": "contains"}, "input_type": "single_key"},
        ]
    )
    engine.reload_rules(new)
    # Cache was cleared, so new rules apply even to same screen hash
    assert engine.process_screen(snap_factory("Goodbye")) is not None


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
    result = engine.process_screen(snap_factory("Sector 42 : Credits: 15,000"))
    assert result is not None
    assert result.kv_data.get("sector") == 42
    assert result.kv_data.get("credits") == 15000


def test_kv_extraction_empty_when_no_kv_config(simple_rules_file, snap_factory) -> None:
    engine = DetectionEngine(simple_rules_file)
    result = engine.process_screen(snap_factory("Hello there"))
    assert result is not None
    assert result.kv_data == {}
