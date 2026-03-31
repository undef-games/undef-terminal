# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
E2E tests for pam_uterm.so — the C PAM session module.

These tests verify the full C→Python chain:
  sshd/login invokes pam_sm_open_session
    → pam_uterm.so reads PAM_USER + PAM_TTY via pam_get_item
    → connects to notify socket
    → sends JSON event
    → PamNotifyListener receives and parses it

Requirements (enforced via markers):
  - requires_root   — to write /etc/pam.d/ and copy .so into system path
  - pam_uterm.so must be built at ../../native/pam_uterm/pam_uterm.so

The tests create a temporary PAM service file (e.g. /etc/pam.d/uterm-e2e-NNN)
so they never disturb the real sshd/login PAM stack.  Cleanup always runs in
finally blocks.
"""

from __future__ import annotations

import asyncio
import ctypes
import ctypes.util
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pamela
import pytest

from undef.terminal.pty.pam_listener import PamEvent, PamNotifyListener

# pam_uterm.so uses pam_get_user() which is an undefined symbol resolved from libpam.
# When pamela loads libpam.so it uses RTLD_LOCAL (the default), so pam_uterm.so
# cannot find pam_get_user at dlopen time and silently fails to load (it is "optional").
# On a real system sshd loads libpam with RTLD_GLOBAL, making the symbols visible.
# We replicate that here so pam_uterm.so loads correctly in tests.
_pam_lib = ctypes.util.find_library("pam")
if _pam_lib:
    ctypes.CDLL(_pam_lib, mode=ctypes.RTLD_GLOBAL)


async def _open_session(username: str, service: str) -> None:
    """Run pamela.open_session in a thread so the event loop can accept connections."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, lambda: pamela.open_session(username, service=service)
    )


