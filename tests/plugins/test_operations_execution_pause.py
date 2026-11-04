"""Account execution interruptions preserve whether any submission could have happened."""
from copy import deepcopy
import time

from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.store import Store
from plugins.operations.workspaces import Workspaces


def configured(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Workspaces().store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='中断测试', goal='不重复执行', account_id='account')
    policy['modules'].update(comments=True, dm=True, report=True)
    store.configure(policy, 0)
    return store


def test_expired_unclaimed_and_read_only_commands_never_claim_submission(tmp_path, monkeypatch):
    store = configured(tmp_path, monkeypatch)
    store.current_run_id = store.start_run(local_day(store.policy()[1]), 'comments', '11:00', 1)
    command = store.enqueue('account', {})
    with store.connection() as db:
        db.execute('UPDATE commands SET expires=? WHERE id=?', (time.time() - 1, command))
    result = store.command(command)
    assert result['result']['dispatch_state'] == 'not_started'
    assert result['result']['submitted'] is False
    assert not store.snapshot()['actions']


def test_logout_pauses_shared_web_execution_but_not_independent_analysis(tmp_path, monkeypatch):
    from plugins.operations.login_status import observe
    store = configured(tmp_path, monkeypatch)
    store.claim('worker', busy=True)
    observe(store, {'platform': 'xiaohongshu', 'worker': 'worker', 'state': 'logged_out', 'account_id': ''})
    from plugins.operations.execution_pause import block, guard, ExecutionPaused
    import pytest
    assert block(store)['error_code'] == 'AUTH_REQUIRED'
    guard(store)
    with pytest.raises(ExecutionPaused):
        guard(store, web=True)
    assert store.policy()[1]['paused'] is False
    observe(store, {'platform': 'xiaohongshu', 'worker': 'worker', 'state': 'logged_in', 'account_id': 'account'})
    assert block(store)['error_code'] == 'AUTH_REQUIRED'


def test_debug_continuation_preserves_completed_steps_and_is_idempotent(tmp_path, monkeypatch):
    from devtools import operations_debug as debug
    from devtools.operations_resume import resume
    from plugins.operations.execution_pause import pause, ExecutionPaused
    from plugins.operations import workflow
    store = configured(tmp_path, monkeypatch)
    (tmp_path / 'config.yaml').write_text('development:\n  operations_debug: true\n')
    version, policy = store.policy()
    policy['modules']['research'] = True
    policy['allowed']['comment'] = True
    version = store.configure(policy, version)
    store.claim('worker', busy=True)
    calls = []
    monkeypatch.setattr(workflow, 'research', lambda *args: calls.append('research') or {'usable': 1})
    def interaction(current, *args, **kwargs):
        calls.append('interact')
        if calls.count('interact') == 1:
            result = {'error_code': 'AUTH_REQUIRED', 'error': '账号已退出'}
            pause(current, result)
            raise ExecutionPaused(result)
        return []
    monkeypatch.setattr(workflow, 'interact', interaction)
    first = debug.execute({'task': 'pipeline', 'tasks': list(debug.TASKS), 'request_id': 'resumable', 'version': version})
    assert first['state'] == 'paused'
    assert calls == ['research', 'interact']
    assert all(step['state'] != 'running' for step in first['steps'])
    monkeypatch.setattr(workflow, 'browser', lambda *args: {'state': 'logged_in', 'account_id': 'account'})
    body = {'request_id': 'continue-once', 'expected_revision': first['revision']}
    finished = resume(first['id'], body)
    assert finished['state'] != 'paused'
    assert calls.count('research') == 1
    count = len(calls)
    assert resume(first['id'], body) == finished
    assert len(calls) == count
    assert len(store.objects('report')) == 2


def test_resume_rejects_changed_rule_without_probing_or_clearing_block(tmp_path, monkeypatch):
    import pytest
    from plugins.operations.execution_pause import pause, block
    from plugins.operations.runtime_resume import resume
    store = configured(tmp_path, monkeypatch)
    key = store.start_run(local_day(store.policy()[1]), 'comments', '11:00', 1)
    paused = pause(store, {'error_code': 'AUTH_REQUIRED', 'error': '需要登录'})
    store.finish_run(key, 'paused', '需要登录')
    version, policy = store.policy()
    policy['style'] = '已更改'
    store.configure(policy, version)
    monkeypatch.setattr('plugins.operations.workflow.browser', lambda *args: pytest.fail('must not probe changed policy'))
    with pytest.raises(ValueError, match='日期或规则'):
        resume(key, {'request_id': 'changed', 'expected_revision': paused['revision']}, store)
    assert block(store)


def test_worker_receipt_freezes_only_the_owning_batch_artifacts(tmp_path, monkeypatch):
    from plugins.operations.execution_pause import load
    store = configured(tmp_path, monkeypatch)
    day = local_day(store.policy()[1])
    store.manual_run_id = 'debug:owner'
    store.start_run(day, 'comments', 'debug:owner:comment', 1)
    store.put('brief', {'day': day, 'scope_topic': '中断测试'}, 'own-brief')
    store.put('brief', {'day': day, 'scope_topic': '中断测试', 'manual_run_id': 'debug:other'}, 'newer-other-brief')
    command = store.enqueue('inbox', {'kind': 'comment', 'account_id': 'account'})
    assert store.claim('worker')['id'] == command
    independent_request = Workspaces().store()
    independent_request.acknowledge(command, 'worker', {
        'state': 'blocked', 'error_code': 'AUTH_REQUIRED', 'error': '账号退出',
        'submitted': False, 'dispatch_state': 'read_only'})
    assert load(independent_request, 'debug:owner')['artifacts']['brief_id'] == 'own-brief'
