"""Ordinary resumes preserve subtask progress, original budgets and truthful completion."""
from copy import deepcopy
import time

import pytest

from plugins.operations import execution_pause, runtime_resume, workflow
from plugins.operations.policy import DEFAULT, local_day, now_iso
from plugins.operations.store import Store, encoded


def configured(tmp_path, monkeypatch, stage='comments', request='batch'):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store(tmp_path / 'resume.db')
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='恢复执行', goal='仅继续未完成工作', account_id='me')
    policy['modules'][stage] = True
    policy['allowed'].update(comment=True, reply=True)
    store.configure(policy, 0)
    store.manual_run_id = request
    run_id = store.start_run(local_day(policy), stage, 'manual:' + request, 1)
    store.put('manual_run', {'day': local_day(policy), 'version': 1}, 'manual:' + request)
    return store, policy, run_id


def paused(store, run_id):
    data = execution_pause.pause(store, {'error_code': 'AUTH_REQUIRED', 'error': '重新登录后继续', 'submitted': False})
    store.finish_run(run_id, 'paused', data['error'])
    return data


def action(store, policy, run_id, *, state='blocked', dispatch=None):
    result = {'state': state, 'submitted': False, 'error': '登录失效'}
    if dispatch:
        result['dispatch_state'] = dispatch
    data = {'kind': 'comment', 'account_id': 'me', 'target': 'note', 'text': '明确的回复',
            'manual_run_id': store.manual_run_id, 'run_id': run_id}
    with store.connection() as db:
        db.execute('INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?)', ('original-action', local_day(policy), 1,
                   'comment', 'note', state, encoded(data), encoded(result), now_iso()))
        db.execute("INSERT INTO commands VALUES (?,?,?,?, 'interrupted','desktop',?,?)", ('original-command', 'original-action',
                   'interact', encoded({**data, 'policy_version': 1}), time.time() - 1, encoded(result)))
    return result


def browser_receipts(store, kind, payload, action_id=None):
    if kind == 'account':
        return {'state': 'logged_in', 'account_id': 'me'}
    result = {'state': 'confirmed', 'evidence': '已核对原动作', 'submitted': True}
    with store.connection() as db:
        db.execute("UPDATE actions SET state='confirmed',result=? WHERE id=?", (encoded(result), action_id))
        db.execute("UPDATE commands SET state='done',result=? WHERE action_id=? AND state='queued'", (encoded(result), action_id))
    return result


def test_resumed_comment_still_checks_reply_without_regenerating_comment(tmp_path, monkeypatch):
    store, policy, run_id = configured(tmp_path, monkeypatch)
    action(store, policy, run_id, dispatch='read_only')
    data = paused(store, run_id)
    monkeypatch.setattr(workflow, 'browser', browser_receipts)
    seen = []
    def remaining(*args, kinds):
        assert args[0].account_required is True
        seen.append(kinds)
        return [{'state': 'confirmed', 'evidence': '已核对回复'}]
    monkeypatch.setattr(workflow, 'interact', remaining)
    result = runtime_resume.resume(data['id'], {'request_id': 'continue', 'expected_revision': data['revision']}, store)
    assert seen == [('reply',)]
    assert result['state'] == 'completed'
    assert store.account_required is False
    with store.connection() as db:
        assert db.execute('SELECT count(*) FROM actions').fetchone()[0] == 1
        assert db.execute('SELECT state FROM runs WHERE id=?', (run_id,)).fetchone()[0] == 'paused'


def test_pause_while_reading_reply_does_not_restart_completed_comment(tmp_path, monkeypatch):
    store, policy, run_id = configured(tmp_path, monkeypatch)
    action(store, policy, run_id, state='confirmed')
    with store.connection() as db:
        db.execute("INSERT INTO commands VALUES (?,NULL,'inbox',?,'interrupted','desktop',?,'{}')", (
            'reply-inventory', encoded({'kind': 'reply', 'account_id': 'me', 'run_id': run_id}), time.time() - 1))
    data = paused(store, run_id)
    monkeypatch.setattr(workflow, 'browser', browser_receipts)
    seen = []
    monkeypatch.setattr(workflow, 'interact', lambda *args, kinds: seen.append(kinds) or [{'state': 'confirmed', 'evidence': '回复完成'}])
    runtime_resume.resume(data['id'], {'request_id': 'continue', 'expected_revision': data['revision']}, store)
    assert seen == [('reply',)]


