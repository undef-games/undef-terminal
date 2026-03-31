# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Colima PAM end-to-end smoke test.

Proves that pam_uterm.so fires real PAM events into PamNotifyListener
when a user SSHes into (and exits from) the Colima VM.

Unix domain sockets can't cross the virtiofs boundary (EOPNOTSUPP), so the
listener runs inside Colima using the virtiofs-mounted venv Python, and
writes events to a JSON file on the shared filesystem for the Mac to read.

Usage (from repo root, Colima running with pam_uterm.so installed):
    uv run python scripts/colima_smoke_test.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

COLIMA_PYTHON = "/usr/bin/python3"  # system Python inside Colima VM (Linux)
NOTIFY_SOCKET = Path("/tmp/uterm-notify.sock")  # noqa: S108 — inside Colima VM (/run is root-owned)
EVENT_LOG = Path.home() / ".colima" / "uterm-smoke-events.json"  # virtiofs shared

LISTENER_SCRIPT = """\
import asyncio, json, os
from pathlib import Path
from undef.terminal.pty.pam_listener import PamEvent, PamNotifyListener

SOCKET = "{socket}"
LOG = "{log}"
READY = LOG + ".ready"

events = []

async def handler(event: PamEvent) -> None:
    events.append({{
        "event": event.event,
        "username": event.username,
        "tty": event.tty,
        "pid": event.pid,
        "mode": event.mode,
    }})
    Path(LOG).write_text(json.dumps(events))
    print(f"[pam] {{event.event}} user={{event.username}} pid={{event.pid}}", flush=True)

async def run():
    if os.path.exists(SOCKET): os.unlink(SOCKET)
    listener = PamNotifyListener(SOCKET)
    # await start() so the socket is bound before we signal ready
    await listener.start(handler)
    Path(READY).touch()
    print("[pam] listener ready at " + SOCKET, flush=True)
    try:
        await asyncio.sleep(30)
    except asyncio.CancelledError:
        pass
    await listener.stop()

asyncio.run(run())
"""


def _colima(cmd: str, *, capture: bool = False, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["colima", "ssh", "--", "sh", "-c", cmd],  # noqa: S607
        capture_output=capture,
        text=True,
        timeout=timeout,
    )


def main() -> None:
    # Pre-flight: verify pam_uterm.so is wired
    r = _colima("grep pam_uterm /etc/pam.d/sshd 2>/dev/null || echo MISSING", capture=True)
    pam_line = r.stdout.strip()
    if "MISSING" in pam_line or not pam_line:
        print("ERROR: pam_uterm.so not in /etc/pam.d/sshd inside Colima")
        print("Run: bash scripts/colima_install_uterm.sh")
        sys.exit(1)
    print(f"PAM line: {pam_line}")

    # Clean up any stale files
    EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    ready_flag = Path(str(EVENT_LOG) + ".ready")
    for f in (EVENT_LOG, ready_flag):
        if f.exists():
            f.unlink()

    # Write the listener script to the shared filesystem
    listener_src = LISTENER_SCRIPT.format(
        socket=str(NOTIFY_SOCKET),
        log=str(EVENT_LOG),
    )
    listener_file = Path.home() / ".colima" / "uterm_listener.py"
    listener_file.write_text(listener_src)

    print("Starting PamNotifyListener inside Colima...")
    listener_proc = subprocess.Popen(  # noqa: S603
        ["colima", "ssh", "--", "sh", "-c", f"{COLIMA_PYTHON} {listener_file}"],  # noqa: S607
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # Wait for listener to signal readiness (creates .ready flag file)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if ready_flag.exists():
            break
        time.sleep(0.1)
    else:
        print("ERROR: Listener did not start within 10 seconds")
        listener_proc.terminate()
        sys.exit(1)

    print("Listener ready. SSHing into Colima (triggers PAM open + close)...")

    # Use direct SSH with ControlMaster=no so sshd creates a fresh PAM session.
    # colima ssh reuses an existing ControlMaster connection which bypasses PAM.
    ssh_cfg = Path.home() / ".colima" / "ssh_config"
    ssh_result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "ssh",
            "-F",
            str(ssh_cfg),
            "-o",
            "ControlMaster=no",
            "-o",
            "ControlPath=none",
            "-tt",
            "colima",
            "echo pam_smoke_ok && exit",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if ssh_result.returncode != 0:
        print(f"ERROR: SSH failed: {ssh_result.stderr}")
        listener_proc.terminate()
        sys.exit(1)
    print(f"SSH output: {ssh_result.stdout.strip()}")

    # Wait for close event (PAM fires close after session ends)
    deadline = time.monotonic() + 10
    events: list[dict[str, object]] = []
    while time.monotonic() < deadline:
        if EVENT_LOG.exists():
            try:
                events = json.loads(EVENT_LOG.read_text())
                if any(e["event"] == "close" for e in events):
                    break
            except (json.JSONDecodeError, OSError):
                pass
        time.sleep(0.2)

    listener_proc.terminate()
    try:
        listener_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        listener_proc.kill()

    # Cleanup
    for f in (EVENT_LOG, ready_flag, listener_file):
        if f.exists():
            f.unlink()

    # --- Report ---
    print()
    print("=" * 60)
    print(f"Events received: {len(events)}")
    for ev in events:
        print(f"  {ev['event']:6s}  user={ev['username']}  tty={ev['tty']}  pid={ev['pid']}  mode={ev['mode']}")
    print("=" * 60)

    errors: list[str] = []
    open_events = [e for e in events if e["event"] == "open"]
    close_events = [e for e in events if e["event"] == "close"]

    if not open_events:
        errors.append("FAIL: no 'open' event received")
    else:
        ev = open_events[0]
        if not ev.get("username"):
            errors.append("FAIL: open event has no username")
        if not isinstance(ev.get("pid"), int) or ev["pid"] <= 0:
            errors.append(f"FAIL: open event has invalid pid={ev.get('pid')}")

    if not close_events:
        errors.append("FAIL: no 'close' event received")

    print()
    if errors:
        for err in errors:
            print(err)
        sys.exit(1)
    else:
        print("PASS: open + close events received")
        print(f"      username={open_events[0]['username']}  mode={open_events[0]['mode']}")


if __name__ == "__main__":
    main()