async def _close_session(username: str, service: str) -> None:
    """Run pamela.close_session in a thread so the event loop can accept connections."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None, lambda: pamela.close_session(username, service=service)
    )


pytestmark = pytest.mark.requires_root

# ── Helpers ───────────────────────────────────────────────────────────────────

_SO_SRC = Path(__file__).parent.parent.parent / "native" / "pam_uterm" / "pam_uterm.so"


def _find_pam_module_dir() -> Path:
    """Return the directory where PAM security modules live on this system."""
    candidates = [
        # Debian/Ubuntu multiarch paths
        Path("/usr/lib/x86_64-linux-gnu/security"),
        Path("/usr/lib/aarch64-linux-gnu/security"),
        # Generic paths
        Path("/usr/lib/security"),
        Path("/lib/security"),
        Path("/usr/lib64/security"),
    ]
    # Prefer the directory that already contains pam_unix.so
    for d in candidates:
        if (d / "pam_unix.so").exists():
            return d
    for d in candidates:
        if d.exists():
            return d
    raise RuntimeError(
        "Cannot find PAM module directory (looked for pam_unix.so in standard paths)"
    )


def _install_module() -> Path:
    """Copy pam_uterm.so into the system PAM module directory. Returns dest path."""
    if not _SO_SRC.exists():
        pytest.skip(
            f"pam_uterm.so not built (run: make -C native/pam_uterm/) [{_SO_SRC}]"
        )
    dest = _find_pam_module_dir() / "pam_uterm.so"
    shutil.copy2(_SO_SRC, dest)
    return dest


async def _collect(events: list[PamEvent], ev: PamEvent) -> None:
    events.append(ev)


# ── Tests ─────────────────────────────────────────────────────────────────────


async def test_pam_module_open_sends_event() -> None:
    """
    pam_uterm.so fires an 'open' JSON event when PAM open_session is called.

    Chain: pamela.open_session → libpam → pam_uterm.so → Unix socket → PamNotifyListener
    """
    dest_so = _install_module()
    svc_path: Path | None = None

    with tempfile.TemporaryDirectory() as td:
        sock = str(Path(td) / "notify.sock")

        # Write a temporary PAM service that chains pam_unix + pam_uterm
        svc_name = f"uterm-e2e-{os.getpid()}"
        svc_path = Path(f"/etc/pam.d/{svc_name}")
        svc_path.write_text(
            "auth     required pam_unix.so\n"
            "account  required pam_unix.so\n"
            f"session  required pam_unix.so\n"
            f"session  optional pam_uterm.so socket={sock}\n"
        )

        events: list[PamEvent] = []
        listener = PamNotifyListener(sock)
        await listener.start(lambda e: _collect(events, e))

        try:
            await _open_session("testuser", svc_name)
            await asyncio.sleep(0.1)

            assert len(events) >= 1, (
                "Expected at least one event — pam_uterm.so may have failed to connect"
            )
            ev = events[0]
            assert ev.event == "open"
            assert ev.username == "testuser"
            assert isinstance(ev.pid, int) and ev.pid > 0
        finally:
            # close_session may succeed or fail depending on PAM implementation;
            # we only care that it doesn't crash the test runner.
            try:
                await _close_session("testuser", svc_name)
            except pamela.PAMError:
                pass
            await listener.stop()
            if svc_path and svc_path.exists():
                svc_path.unlink()
            dest_so.unlink(missing_ok=True)


async def test_pam_module_close_sends_event() -> None:
    """pam_uterm.so fires a 'close' JSON event when PAM close_session is called."""
    dest_so = _install_module()
    svc_path: Path | None = None

    with tempfile.TemporaryDirectory() as td:
        sock = str(Path(td) / "notify.sock")

        svc_name = f"uterm-e2e-close-{os.getpid()}"
        svc_path = Path(f"/etc/pam.d/{svc_name}")
        svc_path.write_text(
            "auth     required pam_unix.so\n"
            "account  required pam_unix.so\n"
            "session  required pam_unix.so\n"
            f"session  optional pam_uterm.so socket={sock}\n"
        )

        events: list[PamEvent] = []
        listener = PamNotifyListener(sock)
        await listener.start(lambda e: _collect(events, e))

        try:
            await _open_session("testuser", svc_name)
            await asyncio.sleep(0.1)
            open_count = len(events)
            assert open_count >= 1
            assert events[0].event == "open"

            await _close_session("testuser", svc_name)
            await asyncio.sleep(0.1)

            close_events = [e for e in events if e.event == "close"]
            assert len(close_events) >= 1, (
                "Expected a close event from pam_sm_close_session"
            )
            assert close_events[0].username == "testuser"
        finally:
            await listener.stop()
            if svc_path and svc_path.exists():
                svc_path.unlink()
            dest_so.unlink(missing_ok=True)


async def test_pam_module_unreachable_socket_does_not_fail_session() -> None:
    """pam_uterm.so must return PAM_SUCCESS even when socket is not listening."""
    dest_so = _install_module()
    svc_path: Path | None = None

    try:
        svc_name = f"uterm-e2e-noconn-{os.getpid()}"
        svc_path = Path(f"/etc/pam.d/{svc_name}")
        svc_path.write_text(
            "auth     required pam_unix.so\n"
            "account  required pam_unix.so\n"
            "session  required pam_unix.so\n"
            # Point to a socket path that nothing is listening on
            "session  optional pam_uterm.so socket=/tmp/uterm-nobody-listening.sock\n"
        )

        # open_session should succeed even though our socket is not there
        await _open_session("testuser", svc_name)
        await _close_session("testuser", svc_name)
        # If we get here without PAMError, pam_uterm.so returned PAM_SUCCESS correctly
    finally:
        if svc_path and svc_path.exists():
            svc_path.unlink()
        dest_so.unlink(missing_ok=True)


async def test_pam_module_custom_socket_path_arg() -> None:
    """The socket= argument in the PAM config is honoured by pam_uterm.so."""
    dest_so = _install_module()
    svc_path: Path | None = None

    with tempfile.TemporaryDirectory() as td:
        # Use a non-default socket path to confirm the arg is read
        custom_sock = str(Path(td) / "custom-path.sock")

        svc_name = f"uterm-e2e-custom-{os.getpid()}"
        svc_path = Path(f"/etc/pam.d/{svc_name}")
        svc_path.write_text(
            "auth     required pam_unix.so\n"
            "account  required pam_unix.so\n"
            "session  required pam_unix.so\n"
            f"session  optional pam_uterm.so socket={custom_sock}\n"
        )

        events: list[PamEvent] = []
        listener = PamNotifyListener(custom_sock)
        await listener.start(lambda e: _collect(events, e))

        try:
            await _open_session("testuser", svc_name)
            await asyncio.sleep(0.1)
            assert any(e.username == "testuser" for e in events), (
                f"No event received on custom socket {custom_sock!r}"
            )
        finally:
            await listener.stop()
            if svc_path and svc_path.exists():
                svc_path.unlink()
            dest_so.unlink(missing_ok=True)


def test_pam_module_so_is_valid_elf() -> None:
    """pam_uterm.so is a valid ELF shared object exporting the required PAM symbols."""
    if not _SO_SRC.exists():
        pytest.skip("pam_uterm.so not built")
    nm = shutil.which("nm") or "nm"
    result = subprocess.run(
        [nm, "-D", str(_SO_SRC)],
        capture_output=True,
        text=True,
        check=True,
    )
    symbols = result.stdout
    assert "pam_sm_open_session" in symbols, "pam_sm_open_session not exported"
    assert "pam_sm_close_session" in symbols, "pam_sm_close_session not exported"
