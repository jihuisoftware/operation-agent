"""Resume probes are durable, idempotent, and cannot erase a later account interruption."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event

import pytest

from plugins.operations import execution_pause, execution_resume, workflow
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.workspaces import Workspaces


@pytest.fixture
def paused(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Workspaces().store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='恢复竞争', goal='保留暂停', account_id='me')
    policy['modules'].update(comments=True, report=True)
    store.configure(policy, 0)
    run = store.start_run(local_day(policy), 'report', '09:00', 1)
    saved = execution_pause.pause(store, {'error_code': 'AUTH_REQUIRED', 'error': '请重新登录'})
    store.finish_run(run, 'paused', '请重新登录')
    store.resume_key = run
    return store, saved, {'request_id': 'continue', 'expected_revision': saved['revision']}


def test_probe_interruption_is_preserved_and_failure_replays_without_a_second_probe(paused, monkeypatch):
    store, saved, body = paused
    probes = []
    def probe(*args):
        probes.append(True)
        with store.connection() as db:
            execution_pause.set_block(store, db, {'error_code': 'VERIFICATION_REQUIRED', 'error': '检查期间出现验证码'})
        return {'state': 'logged_in', 'account_id': 'me'}
    monkeypatch.setattr(workflow, 'browser', probe)
    with pytest.raises(ValueError, match='检查期间'):
        execution_resume.prepare(store, saved['id'], body)
    assert execution_pause.block(store)['error_code'] == 'VERIFICATION_REQUIRED'
    assert execution_pause.load(store, saved['id'])['state'] == 'paused'
    with pytest.raises(ValueError, match='检查期间'):
        execution_resume.replay(store, saved['id'], body)
    assert len(probes) == 1


def test_duplicate_request_observes_persisted_checking_without_repeating_probe(paused, monkeypatch):
    store, saved, body = paused
    entered, release = Event(), Event()
    probes = []
    def probe(*args):
        probes.append(True)
        entered.set()
        assert release.wait(10)
        return {'state': 'logged_in', 'account_id': 'me'}
    monkeypatch.setattr(workflow, 'browser', probe)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(execution_resume.prepare, store, saved['id'], body)
        try:
            assert entered.wait(5)
            assert execution_resume.replay(store, saved['id'], body)['state'] == 'checking'
            duplicate, repeated = execution_resume.prepare(store, saved['id'], body)
            assert repeated and duplicate['state'] == 'checking'
        finally:
            release.set()
        current, repeated = pending.result(timeout=10)
    assert current['state'] == 'running' and not repeated
    assert len(probes) == 1


@pytest.mark.parametrize('exit_phase', ['checking', 'running'])
def test_dead_resume_owner_returns_to_paused_without_clearing_unknown_actions(paused, monkeypatch, exit_phase):
    import json
    import os
    import subprocess
    import sys
    store, saved, body = paused
    script = '''
import json,os
from plugins.operations import execution_resume,workflow
from plugins.operations.workspaces import Workspaces
store = Workspaces().store()
key = os.environ['RESUME_TEST_KEY']
store.resume_key = key
assert store.lease('resume-crash-owner')
def probe(*args):
    if os.environ['RESUME_TEST_PHASE'] == 'checking':
        os._exit(0)
    return {'state':'logged_in','account_id':'me'}
workflow.browser = probe
execution_resume.prepare(store,key,json.loads(os.environ['RESUME_TEST_BODY']))
os._exit(0)
'''
    result = subprocess.run([sys.executable, '-c', script], env={**os.environ, 'RESUME_TEST_KEY': saved['id'],
                            'RESUME_TEST_BODY': json.dumps(body), 'RESUME_TEST_PHASE': exit_phase},
                            capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    with store.connection() as db:
        db.execute("INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?)", ('uncertain', saved['day'], 1,
                   'comment', 'note', 'unknown', json.dumps({'account_id': 'me'}), '{}', saved['paused_at']))
    replayed = execution_resume.replay(store, saved['id'], body)
    assert replayed['state'] == 'paused'
    current = execution_pause.load(store, saved['id'])
    assert current['state'] == 'paused' and current['revision'] > saved['revision']
    assert execution_pause.block(store)
    with store.connection() as db:
        assert db.execute("SELECT state FROM actions WHERE id='uncertain'").fetchone()[0] == 'unknown'
        assert not db.execute("SELECT 1 FROM leases WHERE token='resume-crash-owner'").fetchone()
    monkeypatch.setattr(workflow, 'browser', lambda *args: pytest.fail('不能重放已中断的继续请求'))
    assert execution_resume.replay(store, saved['id'], body) == replayed



def test_account_relink_during_probe_cannot_clear_original_account_pause(paused, monkeypatch):
    store, saved, body = paused
    def probe(*args):
        with store.connection() as db:
            db.execute("INSERT INTO directory.accounts(id) VALUES ('replacement')")
            db.execute("UPDATE directory.businesses SET account='replacement' WHERE id=?", (store.scope['business_id'],))
        return {'state': 'logged_in', 'account_id': 'me'}
    monkeypatch.setattr(workflow, 'browser', probe)
    with pytest.raises(ValueError, match='账号关联已变化'):
        execution_resume.prepare(store, saved['id'], body)
    assert execution_pause.load(store, saved['id'])['state'] == 'paused'
    with store.connection() as db:
        assert db.execute('SELECT 1 FROM directory.preferences WHERE id=?', ('execution-block:' + saved['account_link'],)).fetchone()
