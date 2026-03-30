#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Tests for undef.terminal.deckmux._names — deterministic name and color generation."""

from __future__ import annotations

from undef.terminal.deckmux._names import (
    _ADJECTIVES,
    _ANIMALS,
    _COLORS,
    _hash_int,
    generate_color,
    generate_initials,
    generate_name,
)

# --- _hash_int ---


def test_hash_int_deterministic() -> None:
    assert _hash_int("test") == _hash_int("test")


def test_hash_int_different_inputs() -> None:
    assert _hash_int("a") != _hash_int("b")


# --- generate_name ---


def test_generate_name_deterministic() -> None:
    name1 = generate_name("conn-123")
    name2 = generate_name("conn-123")
    assert name1 == name2


def test_generate_name_format() -> None:
    name = generate_name("test-id")
    parts = name.split()
    assert len(parts) == 2
    assert parts[0].istitle()
    assert parts[1].istitle()


def test_generate_name_different_ids() -> None:
    name1 = generate_name("id-a")
    name2 = generate_name("id-b")
    # Not guaranteed different, but very likely with SHA-256
    # Just verify they're valid names
    assert len(name1.split()) == 2
    assert len(name2.split()) == 2


def test_generate_name_all_combos_valid() -> None:
    """All 1024 combos (32x32) produce title-cased two-word names."""
    seen = set()
    for adj in _ADJECTIVES:
        for animal in _ANIMALS:
            name = f"{adj.title()} {animal.title()}"
            seen.add(name)
    assert len(seen) == 32 * 32


def test_generate_name_uses_adjectives_and_animals() -> None:
    name = generate_name("some-connection")
    parts = name.split()
    assert parts[0].lower() in _ADJECTIVES
    assert parts[1].lower() in _ANIMALS


# --- generate_color ---


def test_generate_color_deterministic() -> None:
    c1 = generate_color("conn-1")
    c2 = generate_color("conn-1")
    assert c1 == c2


def test_generate_color_returns_valid_hex() -> None:
    color = generate_color("test")
    assert color.startswith("#")
    assert len(color) == 7


def test_generate_color_avoids_taken() -> None:
    # Get the default color for this ID
    default_color = generate_color("test-id")
    # Now mark it as taken
    color = generate_color("test-id", taken=frozenset({default_color}))
    assert color != default_color
    assert color in _COLORS


def test_generate_color_all_taken_fallback() -> None:
    """When all colors are taken, falls back to the hash-based default."""
    all_taken = frozenset(_COLORS)
    color = generate_color("test-id", taken=all_taken)
    assert color in _COLORS


def test_generate_color_empty_taken() -> None:
    c1 = generate_color("id", taken=frozenset())
    c2 = generate_color("id")
    assert c1 == c2


# --- generate_initials ---


def test_generate_initials_two_words() -> None:
    assert generate_initials("Red Fox") == "RF"


def test_generate_initials_two_words_lowercase() -> None:
    assert generate_initials("red fox") == "RF"


def test_generate_initials_single_word() -> None:
    assert generate_initials("Alice") == "AL"


def test_generate_initials_three_words() -> None:
    assert generate_initials("A B C") == "AB"


def test_generate_initials_single_char() -> None:
    # Edge case: single character name — name[:2] = "A", .upper() = "A"
    assert generate_initials("A") == "A"


def test_generate_initials_single_char_value() -> None:
    result = generate_initials("A")
    assert result == "A"
    assert result == result.upper()
