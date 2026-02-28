#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
# SPDX-License-Identifier: AGPL-3.0-or-later
#
"""undefterm — command-line WebSocket terminal proxy.

Starts a standalone FastAPI/uvicorn server that accepts browser WebSocket
connections and proxies them to a remote telnet (or other) host.

Usage::

    undefterm proxy bbs.example.com 23
    undefterm proxy bbs.example.com 23 --port 9000 --bind 127.0.0.1 --path /ws/term
    undefterm proxy bbs.example.com 22 --transport ssh

Requires the ``[cli]`` extra::

    pip install 'undef-terminal[cli]'
"""

from __future__ import annotations

import argparse
import sys

# ---------------------------------------------------------------------------
# Subcommand: proxy
# ---------------------------------------------------------------------------


def _cmd_proxy(args: argparse.Namespace) -> None:
    """Start the WsTerminalProxy server."""
    try:
        import uvicorn
        from fastapi import FastAPI

        from undef.terminal.fastapi import WsTerminalProxy
        from undef.terminal.transports.base import ConnectionTransport
    except ImportError as exc:
        print(  # noqa: T201
            f"error: missing dependency — {exc}\n"
            "install the cli extra: pip install 'undef-terminal[cli]'",
            file=sys.stderr,
        )
        sys.exit(1)

    transport_factory: type[ConnectionTransport] | None = None
    if args.transport == "ssh":
        try:
            from undef.terminal.transports.ssh import SSHTransport

            transport_factory = SSHTransport
        except ImportError:
            print(  # noqa: T201
                "error: SSH transport requires asyncssh: pip install 'undef-terminal[ssh]'",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        from undef.terminal.transports.telnet import TelnetTransport

        transport_factory = TelnetTransport

    proxy = WsTerminalProxy(
        args.host,
        args.bbs_port,
        transport_factory=transport_factory,
    )

    app = FastAPI(title="uterm proxy", docs_url=None, redoc_url=None)
    app.include_router(proxy.create_router(args.path))

    print(  # noqa: T201
        f"uterm proxy  {args.transport}://{args.host}:{args.bbs_port}"
        f"  →  ws://{args.bind}:{args.port}{args.path}"
    )

    uvicorn.run(app, host=args.bind, port=args.port, log_level="warning")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="undefterm",
        description="WebSocket terminal proxy for BBS/telnet servers.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # ---- proxy subcommand ----
    proxy_p = sub.add_parser(
        "proxy",
        help="start a WebSocket→telnet proxy server",
        description=(
            "Accept browser WebSocket connections and proxy them "
            "to a remote telnet/SSH host."
        ),
    )
    proxy_p.add_argument("host", metavar="HOST", help="remote BBS hostname or IP")
    proxy_p.add_argument("bbs_port", metavar="PORT", type=int, help="remote BBS port")
    proxy_p.add_argument(
        "--port", "-p",
        metavar="PORT",
        type=int,
        default=8765,
        help="local HTTP listen port (default: 8765)",
    )
    proxy_p.add_argument(
        "--bind",
        metavar="ADDR",
        default="0.0.0.0",  # noqa: S104
        help="bind address (default: 0.0.0.0)",
    )
    proxy_p.add_argument(
        "--path",
        metavar="PATH",
        default="/ws/terminal",
        help="WebSocket endpoint path (default: /ws/terminal)",
    )
    proxy_p.add_argument(
        "--transport",
        choices=["telnet", "ssh"],
        default="telnet",
        help="outbound transport protocol (default: telnet)",
    )
    proxy_p.set_defaults(func=_cmd_proxy)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    """CLI entry point — called by the ``uterm`` script."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    args.func(args)
