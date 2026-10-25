"""Desktop exposes a headless backend without a browser-dashboard command."""

from __future__ import annotations

import argparse

import pytest

from hermes_cli.subcommands.serve import register_serve_parser


def _serve(args):
    return args


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    register_serve_parser(parser.add_subparsers(dest="command"), cmd_serve=_serve)
    return parser

def test_serve_preserves_desktop_runtime_arguments_and_is_headless():
    args = _parser().parse_args([
        "serve", "--host", "127.0.0.1", "--port", "0", "--isolated",
        "--ssh-session-token-file", "token.txt", "--ssh-owner-nonce", "0123456789abcdef",
    ])

    assert args.func is _serve
    assert args.headless_backend and args.no_open and args.isolated
    assert args.port == 0
    assert args.ssh_session_token_file == "token.txt"
    assert args.ssh_owner_nonce == "0123456789abcdef"


@pytest.mark.parametrize("argv", [["dashboard"], ["dashboard", "register"]])
def test_browser_dashboard_is_not_a_product_entrypoint(argv):
    with pytest.raises(SystemExit) as exc:
        _parser().parse_args(argv)

    assert exc.value.code == 2
