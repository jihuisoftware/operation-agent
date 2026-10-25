"""Runtime lifecycle commands remain available without messaging setup/enrollment."""

import argparse

import pytest

from hermes_cli.subcommands.gateway import build_gateway_parser


def _parser():
    parser = argparse.ArgumentParser(prog="hermes")
    build_gateway_parser(parser.add_subparsers(dest="command"), cmd_gateway=lambda args: args,
                         cmd_proxy=lambda args: args)
    return parser


def test_runtime_ensure_and_restart_remain_parseable():
    args = _parser().parse_args(["gateway", "ensure", "--json", "--timeout", "30"])
    assert args.gateway_command == "ensure"
    assert args.json and args.timeout == "30"
    args = _parser().parse_args(["gateway", "restart", "--detach"])
    assert args.gateway_command == "restart" and args.detach


@pytest.mark.parametrize("command", ["setup", "enroll"])
def test_messaging_setup_and_relay_enrollment_are_removed(command):
    with pytest.raises(SystemExit) as exc:
        _parser().parse_args(["gateway", command])
    assert exc.value.code == 2
