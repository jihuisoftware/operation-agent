"""Exercise new-start preflight and original-batch resume with unrelated pending posts."""
import json
from datetime import date, timedelta

import pytest

from devtools import operations_debug as debug, operations_selection
from plugins.operations import execution_pause, workflow
from plugins.operations.policy import local_day
from plugins.operations.workspaces import Workspaces
from plugins.operations.workspace_execution import sync_actions
from tests.plugins.test_operations import enable


def environment(tmp_path, monkeypatch, shared=False):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text('development:\n  operations_debug: true\n')
    directory = Workspaces()
    current = directory.store()
    version, policy = enable(current)
    previous = current
    if shared:
        scope = directory.create('历史主题', business=current.scope['business_id'])
        previous = directory.store(scope['business_id'], scope['topic_id'])
        enable(previous)
    previous.manual_run_id = 'debug:historical'
    yesterday = (date.fromisoformat(local_day(policy)) - timedelta(days=1)).isoformat()
    action = previous.reserve_action({'kind': 'publish', 'account_id': 'me', 'target': 'old-manuscript',
        'content': {'title': '旧稿', 'body': '旧正文'}}, previous.policy()[0], yesterday)
    with previous.connection() as db:
        db.execute("UPDATE actions SET state='unknown' WHERE id=?", (action,))
        db.execute("UPDATE commands SET state='done',result=? WHERE action_id=?", (json.dumps({'state': 'unknown'}), action))
        sync_actions(previous, db)
    current.manual_run_id = None
    with current.connection() as db:
        execution_pause.set_block(current, db, {'error_code': 'AUTH_REQUIRED', 'error': '历史登录阻塞'})
    current.claim('desktop', busy=True)
    return current, previous, action, version


@pytest.mark.parametrize('shared', [False, True])
@pytest.mark.parametrize('same_content', [False, True])
def test_selected_publish_probes_account_then_admits_only_independent_content(tmp_path, monkeypatch, shared, same_content):
    current, previous, old_action, version = environment(tmp_path, monkeypatch, shared)
    calls = []
    def browser(_store, kind, payload, *_args):
        calls.append((kind, payload))
        return {'state': 'logged_in', 'account_id': 'me'}
    def publish(store, _policy, day, version, **_kwargs):
        target = 'old-manuscript' if same_content else 'new-manuscript'
        store.reserve_action({'kind': 'publish', 'account_id': 'me', 'target': target,
                              'content': {'title': target, 'body': '本次正文'}}, version, day)
        return {'state': 'queued', 'evidence': '模拟平台，仅创建命令'}
    monkeypatch.setattr(workflow, 'browser', browser)
    monkeypatch.setattr(workflow, 'publish', publish)
    monkeypatch.setattr(operations_selection, 'bind_existing_content', lambda _store, data, _policy: data.update(content_id='new-draft'))
    from plugins.operations.workspaces import ACTIVE_SCOPE
    token = ACTIVE_SCOPE.set((current.scope['business_id'], current.scope['id']))
    try:
        result = debug.execute({'task': 'pipeline', 'tasks': ['publish'], 'mode': 'quick', 'external_actions': 'execute_once',
                                'version': version, 'request_id': 'fresh-post'})
    finally:
        ACTIVE_SCOPE.reset(token)
    assert calls == [('account', {'resume_probe': True, 'preflight': 'explicit_start'})]
    step = result['steps'][0]
    assert step['state'] == ('skipped' if same_content else 'needs_attention')
    if same_content:
        assert step['result']['blocking_action']['id'] == old_action
    assert execution_pause.block(current) is None
    with previous.connection() as db:
        assert db.execute('SELECT state FROM actions WHERE id=?', (old_action,)).fetchone()[0] == 'unknown'
    with current.connection() as db:
        assert db.execute("SELECT count(*) FROM actions WHERE json_extract(data,'$.manual_run_id')='debug:fresh-post'").fetchone()[0] == (0 if same_content else 1)


@pytest.mark.parametrize('own_action', [False, True])
def test_resume_requires_reconciliation_only_for_its_own_pending_actions(tmp_path, monkeypatch, own_action):
    from plugins.operations.execution_resume import prepare
    current, _previous, action, version = environment(tmp_path, monkeypatch)
    current.manual_run_id = 'debug:resume-post'
    current.start_run(local_day(current.policy()[1]), 'publish', current.manual_run_id + ':publish', version)
    paused = execution_pause.pause(current, {'error_code': 'AUTH_REQUIRED', 'error': '请重验账号'})
    with current.connection() as db:
        if own_action:
            db.execute("UPDATE actions SET data=json_set(data,'$.manual_run_id',?) WHERE id=?", (current.manual_run_id, action))
    probes = []
    monkeypatch.setattr(workflow, 'browser', lambda *_args: probes.append(True) or {'state': 'logged_in', 'account_id': 'me'})
    body = {'request_id': 'resume', 'expected_revision': paused['revision']}
    if own_action:
        with pytest.raises(ValueError, match='本批次'):
            prepare(current, current.manual_run_id, body)
        assert not probes
    else:
        restored, _ = prepare(current, current.manual_run_id, body)
        assert restored['state'] == 'running' and probes == [True]


@pytest.mark.parametrize('entry', ['retry', 'resume'])
@pytest.mark.parametrize('same_content', [False, True])
def test_proved_unsubmitted_replay_does_not_bypass_pending_copy_guard(tmp_path, monkeypatch, entry, same_content):
    from plugins.operations.store import Store
    from plugins.operations.action_admission import ActionDeferred
    from plugins.operations.service import retry_action
    from plugins.operations.resume_actions import _continue_action
    store = Store(tmp_path / 'replay.db')
    version, policy = enable(store, limits={**store.policy()[1]['limits'], 'publish': 10})
    day = local_day(policy)
    data = {'kind': 'publish', 'account_id': 'me', 'target': 'original', 'content': {'title': '原稿', 'body': '正文'}}
    store.manual_run_id = 'debug:original'
    original = store.reserve_action(data, version, day)
    with store.connection() as db:
        db.execute("UPDATE actions SET state='confirmed_not_published',result=? WHERE id=?", (json.dumps({'submitted': False, 'dispatch_state': 'read_only'}), original))
        db.execute("UPDATE commands SET state='done' WHERE action_id=?", (original,))
    store.manual_run_id = 'debug:other'
    store.reserve_action({**data, 'target': 'original' if same_content else 'different'}, version, day)
    store.manual_run_id = 'debug:original'
    with store.connection() as db:
        row = dict(db.execute('SELECT * FROM actions WHERE id=?', (original,)).fetchone())
    calls = []
    monkeypatch.setattr(workflow, 'browser', lambda *_args: calls.append(True) or {'state': 'submitted'})
    def replay():
        return retry_action(store, original) if entry == 'retry' else _continue_action(store, row, json.loads(row['data']), policy, day, version)
    if same_content:
        with pytest.raises(ActionDeferred):
            replay()
        assert not calls
    else:
        assert replay()
        with store.connection() as db:
            assert db.execute('SELECT state FROM actions WHERE id=?', (original,)).fetchone()[0] == 'queued'
