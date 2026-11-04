"""Current login observations clarify a sticky pause without rewriting or releasing it."""
from copy import deepcopy
from datetime import datetime, timedelta, UTC

import pytest

from plugins.operations import execution_pause, login_status
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.workspaces import Workspaces


@pytest.fixture
def paused_account(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Workspaces().store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='登录恢复显示', goal='显示当前状态并保留历史', account_id='me')
    policy['modules']['comments'] = True
    store.configure(policy, 0)
    store.manual_run_id = 'debug:login-view'
    run = store.start_run(local_day(policy), 'comments', 'debug:login-view:comment', 1)
    earlier = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    with monkeypatch.context() as clock:
        clock.setattr(execution_pause, 'now_iso', lambda: earlier)
        paused = execution_pause.pause(store, {'error_code': 'AUTH_REQUIRED', 'error': '账号已退出，请重新登录后手动继续',
                                              'account_id': 'me', 'submitted': False})
    store.finish_run(run, 'paused', paused['error'])
    store.claim('desktop', busy=True)
    return store, paused


def observe(store, state, account=''):
    login_status.observe(store, {'platform': 'xiaohongshu', 'worker': 'desktop', 'state': state, 'account_id': account})


def test_confirmed_login_is_display_only_and_does_not_release_or_rewrite_pause(paused_account):
    from plugins.operations.execution_pause_view import describe
    store, paused = paused_account
    original = execution_pause.block(store)
    observe(store, 'logged_in', 'me')
    before_pause = execution_pause.load(store, paused['id'])
    view = describe(store, original)
    assert '已确认登录' in view['error'] and '手动继续' in view['error']
    assert view['historical_error'] == original['error']
    assert view['login_state'] == 'logged_in' and isinstance(view['login_checked_at'], (int, float))
    assert original['error'] == '账号已退出，请重新登录后手动继续'
    assert execution_pause.block(store) == original
    assert execution_pause.load(store, paused['id']) == before_pause
    assert before_pause['state'] == 'paused'
    with store.connection() as db:
        assert describe(store, original, db=db) == view
        assert db.execute('SELECT count(*) FROM commands').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM actions').fetchone()[0] == 0


@pytest.mark.parametrize(('state', 'account'), [('unknown', ''), ('verification', ''), ('logged_out', ''), ('logged_in', 'someone-else')])
def test_latest_unknown_verification_logout_or_different_account_is_not_recovery(paused_account, state, account):
    from plugins.operations.execution_pause_view import describe
    store, _ = paused_account
    original = execution_pause.block(store)
    observe(store, 'logged_in', 'me')
    observe(store, state, account)
    before = execution_pause.block(store)
    view = describe(store, original)
    if state == 'unknown':
        assert '尚待确认' in view['error']
        assert view['historical_error'] == original['error']
    else:
        assert view['error'] == original['error']
    assert view['login_state'] == state
    assert '已确认登录' not in view['error']
    assert execution_pause.block(store) == before


def test_propagating_sticky_guard_preserves_original_failure_time_and_revision(paused_account):
    store, paused = paused_account
    observe(store, 'logged_in', 'me')
    original = execution_pause.block(store)
    before_pause = execution_pause.load(store, paused['id'])
    for _ in range(2):
        with pytest.raises(execution_pause.ExecutionPaused):
            execution_pause.guard(store, web=True)
    assert execution_pause.block(store) == original
    assert execution_pause.load(store, paused['id']) == before_pause


def test_newer_shared_block_takes_priority_without_overwriting_old_pause_history(paused_account):
    store, paused = paused_account
    historical = execution_pause.load(store, paused['id'])
    with store.connection() as db:
        execution_pause.set_block(store, db, {'error_code': 'VERIFICATION_REQUIRED', 'error': '当前页面要求安全验证'})
    newer = execution_pause.block(store)
    with pytest.raises(execution_pause.ExecutionPaused) as stopped:
        execution_pause.guard(store, web=True)
    assert stopped.value.result['error_code'] == 'VERIFICATION_REQUIRED'
    assert execution_pause.block(store) == newer
    assert execution_pause.load(store, paused['id']) == historical


def test_new_failure_after_positive_observation_is_not_reported_as_recovered(paused_account):
    from plugins.operations.execution_pause_view import describe
    store, _ = paused_account
    observe(store, 'logged_in', 'me')
    with store.connection() as db:
        execution_pause.set_block(store, db, {'error_code': 'AUTH_REQUIRED', 'error': '新的网页登录失败', 'account_id': 'me'})
    newer = execution_pause.block(store)
    view = describe(store, newer)
    assert isinstance(newer['cause_at'], (int, float))
    assert view['error'] == '新的网页登录失败'
    assert '已确认登录' not in view['error']
    assert execution_pause.block(store) == newer


def test_legacy_pause_uses_qualified_recent_observation_without_clearing_it(paused_account):
    from plugins.operations.execution_pause_view import describe
    from plugins.operations.store import encoded
    store, _ = paused_account
    old = execution_pause.block(store)
    old.pop('cause_at', None)
    with store.connection() as db:
        key = 'execution-block:' + execution_pause.account_key(store, db)
        db.execute('UPDATE directory.preferences SET data=? WHERE id=?', (encoded(old), key))
    observe(store, 'logged_in', 'me')
    view = describe(store, execution_pause.block(store))
    assert '最近已确认登录' in view['error']
    assert view['historical_error'] == old['error']
    assert execution_pause.block(store) == old


def test_old_pause_does_not_hide_a_newer_shared_failure(paused_account):
    from plugins.operations.execution_pause_view import describe
    store, old = paused_account
    observe(store, 'logged_in', 'me')
    with store.connection() as db:
        execution_pause.set_block(store, db, {'error_code': 'AUTH_REQUIRED', 'error': '后续登录失败', 'account_id': 'me'})
    assert '已确认登录' not in describe(store, old)['error']


def test_debug_projection_updates_current_message_without_rewriting_history(paused_account):
    from devtools.operations_debug_status import present_run
    store, paused = paused_account
    observe(store, 'logged_in', 'me')
    saved = {'id': paused['id'], 'state': 'paused', 'detail': paused['error'], 'steps': [
        {'id': 'comment', 'state': 'paused', 'detail': paused['error']},
        {'id': 'reply', 'state': 'paused', 'detail': '批次暂停：' + paused['error']} ]}
    view = present_run(store, saved)
    assert '已确认登录' in view['detail']
    assert all('已确认登录' in step['detail'] for step in view['steps'])
    assert saved['detail'] == paused['error']
    assert saved['steps'][1]['detail'] == '批次暂停：' + paused['error']
