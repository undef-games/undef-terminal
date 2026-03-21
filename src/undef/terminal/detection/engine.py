from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from undef.terminal.detection.detector import PromptDetector
from undef.terminal.detection.extractor import extract_kv
from undef.terminal.detection.loader import load_ruleset
from undef.terminal.detection.models import PromptDetection, PromptDetectionDiagnostics, PromptMatch

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from undef.terminal.detection.rules import RuleSet

logger = logging.getLogger(__name__)


class DetectionEngine:
    """Rule-based prompt detection and data extraction engine.

    Accepts rules at init, compiles patterns, and provides sync
    process_screen() for prompt detection + KV extraction.
    """

    def __init__(
        self,
        rules: RuleSet | Path | str,
        *,
        normalizer: Callable[[str], str] | None = None,
    ) -> None:
        """Compile rules into a PromptDetector + KVExtractor.

        Args:
            rules: A RuleSet object, path to rules.json, or JSON string.
            normalizer: Optional function to normalize prompt region text
                before fingerprinting (e.g. strip volatile timer fields).

        Raises:
            ValueError: If rules cannot be loaded or parsed.
        """
        self._normalizer = normalizer
        self._enabled = True
        self._last_fingerprint: str = ""
        self._last_match: PromptMatch | None = None
        ruleset = load_ruleset(rules)
        patterns = ruleset.to_prompt_patterns()
        self._detector = PromptDetector(patterns, normalizer=normalizer)

    def process_screen(self, snapshot: dict[str, Any]) -> PromptDetection | None:
        """Detect prompt and extract KV data from a screen snapshot.

        Sync — pure CPU regex matching, no I/O.
        Returns None if no prompt matched or engine is disabled.
        """
        if not self._enabled:
            return None

        fingerprint = self._detector.prompt_fingerprint(snapshot)
        if fingerprint and fingerprint == self._last_fingerprint:
            prompt_match = self._last_match
        else:
            prompt_match = self._detector.detect_prompt(snapshot)
            self._last_fingerprint = fingerprint
            self._last_match = prompt_match

        if prompt_match is None:
            return None

        kv_data: dict[str, Any] = {}
        if prompt_match.kv_extract:
            extracted = extract_kv(snapshot.get("screen", ""), prompt_match.kv_extract)
            if extracted:
                kv_data = extracted

        return PromptDetection(
            prompt_id=prompt_match.prompt_id,
            input_type=prompt_match.input_type,
            kv_data=kv_data,
            match=prompt_match,
        )

    def detect_with_diagnostics(self, snapshot: dict[str, Any]) -> PromptDetectionDiagnostics:
        """Detect with partial-match info for debugging."""
        return self._detector.detect_prompt_with_diagnostics(snapshot)

    def reload_rules(self, rules: RuleSet | Path | str) -> None:
        """Hot-reload rules. Transactional: on failure, old rules remain active.

        Raises:
            ValueError: If new rules cannot be loaded.
        """
        ruleset = load_ruleset(rules)
        patterns = ruleset.to_prompt_patterns()
        # Only swap if compilation succeeds
        self._detector = PromptDetector(patterns, normalizer=self._normalizer)
        self._last_fingerprint = ""
        self._last_match = None

    @property
    def detector(self) -> PromptDetector:
        """Access the underlying PromptDetector."""
        return self._detector

    @property
    def pattern_count(self) -> int:
        """Number of compiled patterns."""
        return self._detector.pattern_count

    @property
    def enabled(self) -> bool:
        """Whether the engine processes screens."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
