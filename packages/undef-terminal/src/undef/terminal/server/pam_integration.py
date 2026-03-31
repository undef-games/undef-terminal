# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Server-side PAM event integration.

Wires PamNotifyListener (undef-terminal-pty) into the session registry so that
sshd logins tracked by pam_uterm.so automatically become undef-terminal sessions.

Two modes, configured via ``ServerConfig.pam.mode``:

  notify (default)
    pam_uterm.so sends a JSON notification.  The server receives it, logs it,
    and — when ``pam.auto_session`` is true — auto-creates a *new* shell as
    the authenticated user (a parallel companion session, not the SSH session
    itself).

  capture
    pam_uterm.so sends the notification AND injects ``LD_PRELOAD=libuterm_capture.so``
    + ``UTERM_CAPTURE_SOCKET=/run/uterm-cap-{pid}.sock`` into the login
    environment.  The server pre-allocates a CaptureSocket at that path so the
    shell's I/O flows directly into a read-only session in the registry — this
    IS the live SSH session, observable via the undef-terminal UI.

The integration starts at server startup and runs until the server shuts down.
It is fully opt-in: nothing happens unless ``config.pam.notify_socket`` is set.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from undef.terminal.pty.pam_listener import PamEvent  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

_TTY_SLUG_RE = re.compile(r"[^a-zA-Z0-9]+")


def _tty_slug(tty: str) -> str:
    """'/dev/pts/3' → 'pts-3'."""
    basename = tty.split("/")[-1] if "/" in tty else tty
    return _TTY_SLUG_RE.sub("-", basename).strip("-") or "tty"


async def run_pam_integration(config: object, registry: object) -> None:
    """
    Long-running coroutine: start PamNotifyListener and dispatch events.

    Wrap in ``asyncio.create_task()``.  Cancelled cleanly on server shutdown.
    """
    from undef.terminal.server.models import PamConfig, ServerConfig

    if not isinstance(config, ServerConfig):
        return

    pam_cfg: PamConfig = config.pam
    if not pam_cfg.notify_socket:
        return

    try:
        from undef.terminal.pty.pam_listener import PamNotifyListener
    except ImportError:
        logger.warning("pam_integration: undef-terminal-pty not installed — PAM listener disabled")
        return

    async def handle(event: object) -> None:
        ev = cast("PamEvent", event)
        logger.info(
            "pam_event event=%s username=%s tty=%s pid=%d mode=%s",
            ev.event,
            ev.username,
            ev.tty,
            ev.pid,
            ev.mode,
        )
        if ev.event == "open":
            await _on_open(ev, pam_cfg, registry)
        elif ev.event == "close":
            await _on_close(ev, registry)

    listener = PamNotifyListener(pam_cfg.notify_socket)
    await listener.start(handle)
    logger.info(
        "pam_integration started socket=%s mode=%s auto_session=%s",
        pam_cfg.notify_socket,
        pam_cfg.mode,
        pam_cfg.auto_session,
    )
    try:
        await asyncio.get_event_loop().create_future()  # wait until cancelled
    except asyncio.CancelledError:
        pass
    finally:
        await listener.stop()
        logger.info("pam_integration stopped")


async def _on_open(event: object, pam_cfg: object, registry: object) -> None:
    from undef.terminal.server.models import PamConfig  # noqa: TC001 — runtime cast needed

    ev = cast("PamEvent", event)
    cfg: PamConfig = pam_cfg  # type: ignore[assignment]

    if cfg.mode == "capture" and ev.capture_socket:
        await _create_capture_session(ev, registry)
    elif cfg.auto_session:
        await _create_notify_session(ev, cfg, registry)


async def _on_close(event: object, registry: object) -> None:
    ev = cast("PamEvent", event)
    slug = _tty_slug(ev.tty)
    session_id = f"pam-{ev.username}-{slug}"
    try:
        # get_session raises if not found; runtime exposes stop()
        runtime = _get_runtime(registry, session_id)
        if runtime is not None:
            stop = getattr(runtime, "stop", None)
            if callable(stop):
                await stop()
            logger.info("pam_session_stopped session_id=%s", session_id)
    except Exception as exc:
        logger.debug("pam_session_stop_failed session_id=%s error=%s", session_id, exc)


# ── notify mode ───────────────────────────────────────────────────────────────


async def _create_notify_session(event: object, pam_cfg: object, registry: object) -> None:
    from undef.terminal.server.models import PamConfig  # noqa: TC001 — runtime cast needed

    ev = cast("PamEvent", event)
    cfg: PamConfig = pam_cfg  # type: ignore[assignment]

    slug = _tty_slug(ev.tty)
    session_id = f"pam-{ev.username}-{slug}"
    command = cfg.auto_session_command or "/bin/bash"

    payload: dict[str, object] = {
        "session_id": session_id,
        "display_name": f"{ev.username} ({ev.tty or 'pam'})",
        "connector_type": "pty",
        "connector_config": {
            "command": command,
            "username": ev.username,
            "inject": False,
        },
        "input_mode": "hijack",
        "auto_start": True,
        "ephemeral": True,
        "tags": ["pam", "notify", ev.username],
        "visibility": "operator",
    }
    await _safe_create(registry, payload)


# ── capture mode ──────────────────────────────────────────────────────────────


async def _create_capture_session(event: object, registry: object) -> None:
    ev = cast("PamEvent", event)
    if ev.capture_socket is None:
        return

    slug = _tty_slug(ev.tty)
    session_id = f"pam-{ev.username}-{slug}"

    payload: dict[str, object] = {
        "session_id": session_id,
        "display_name": f"{ev.username} ({ev.tty or 'pam'}) [live]",
        "connector_type": "pty_capture",
        "connector_config": {
            "socket_path": ev.capture_socket,
        },
        "input_mode": "open",
        "auto_start": True,
        "ephemeral": True,
        "tags": ["pam", "capture", ev.username],
        "visibility": "operator",
    }
    await _safe_create(registry, payload)


# ── helpers ───────────────────────────────────────────────────────────────────


async def _safe_create(registry: object, payload: dict[str, object]) -> None:
    session_id = str(payload.get("session_id", ""))
    try:
        create = registry.create_session  # type: ignore[attr-defined]
        await create(payload)
        logger.info("pam_session_created session_id=%s", session_id)
    except Exception as exc:
        logger.warning("pam_session_create_failed session_id=%s error=%s", session_id, exc)


def _get_runtime(registry: object, session_id: str) -> object | None:
    """Return the HostedSessionRuntime if present, else None."""
    try:
        runtimes: dict[str, object] = registry._runtimes  # type: ignore[attr-defined]
        return runtimes.get(session_id)
    except Exception:
        return None
