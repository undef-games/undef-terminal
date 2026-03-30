#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""Tests for undef.deckmux._transfer — control transfer and keystroke queue."""

from __future__ import annotations

from undef.deckmux._transfer import MAX_QUEUE_LENGTH, TransferManager

# --- Properties ---


def test_auto_transfer_enabled_default() -> None:
    tm = TransferManager()
    assert tm.auto_transfer_enabled is True


def test_auto_transfer_disabled() -> None:
    tm = TransferManager(auto_transfer_idle_s=0)
    assert tm.auto_transfer_enabled is False


def test_auto_transfer_disabled_negative() -> None:
    tm = TransferManager(auto_transfer_idle_s=-1)
    assert tm.auto_transfer_enabled is False


def test_queue_mode_default() -> None:
    tm = TransferManager()
    assert tm.queue_mode == "display"


def test_queue_mode_replay() -> None:
    tm = TransferManager(keystroke_queue_mode="replay")
    assert tm.queue_mode == "replay"


# --- Keystroke queueing ---


def test_queue_keystroke_basic() -> None:
    tm = TransferManager()
    display = tm.queue_keystroke("u1", "ls")
    assert display == "ls"


def test_queue_keystroke_accumulates() -> None:
    tm = TransferManager()
    tm.queue_keystroke("u1", "l")
    display = tm.queue_keystroke("u1", "s")
    assert display == "ls"


def test_queue_keystroke_with_special_keys() -> None:
    tm = TransferManager()
    display = tm.queue_keystroke("u1", "ls\r")
    assert display == "ls↵"


def test_queue_keystroke_overflow_truncates() -> None:
    tm = TransferManager()
    long_input = "a" * (MAX_QUEUE_LENGTH + 50)
    tm.queue_keystroke("u1", long_input)
    # The raw buffer should be truncated to MAX_QUEUE_LENGTH
    display = tm.get_queue_display("u1")
    assert len(display) == MAX_QUEUE_LENGTH


def test_flush_queue() -> None:
    tm = TransferManager()
    tm.queue_keystroke("u1", "hello")
    raw = tm.flush_queue("u1")
    assert raw == "hello"
    # Queue should be empty now
    assert tm.flush_queue("u1") == ""


def test_flush_queue_empty() -> None:
    tm = TransferManager()
    assert tm.flush_queue("u1") == ""


def test_clear_queue() -> None:
    tm = TransferManager()
    tm.queue_keystroke("u1", "hello")
    tm.clear_queue("u1")
    assert tm.get_queue_display("u1") == ""


def test_clear_queue_nonexistent() -> None:
    tm = TransferManager()
    tm.clear_queue("nonexistent")  # should not raise


def test_get_queue_display_empty() -> None:
    tm = TransferManager()
    assert tm.get_queue_display("u1") == ""


def test_get_queue_display_with_data() -> None:
    tm = TransferManager()
    tm.queue_keystroke("u1", "ls\r")
    assert tm.get_queue_display("u1") == "ls↵"


# --- Auto-transfer checks ---


def test_check_auto_transfer_disabled() -> None:
    tm = TransferManager(auto_transfer_idle_s=0)
    warn, transfer = tm.check_auto_transfer(999, ["u2"])
    assert warn is False
    assert transfer is False


def test_check_auto_transfer_no_queued_users() -> None:
    tm = TransferManager(auto_transfer_idle_s=30)
    warn, transfer = tm.check_auto_transfer(999, [])
    assert warn is False
    assert transfer is False


def test_check_auto_transfer_should_transfer() -> None:
    tm = TransferManager(auto_transfer_idle_s=30)
    warn, transfer = tm.check_auto_transfer(30, ["u2"])
    assert warn is False
    assert transfer is True


def test_check_auto_transfer_should_transfer_exceeds() -> None:
    tm = TransferManager(auto_transfer_idle_s=30)
    warn, transfer = tm.check_auto_transfer(45, ["u2"])
    assert warn is False
    assert transfer is True


