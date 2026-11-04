"""New paused reports snapshot current observations without rewriting past execution facts."""
from copy import deepcopy
from datetime import datetime, UTC

from plugins.operations import execution_pause, login_status
from plugins.operations.policy import DEFAULT, local_day, now_iso
from plugins.operations.report import daily_report
from plugins.operations.store import Store


TASKS = [('publish', 'publish', '图文发布'), ('comment', 'comments', '主动评论'),
         ('reply', 'comments', '评论回复'), ('dm', 'dm', '收到私信处理'), ('follow', 'follow', '条件回关')]


def save_batch(store, policy, identity, tasks, reason):
    store.manual_run_id = identity
    run = store.start_run(local_day(policy), 'publish', identity + ':publish', 1)
    execution_pause.pause(store, reason)
    store.finish_run(run, 'paused', reason['error'])
    store.put('debug_run', {'day': local_day(policy), 'state': 'paused', 'task': 'pipeline', 'started': now_iso(),
              'selected_tasks': [task for task, _, _ in tasks], 'steps': [
                  {'id': task, 'module': module, 'title': title, 'state': 'paused', 'detail': reason['error'],
                   **({'run_id': run} if index == 0 else {})} for index, (task, module, title) in enumerate(tasks)]}, identity)


def test_new_report_projects_login_and_all_selected_unstarted_steps_but_old_snapshot_stays(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store(tmp_path / 'reports.db')
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='登录恢复日报', goal='显示当前事实', account_id='me')
    policy['modules'].update(publish=True, comments=True, dm=True, follow=True)
    store.configure(policy, 0)
    store.report_phase = 'paused'
    reason = {'error_code': 'AUTH_REQUIRED', 'error': '账号已退出，请重新登录后手动继续'}
    save_batch(store, policy, 'debug:old', [('publish', 'publish', '其他批次的发布')], reason)
    old = daily_report(store, local_day(policy))
    old_details = next(row['markdown'] for row in store.objects('report_detail') if row['id'] == old['details_id'])
    saved_reason = execution_pause.block(store)
    store.claim('desktop', busy=True)
    login_status.observe(store, {'platform': 'xiaohongshu', 'worker': 'desktop', 'state': 'logged_in', 'account_id': 'me'})
    with store.connection() as db:
        checked = db.execute("SELECT checked FROM platform_logins WHERE worker='desktop'").fetchone()[0]
    save_batch(store, policy, 'debug:current', TASKS, saved_reason)
    current = daily_report(store, local_day(policy))
    summary = current['markdown']
    full = next(row['markdown'] for row in store.objects('report_detail') if row['id'] == current['details_id'])
    assert '已确认登录' in summary
    for _, _, title in TASKS:
        assert title in summary and title in full
        assert title in summary.split('## 当前阻塞', 1)[1]
    assert summary.count('尚未开始') >= 4
    assert '其他批次的发布' not in summary and '其他批次的发布' not in full
    assert '历史暂停原因：账号已退出' in full
    assert datetime.fromtimestamp(checked, UTC).isoformat() in full
    assert datetime.fromtimestamp(saved_reason['cause_at'], UTC).isoformat() in full
    assert '历史暂停原因：' not in summary
    assert next(row['markdown'] for row in store.objects('report') if row['id'] == old['id']) == old['markdown']
    assert next(row['markdown'] for row in store.objects('report_detail') if row['id'] == old['details_id']) == old_details
    login_status.observe(store, {'platform': 'xiaohongshu', 'worker': 'desktop', 'state': 'logged_out', 'account_id': ''})
    assert daily_report(store, local_day(policy))['markdown'] == summary
    assert next(row['markdown'] for row in store.objects('report_detail') if row['id'] == current['details_id']) == full


def test_preflight_report_uses_latest_same_batch_result_without_claiming_external_success(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store(tmp_path / 'preflight.db')
    day = local_day(store.policy()[1])
    store.manual_run_id = 'debug:other-preflight'
    store.event('account_preflight', {'day': day, 'state': 'logged_in', 'detail': '其他批次的核对结果', 'account_id': 'other-account'})
    store.manual_run_id = 'debug:preflight-report'
    store.event('account_preflight', {'day': day, 'state': 'paused', 'error_code': 'AUTH_REQUIRED', 'error': '此前核对失败'})
    store.event('account_preflight', {'day': day, 'state': 'logged_in', 'account_id': 'private-account-123456',
        'cleared_error_code': 'AUTH_REQUIRED', 'detail': '启动前已核对实际登录，旧登录暂停已解除；历史批次未自动恢复'})
    report = daily_report(store, day)
    full = next(row['markdown'] for row in store.objects('report_detail') if row['id'] == report['details_id'])
    for text in (report['markdown'], full):
        assert '## 启动前账号核对' in text and '核对通过' in text
        assert '历史批次未自动恢复' in text
        assert '外部动作记录 0 条' in text and '已核对成功 0 次' in text
        assert '其他批次的核对结果' not in text and '此前核对失败' not in text
        assert 'private-account-123456' not in text and 'other-account' not in text
    store.event('account_preflight', {'day': day, 'state': 'paused', 'error_code': 'AUTH_REQUIRED', 'error': '后续再次退出'})
    assert daily_report(store, day)['markdown'] == report['markdown']


def test_report_does_not_duplicate_a_started_step_when_batch_snapshot_has_not_saved_run_id(tmp_path, monkeypatch):
    from plugins.operations.run_scope import ReportScope
    from plugins.operations.report_execution import snapshot
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store(tmp_path / 'race.db')
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='步骤关联', goal='不重复项目')
    policy['modules']['research'] = True
    store.configure(policy, 0)
    store.manual_run_id = 'debug:race'
    day = local_day(policy)
    run = store.start_run(day, 'research', 'debug:race:research', 1)
    reason = {'error_code': 'BROWSER_UNAVAILABLE', 'error': '只读网页超时'}
    execution_pause.pause(store, reason)
    store.finish_run(run, 'paused', reason['error'])
    store.put('debug_run', {'day': day, 'selected_tasks': ['research'], 'steps': [
        {'id': 'research', 'module': 'research', 'title': '信息采集', 'state': 'paused', 'detail': reason['error']}
    ]}, 'debug:race')
    rows = snapshot(ReportScope(store, day))['runs']
    assert len(rows) == 1
    assert rows[0]['id'] == run and not rows[0].get('unstarted')
