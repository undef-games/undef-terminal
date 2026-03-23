from undef.terminal.detection.input_type import auto_detect_input_type

from undef.terminal.detection.buffer import BufferManager, ScreenBuffer
from undef.terminal.detection.detector import PromptDetector
from undef.terminal.detection.engine import DetectionEngine
from undef.terminal.detection.extractor import KVExtractor, extract_kv
from undef.terminal.detection.loader import load_ruleset
from undef.terminal.detection.models import (
    PromptDetection,
    PromptDetectionDiagnostics,
    PromptMatch,
    ScreenSnapshot,
)
from undef.terminal.detection.rules import RuleSet
from undef.terminal.detection.saver import ScreenSaver

__all__ = [
    "BufferManager",
    "DetectionEngine",
    "KVExtractor",
    "PromptDetection",
    "PromptDetectionDiagnostics",
    "PromptDetector",
    "PromptMatch",
    "RuleSet",
    "ScreenBuffer",
    "ScreenSaver",
    "ScreenSnapshot",
    "auto_detect_input_type",
    "extract_kv",
    "load_ruleset",
]
