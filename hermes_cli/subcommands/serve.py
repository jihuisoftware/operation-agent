"""The headless ``hermes serve`` backend used by Desktop and remote clients."""

from __future__ import annotations

import argparse
from typing import Callable


def _add_server_runtime_args(parser) -> None:
    """HTTP and WebSocket backend runtime flags."""
    parser.add_argument(
        "--port", type=int, default=9119, help="Port (default 9119, 0 for auto-assign by OS)")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default 127.0.0.1)")
    parser.add_argument(
        "--insecure", action="store_true",
        help="DEPRECATED / NO-OP. Formerly bypassed auth on a non-loopback "
            "bind. As of the June 2026 hardening it no longer disables "
            "authentication — a public bind always requires an auth provider "
            "(password or OAuth). Bind 127.0.0.1 + tunnel to keep it local.")
    # Existing Desktop launchers pass this; serve never builds a frontend.
    parser.add_argument("--skip-build", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--isolated", action="store_true",
        help="When launched from a named profile, run a dedicated server scoped "
            "to that profile instead of routing to the machine-level server. "
            "Default behavior is unified: profile launches attach to (or start) "
            "ONE machine-level server and preselect the profile.")
    # Internal: set by the unified-launch re-exec to preselect the launching profile.
    parser.add_argument("--open-profile", dest="open_profile", default="", help=argparse.SUPPRESS)
    # Lifecycle flags win over the start-a-server flags (they exit first). No service
    # manager / PID file: they scan the process table for `hermes dashboard|serve`
    # cmdlines and SIGTERM them — the same path `hermes update` uses.
    parser.add_argument(
        "--stop", action="store_true", help="Stop all running Hermes web server processes and exit")
    parser.add_argument(
        "--status", action="store_true", help="List running Hermes web server processes and exit")


def _configure_serve_parser(parser, *, cmd_serve: Callable) -> None:
    """Canonical ``serve`` arguments; shared by the full tree and Desktop's lean hot-path parser."""
    _add_server_runtime_args(parser)
    # Redundant (serve is always headless) but accepted so legacy callers don't error.
    parser.add_argument("--no-open", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--ssh-session-token-file", dest="ssh_session_token_file", metavar="PATH", default=None,
        help="Read a one-shot Desktop SSH session token from PATH")
    parser.add_argument(
        "--ssh-owner-nonce", dest="ssh_owner_nonce", metavar="NONCE", default=None,
        help="Identify a Desktop-owned SSH backend process")
    parser.set_defaults(func=cmd_serve, no_open=True, headless_backend=True, command="serve")


def build_serve_parser(
    *, cmd_serve: Callable, add_help: bool = True, exit_on_error: bool = True,
) -> argparse.ArgumentParser:
    """Build the standalone parser used by the lean ``serve`` dispatch path."""
    parser = argparse.ArgumentParser(
        prog="hermes serve",
        description="Run the Hermes backend server - the JSON-RPC/WebSocket gateway the "
            "desktop app and remote clients connect to. Headless: it never opens "
            "a browser UI.",
        add_help=add_help, exit_on_error=exit_on_error)
    _configure_serve_parser(parser, cmd_serve=cmd_serve)
    return parser


def register_serve_parser(subparsers, *, cmd_serve: Callable) -> None:
    """Attach the Desktop and remote-client backend to the full CLI tree."""
    serve_parser = subparsers.add_parser(
        "serve",
        help="Start the Hermes backend server (headless; powers the desktop app and remote backends)",
        description="Run the Hermes backend server — the JSON-RPC/WebSocket gateway the "
            "desktop app and remote clients connect to. Headless: it never opens "
            "a browser UI.")
    _configure_serve_parser(serve_parser, cmd_serve=cmd_serve)
