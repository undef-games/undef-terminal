from __future__ import annotations

from undef.terminal.detection.detector import PromptDetector


def _make_patterns() -> list[dict]:
    return [
        {"id": "prompt.login", "regex": r"Enter your name:", "input_type": "multi_key", "eol_pattern": "$"},
        {"id": "prompt.password", "regex": r"Password:", "input_type": "multi_key", "eol_pattern": "$"},
    ]


def test_detect_prompt_matches_in_region(snap_factory) -> None:
    d = PromptDetector(_make_patterns())
    match = d.detect_prompt(snap_factory("Welcome\nEnter your name:"))
    assert match is not None
    assert match.prompt_id == "prompt.login"


def test_detect_prompt_returns_none_on_no_match(snap_factory) -> None:
    d = PromptDetector(_make_patterns())
    assert d.detect_prompt(snap_factory("Just some text")) is None


def test_negative_match_excludes_pattern(snap_factory) -> None:
    patterns = [
        {
            "id": "prompt.buy",
            "regex": r"which item",
            "input_type": "single_key",
            "eol_pattern": "$",
            "negative_match": {"pattern": r"stardock", "match_mode": "regex"},
        }
    ]
    d = PromptDetector(patterns)
    assert d.detect_prompt(snap_factory("stardock\nwhich item")) is None
    assert d.detect_prompt(snap_factory("shop\nwhich item")) is not None


def test_negative_match_allows_when_absent(snap_factory) -> None:
    patterns = [
        {
            "id": "prompt.buy",
            "regex": r"which item",
            "input_type": "single_key",
            "eol_pattern": "$",
            "negative_match": {"pattern": r"stardock", "match_mode": "regex"},
        }
    ]
    d = PromptDetector(patterns)
    result = d.detect_prompt(snap_factory("regular store\nwhich item"))
    assert result is not None
    assert result.prompt_id == "prompt.buy"


def test_normalizer_callback_applied(snap_factory) -> None:
    d = PromptDetector(_make_patterns(), normalizer=lambda t: t.replace("name", "NAME"))
    fp1 = d.prompt_fingerprint(snap_factory("Enter your name:"))
    fp2 = d.prompt_fingerprint(snap_factory("Enter your NAME:"))
    assert fp1 == fp2


def test_no_normalizer_preserves_text(snap_factory) -> None:
    d = PromptDetector(_make_patterns())
    fp1 = d.prompt_fingerprint(snap_factory("Enter your name:"))
    fp2 = d.prompt_fingerprint(snap_factory("Enter your NAME:"))
    assert fp1 != fp2


def test_diagnostics_returns_match(snap_factory) -> None:
    d = PromptDetector(_make_patterns())
    diag = d.detect_prompt_with_diagnostics(snap_factory("Enter your name:"))
    assert diag.match is not None
    assert diag.match.prompt_id == "prompt.login"


def test_diagnostics_no_match(snap_factory) -> None:
    d = PromptDetector(_make_patterns())
    diag = d.detect_prompt_with_diagnostics(snap_factory("nothing here"))
    assert diag.match is None


def test_auto_detect_input_type() -> None:
    d = PromptDetector([])
    result = d.auto_detect_input_type("Press any key to continue")
    assert isinstance(result, str)


def test_reload_patterns(snap_factory) -> None:
    d = PromptDetector([])
    assert d.detect_prompt(snap_factory("Enter your name:")) is None
    d.reload_patterns(_make_patterns())
    assert d.detect_prompt(snap_factory("Enter your name:")) is not None


def test_add_pattern(snap_factory) -> None:
    d = PromptDetector([])
    d.add_pattern({"id": "p.new", "regex": r"New prompt", "input_type": "single_key", "eol_pattern": "$"})
    assert d.detect_prompt(snap_factory("New prompt")) is not None


def test_pattern_count() -> None:
    d = PromptDetector(_make_patterns())
    assert d.pattern_count == 2

    d.add_pattern({"id": "p.x", "regex": "X", "input_type": "single_key", "eol_pattern": "$"})
    assert d.pattern_count == 3