def test_check_auto_transfer_should_warn() -> None:
    tm = TransferManager(auto_transfer_idle_s=30)
    # Owner idle for 20s (>= 30-10=20), should warn
    warn, transfer = tm.check_auto_transfer(20, ["u2"])
    assert warn is True
    assert transfer is False


def test_check_auto_transfer_warn_only_once() -> None:
    tm = TransferManager(auto_transfer_idle_s=30)
    warn1, _ = tm.check_auto_transfer(22, ["u2"])
    assert warn1 is True
    # Second check at same idle — should NOT warn again
    warn2, _ = tm.check_auto_transfer(25, ["u2"])
    assert warn2 is False


def test_check_auto_transfer_below_warn_threshold() -> None:
    tm = TransferManager(auto_transfer_idle_s=30)
    warn, transfer = tm.check_auto_transfer(15, ["u2"])
    assert warn is False
    assert transfer is False


def test_check_auto_transfer_warn_resets_on_no_queued() -> None:
    tm = TransferManager(auto_transfer_idle_s=30)
    # Trigger warning
    tm.check_auto_transfer(22, ["u2"])
    # No queued users resets warning
    tm.check_auto_transfer(22, [])
    # Now warning should fire again
    warn, _ = tm.check_auto_transfer(22, ["u2"])
    assert warn is True


def test_check_auto_transfer_warn_resets_on_disabled() -> None:
    tm = TransferManager(auto_transfer_idle_s=0)
    # Disabled — always returns False, resets warning
    warn, transfer = tm.check_auto_transfer(999, ["u2"])
    assert warn is False
    assert transfer is False


def test_check_auto_transfer_small_threshold() -> None:
    """With threshold < 10, warn_threshold clamps to 0."""
    tm = TransferManager(auto_transfer_idle_s=5)
    # idle 3s: >= max(0, 5-10)=0, so should warn
    warn, transfer = tm.check_auto_transfer(3, ["u2"])
    assert warn is True
    assert transfer is False


def test_check_auto_transfer_transfer_resets_warning() -> None:
    """Transfer resets the warning flag."""
    tm = TransferManager(auto_transfer_idle_s=30)
    # First: warn
    tm.check_auto_transfer(22, ["u2"])
    # Then: transfer
    _, transfer = tm.check_auto_transfer(30, ["u2"])
    assert transfer is True
    # Warning should be reset, can warn again
    warn, _ = tm.check_auto_transfer(22, ["u2"])
    assert warn is True


# --- reset_warning ---


def test_reset_warning() -> None:
    tm = TransferManager(auto_transfer_idle_s=30)
    tm.check_auto_transfer(22, ["u2"])  # triggers warning
    tm.reset_warning()
    warn, _ = tm.check_auto_transfer(22, ["u2"])
    assert warn is True  # can warn again after reset


# --- build_transfer_message ---


def test_build_transfer_message_display_mode() -> None:
    tm = TransferManager(keystroke_queue_mode="display")
    tm.queue_keystroke("u2", "ls\r")
    msg = tm.build_transfer_message("u1", "u2", "handover")
    assert msg["type"] == "control_transfer"
    assert msg["from_user_id"] == "u1"
    assert msg["to_user_id"] == "u2"
    assert msg["reason"] == "handover"
    assert msg["queued_keys"] == "ls↵"  # display format
    # Queue should be cleared
    assert tm.get_queue_display("u2") == ""


def test_build_transfer_message_replay_mode() -> None:
    tm = TransferManager(keystroke_queue_mode="replay")
    tm.queue_keystroke("u2", "ls\r")
    msg = tm.build_transfer_message("u1", "u2", "auto_idle")
    assert msg["queued_keys"] == "ls\r"  # raw keys for replay
    # Queue should be flushed
    assert tm.flush_queue("u2") == ""


def test_build_transfer_message_empty_queue() -> None:
    tm = TransferManager()
    msg = tm.build_transfer_message("u1", "u2", "admin_takeover")
    assert msg["queued_keys"] == ""


def test_build_transfer_message_replay_empty_queue() -> None:
    tm = TransferManager(keystroke_queue_mode="replay")
    msg = tm.build_transfer_message("u1", "u2", "lease_expired")
    assert msg["queued_keys"] == ""
