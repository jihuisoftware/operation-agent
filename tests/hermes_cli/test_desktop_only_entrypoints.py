"""The desktop-only product keeps administration and machine calls without terminal chat."""
from argparse import Namespace
import os
from pathlib import Path
import subprocess
import sys

import pytest


def test_retired_frontend_flags_are_rejected_but_gateway_management_remains():
    from hermes_cli.main import _build_cli_parser
    parser, _ = _build_cli_parser()
    for flag in ('--tui', '--tui-native', '--cli'):
        with pytest.raises(SystemExit) as exc:
            parser.parse_args([flag])
        assert exc.value.code == 2
    args = parser.parse_args(['gateway', 'ensure', '--json'])
    assert args.command == 'gateway'


def test_bare_chat_directs_to_desktop_without_starting_an_agent(capsys, monkeypatch):
    from hermes_cli import main
    monkeypatch.setattr(main, '_prepare_agent_startup', lambda *_: pytest.fail('cannot start a terminal chat'))
    main.cmd_chat(Namespace())
    assert 'hermes desktop' in capsys.readouterr().out


def test_payload_rejects_retired_terminal_products(tmp_path):
    from scripts.build.inputs import validate_frontends
    validate_frontends({})
    with pytest.raises(ValueError, match='not supported'):
        validate_frontends({'tui': tmp_path})


def test_old_terminal_preference_cannot_launch_a_terminal_client(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text('display:\n  interface: tui\n', encoding='utf-8')
    result = subprocess.run([sys.executable, '-m', 'hermes_cli.main', 'chat'],
                            cwd=Path(__file__).resolve().parents[2], env={**os.environ, 'HERMES_TUI': '1'},
                            capture_output=True, text=True, encoding='utf-8', timeout=45, check=False)
    assert result.returncode == 0, result.stderr
    assert 'hermes desktop' in result.stdout
