"""Real shell activation must launch PM's Python, including with an old venv present."""

import json
import shlex
import shutil
import subprocess

import pytest

from tests.pm.activation_support import bash_env, fake_store, isolated_checkout


@pytest.mark.platforms("posix")
@pytest.mark.parametrize("shell", ["bash", "zsh"])
def test_repeated_activation_restores_environment_and_uses_pm_python(tmp_path, shell):
    executable = shutil.which(shell)
    if executable is None:
        pytest.skip(f"{shell} is not installed")
    root = isolated_checkout(tmp_path)
    store, entry = fake_store(tmp_path)
    facts_path = store / "facts.json"
    facts = json.loads(facts_path.read_text(encoding="utf-8-sig"))
    facts["packages"]["python"]["env"]["PATH"] = [str(entry / "bin")]
    facts_path.write_text(json.dumps(facts), encoding="utf-8")
    # A local legacy interpreter can emit the environment but must not run the
    # application once PM's Python and dependencies have been selected.
    legacy = root / "venv" / "bin" / "python"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        '#!/bin/sh\n[ "$1" != hermes ] || { echo WRONG_PYTHON >&2; exit 17; }\n'
        f'exec {shlex.quote(str(entry / "bin/python3"))} "$@"\n', encoding="utf-8",
    )
    legacy.chmod(0o755)
    (entry / "bin/python").symlink_to("python3")
    (root / "hermes").write_text("print('PM_PYTHON_OK')\n", encoding="utf-8")
    env = bash_env(store)
    env["PYTHON"] = str(legacy)
    env["HERMES_PM_ACTIVATE_CANARY"] = 'original spaces $HOME `literal`'
    subprocess.run(["git", "init", "-q", str(root)], env=env, check=True, capture_output=True)
    script = f'''
        set -e
        original_path="$PATH"
        original_canary="$HERMES_PM_ACTIVATE_CANARY"
        original_python="$PYTHON"
        PS1='original> '
        source {shlex.quote(str(root / 'activate'))}
        cd {shlex.quote(str(root))}
        hermes
        _hermes_prompt
        first_prompt="$PS1"
        source {shlex.quote(str(root / 'activate'))}
        test "$PS1" = "$first_prompt"
        test "$HERMES_PM_ACTIVATE_CANARY" = env-ok
        hermes
        deactivate
        test "$PATH" = "$original_path"
        test "$HERMES_PM_ACTIVATE_CANARY" = "$original_canary"
        test "$PYTHON" = "$original_python"
        test "$PS1" = 'original> '
        test -z "${{__HERMES_ACTIVATED+set}}"
        ! typeset -f hermes >/dev/null
        printf 'RESTORED\\n'
    '''
    run = subprocess.run([executable, "-c", script], cwd=tmp_path, env=env,
                         capture_output=True, text=True, timeout=40, check=False)
    assert run.returncode == 0, run.stdout + run.stderr
    assert run.stderr == ""
    assert run.stdout.splitlines() == ["PM_PYTHON_OK", "PM_PYTHON_OK", "RESTORED"]
