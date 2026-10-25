"""``activate``: an interactive shell takes on the environment and gives it back.

What a process launched under ``scripts/run-in-hermes-env`` sees is covered in
tests/scripts/test_run_in_hermes_env.py; how the environment is composed, in
test_environment_script.py; the fish port, in test_activate_fish.py.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


from tests.pm.activation_support import (
    ACTIVATE, SETUP_HERMES_SH, bash, bash_env,
    child_env, isolated_checkout, posix,
)


def test_bash_scripts_pass_syntax_check():
    for script in (ACTIVATE, SETUP_HERMES_SH):
        result = subprocess.run(
            [bash(), "-n", posix(script)], capture_output=True, text=True, env=child_env(),
            check=False,
        )
        assert result.returncode == 0, f"{script.name}: {result.stderr}"


def test_activate_fails_cleanly_without_a_store(tmp_path: Path):
    env = bash_env(tmp_path / "empty-store")
    isolated = isolated_checkout(tmp_path) / "activate"
    script = (
        f'source "{posix(isolated)}" 2>/dev/null; '
        f'test $? -ne 0 && echo refused'
    )
    result = subprocess.run(
        [bash(), "-c", script],
        capture_output=True,
        text=True,
        cwd=posix(tmp_path),
        env=env,
        check=False,
    )
    # Without any provisioned python the source must refuse — never
    # silently no-op with a half-activated shell.
    assert "refused" in result.stdout


