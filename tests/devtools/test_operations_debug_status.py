"""The task list exposes durable per-step progress independently of opened history."""
from copy import deepcopy

from devtools import operations_debug as debug
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.store import Store


def test_catalog_projects_live_pipeline_and_latest_single_task(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text('development:\n  operations_debug: true\n')
    store = debug.DebugStore('debug:live')
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='任务状态', goal='展示真实进度')
    policy['modules'].update(research=True, organize=True, content=True)
    store.configure(policy, 0)
    assert store.lease('debug:live')
    day = local_day(policy)
    run = debug.new_record('debug:live', 'pipeline', '整链路测试', 1, day)
    run['steps'] = [
        {'id': 'research', 'state': 'completed', 'detail': '已读取资料', 'duration_ms': 80},
        {'id': 'organize', 'state': 'running', 'detail': '开始执行', 'started': run['started']},
        {'id': 'content', 'state': 'pending', 'detail': '等待执行'},
    ]
    store.put('debug_run', run, run['id'])
    store.debug_step = 'organize'
    store.start_run(day, 'organize', 'debug:live:organize', 1)
    store.progress('正在整理第 2 批资料', {'completed': 4, 'total': 10})
    status = debug.catalog()['task_status']
    assert status['research']['state'] == 'completed'
    assert status['organize']['state'] == 'running'
    assert status['organize']['detail'] == '正在整理第 2 批资料'
    assert status['organize']['duration_ms'] >= 0
    assert status['content']['state'] == 'pending'
    store.release('debug:live')
    interrupted = debug.catalog()['task_status']
    assert interrupted['organize']['state'] == interrupted['content']['state'] == 'interrupted'
    newer = debug.new_record('debug:single', 'organize', '资料整理', 1, day)
    newer.update(state='failed', detail='模型服务繁忙（503）', duration_ms=12)
    Store().put('debug_run', newer, newer['id'])
    updated = debug.catalog()['task_status']
    assert updated['organize']['run_id'] == newer['id']
    assert updated['organize']['state'] == 'failed'
    assert updated['research']['run_id'] == run['id']


def test_existing_saved_draft_is_presented_as_generated_without_rewriting_history(tmp_path):
    from devtools.operations_debug_status import task_status
    store = Store(tmp_path / 'view.db')
    run = {'id': 'debug:old', 'task': 'pipeline', 'state': 'needs_attention', 'steps': [
        {'id': 'content', 'title': '内容生产', 'state': 'needs_attention', 'detail': '草稿已保存',
         'result': {'content_id': 'draft', 'ready': False, 'missing': ['缺少获授权图片']}},
        {'id': 'publish', 'state': 'skipped', 'detail': '依赖步骤「内容生产」未完成，不使用旧产物替代本轮结果'},
    ]}
    view = task_status(store, [run])
    assert view['content']['state'] == 'completed'
    assert '缺少获授权图片' in view['publish']['detail']
    assert run['steps'][0]['state'] == 'needs_attention'


def test_scheduled_run_is_visible_and_rejected_debug_does_not_start(tmp_path, monkeypatch):
    import pytest
    from fastapi import HTTPException
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text('development:\n  operations_debug: true\n')
    store = Store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='占用状态', goal='显示后台任务')
    policy['modules']['research'] = True
    store.configure(policy, 0)
    assert store.lease('scheduled')
    run = store.start_run(local_day(policy), 'research', '09:00', 1)
    store.progress('正在读取来源正文')
    current = debug.catalog()['execution']
    assert current['run_id'] == run
    assert '信息采集' in current['message'] and '正在读取来源正文' in current['message']
    with pytest.raises(HTTPException) as rejected:
        debug.execute({'task': 'research', 'request_id': 'occupied', 'version': 1})
    assert rejected.value.status_code == 409
    assert '本次调试未启动' in rejected.value.detail
    assert not store.objects('debug_run')
    store.release('scheduled')
    assert debug.catalog()['execution'] is None


def test_reading_live_pause_does_not_overwrite_execution_threads_batch_snapshot(tmp_path, monkeypatch):
    import json
    from plugins.operations.execution_pause import pause
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = debug.DebugStore('debug:writer')
    store.manual_run_id = 'debug:writer'
    assert store.lease('debug:writer')
    run = debug.new_record('debug:writer', 'pipeline', '执行中的批次', 0, local_day(store.policy()[1]))
    run['steps'] = [{'id': 'research', 'state': 'running', 'detail': '开始'}]
    store.put('debug_run', run, run['id'])
    store.start_run(run['day'], 'research', 'debug:writer:research', 0)
    pause(store, {'error_code': 'BROWSER_UNAVAILABLE', 'error': '读取超时'})
    with store.connection() as db:
        before = db.execute('SELECT data FROM objects WHERE id=?', (run['id'],)).fetchone()[0]
    debug.record(store, run['id'])
    with store.connection() as db:
        after = db.execute('SELECT data FROM objects WHERE id=?', (run['id'],)).fetchone()[0]
    assert json.loads(after) == json.loads(before)


def test_recovery_does_not_replace_a_newer_writer_snapshot(tmp_path):
    from devtools.operations_debug_status import persist_recovery
    from plugins.operations.store import encoded
    store = Store(tmp_path / 'compare.db')
    original = {'id': 'debug:compare', 'state': 'running', 'steps': [{'id': 'research', 'state': 'running'}]}
    store.put('debug_run', original, original['id'])
    writer = {**original, 'state': 'paused', 'steps': [{'id': 'research', 'state': 'paused', 'run_id': 'persisted-run'}]}
    debug.update_record(store, writer)
    stale_recovery = {**original, 'state': 'interrupted'}
    persist_recovery(store, stale_recovery, encoded(original))
    assert stale_recovery == writer
    with store.connection() as db:
        import json
        assert json.loads(db.execute('SELECT data FROM objects WHERE id=?', (original['id'],)).fetchone()[0]) == writer
