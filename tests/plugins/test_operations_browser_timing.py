"""Queue expiry stays short; one claim grants the slow-network execution budget exactly once."""
from copy import deepcopy
import time

from plugins.operations.policy import DEFAULT
from plugins.operations.workspaces import Workspaces


def test_claim_grants_execution_deadline_but_heartbeats_never_extend_it(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Workspaces().store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='慢网络', goal='读取网页')
    policy['modules']['research'] = True
    store.configure(policy, 0)
    command = store.enqueue('account', {})
    queued = store.command(command)
    assert 0 < queued['expires'] - time.time() <= 120
    received = store.claim('reader')
    assert 590 < received['expires'] - time.time() <= 600
    assert store.claim('reader', busy=True) is None
    assert store.command(command)['expires'] == received['expires']
    with store.connection() as db:
        assert db.execute('SELECT expires FROM directory.account_leases WHERE command_id=?', (command,)).fetchone()[0] == received['expires']


def test_workflow_wait_observes_worker_admission_instead_of_a_fixed_two_minute_cutoff(tmp_path, monkeypatch):
    from plugins.operations.workflow import browser
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Workspaces().store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='慢网络', goal='等待正在执行的网页')
    policy['modules']['research'] = True
    store.configure(policy, 0)
    mono = [0.0]
    monkeypatch.setattr('plugins.operations.workflow.time.monotonic', lambda: mono[0])
    monkeypatch.setattr('plugins.operations.workflow.threading.Event', lambda: type('Event', (), {'wait': lambda self, _: mono.__setitem__(0, mono[0] + 140)})())
    original = store.command
    polls = []
    def progress(identity):
        if not polls:
            row = store.claim('reader')
            polls.append(row['id'])
        else:
            store.acknowledge(identity, 'reader', {'state': 'logged_in', 'account_id': 'me'})
        return original(identity)
    monkeypatch.setattr(store, 'command', progress)
    assert browser(store, 'account', {})['account_id'] == 'me'
    assert mono[0] == 140