def test_quick_start_resume_restores_original_options_and_preserves_attempt_history(tmp_path, monkeypatch):
    store, policy, run_id = configured(tmp_path, monkeypatch, 'analytics', 'quick:first')
    options = {'read_limit': 2, 'query_limit': 1, 'model_calls': 3}
    store.put('quick_run', {'version': 1, 'day': local_day(policy), 'state': 'partial', 'options': options}, 'quick:first')
    data = paused(store, run_id)
    monkeypatch.setattr(workflow, 'browser', browser_receipts)
    observed = []
    monkeypatch.setattr(workflow, 'analytics', lambda active, *_: observed.append(active.run_options) or {'state': 'completed', 'detail': '统计完成'})
    body = {'request_id': 'continue', 'expected_revision': data['revision']}
    result = runtime_resume.resume(data['id'], body, store)
    assert observed == [options]
    assert result['state'] == 'completed'
    assert runtime_resume.resume(data['id'], body, store) == result
    assert len(observed) == 1
    from plugins.operations.quick_start import status
    first_run = status(store)
    assert first_run['run']['state'] == 'completed'
    assert first_run['run']['resume_result']['attempt'] == 1
    assert [step['attempt'] for step in first_run['steps']] == [0, 1]
    with store.connection() as db:
        assert db.execute('SELECT state FROM runs WHERE id=?', (run_id,)).fetchone()[0] == 'paused'
        assert db.execute("SELECT count(*) FROM runs WHERE stage='analytics'").fetchone()[0] == 2


def test_manual_resume_without_executable_work_does_not_hide_prior_failure(tmp_path, monkeypatch):
    store, _, run_id = configured(tmp_path, monkeypatch, 'analytics')
    data = paused(store, run_id)
    store.finish_run(run_id, 'failed', '统计任务失败')
    monkeypatch.setattr(workflow, 'browser', browser_receipts)
    result = runtime_resume.resume(data['id'], {'request_id': 'continue', 'expected_revision': data['revision']}, store)
    assert result['state'] == 'failed'
    assert '统计任务失败' in result['detail']
    assert result['steps'][0]['id'] == run_id


@pytest.mark.parametrize('dispatch', [None, 'read_only'])
def test_uncertain_legacy_submit_evidence_is_not_replayed_without_explicit_dispatch_receipt(tmp_path, monkeypatch, dispatch):
    store, policy, run_id = configured(tmp_path, monkeypatch)
    action(store, policy, run_id, dispatch=dispatch)
    store.put('browser_step', {'command_id': 'original-command', 'name': 'submit_interaction', 'phase': 'started'})
    data = paused(store, run_id)
    monkeypatch.setattr(workflow, 'browser', browser_receipts)
    monkeypatch.setattr(workflow, 'interact', lambda *args, **kwargs: [])
    result = runtime_resume.resume(data['id'], {'request_id': 'continue', 'expected_revision': data['revision']}, store)
    assert result['state'] == ('failed' if dispatch is None else 'completed')
    with store.connection() as db:
        count = db.execute('SELECT count(*) FROM commands WHERE action_id=?', ('original-action',)).fetchone()[0]
    assert count == (1 if dispatch is None else 2)


def test_scheduled_action_can_pause_twice_without_new_identity_or_lost_run_history(tmp_path, monkeypatch):
    store, policy, old_run = configured(tmp_path, monkeypatch)
    store.finish_run(old_run, 'completed', '其他批次已结束')
    store.manual_run_id = None
    run_id = store.start_run(local_day(policy), 'comments', '09:00', 1)
    action(store, policy, run_id, dispatch='read_only')
    data = paused(store, run_id)
    attempts = []
    def browser(active, kind, payload, action_id=None):
        if kind == 'account':
            return {'state': 'logged_in', 'account_id': 'me'}
        attempts.append(action_id)
        if len(attempts) == 1:
            failure = {'state': 'blocked', 'submitted': False, 'dispatch_state': 'read_only',
                       'error_code': 'AUTH_REQUIRED', 'error': '再次退出登录'}
            with active.connection() as db:
                db.execute("UPDATE actions SET state='blocked',result=? WHERE id=?", (encoded(failure), action_id))
                db.execute("UPDATE commands SET state='interrupted',result=? WHERE action_id=? AND state='queued'", (encoded(failure), action_id))
            execution_pause.pause(active, failure, payload=payload)
            raise execution_pause.ExecutionPaused(failure)
        return browser_receipts(active, kind, payload, action_id)
    monkeypatch.setattr(workflow, 'browser', browser)
    monkeypatch.setattr(workflow, 'interact', lambda *args, **kwargs: [])
    first = runtime_resume.resume(data['id'], {'request_id': 'first', 'expected_revision': data['revision']}, store)
    assert first['state'] == 'paused'
    updated = execution_pause.load(store, data['id'])
    second = runtime_resume.resume(data['id'], {'request_id': 'second', 'expected_revision': updated['revision']}, Store(store.path))
    assert second['state'] == 'completed' and second['attempt'] == 2
    assert attempts == ['original-action', 'original-action']
    with store.connection() as db:
        assert db.execute('SELECT count(*) FROM actions').fetchone()[0] == 1
        assert db.execute("SELECT state FROM runs WHERE slot LIKE '09:00%' ORDER BY started,rowid").fetchall()[0][0] == 'paused'
        assert [row[0] for row in db.execute("SELECT state FROM runs WHERE slot LIKE '09:00%' ORDER BY started,rowid")] == ['paused', 'paused', 'completed']
