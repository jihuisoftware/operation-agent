"""The distributed state package preserves SQLite sessions without root storage modules."""
import subprocess
import sys
import tomllib
from pathlib import Path

from setuptools import Distribution, find_packages
from setuptools.command.build_py import build_py


ROOT = Path(__file__).resolve().parents[1]


def test_packaged_store_round_trips_a_session(tmp_path):
    config = tomllib.loads((ROOT / 'pyproject.toml').read_text())
    discovery = config['tool']['setuptools']['packages']['find']
    packages = find_packages(where=str(ROOT), include=discovery['include'])
    distribution = Distribution({
        'packages': [name for name in packages if name == 'state' or name.startswith('state.')],
        'package_dir': {'': str(ROOT)},
    })
    distribution.script_name = str(ROOT / "setup.py")
    build = build_py(distribution)
    build.ensure_finalized()
    build.build_lib = str(tmp_path / 'lib')
    build.run()
    # The package comes from build output; other shared runtime dependencies come from the checkout.
    probe = '''
import sys
from pathlib import Path
sys.path[:0] = [sys.argv[1], sys.argv[2]]
from state.store import SessionDB
from state import store
assert Path(store.__file__).is_relative_to(Path(sys.argv[1]))
assert 'hermes_state' not in sys.modules
with_db = SessionDB(Path(sys.argv[3]) / 'state.db')
with_db.create_session('packaged-session', source='desktop')
with_db.append_message('packaged-session', 'user', '保存中文会话')
with_db.close()
reopened = SessionDB(Path(sys.argv[3]) / 'state.db')
assert reopened.get_messages('packaged-session')[0]['content'] == '保存中文会话'
reopened.close()
'''
    subprocess.run([sys.executable, '-I', '-c', probe, build.build_lib, str(ROOT), str(tmp_path)],
                   check=True, capture_output=True, text=True, timeout=30)
