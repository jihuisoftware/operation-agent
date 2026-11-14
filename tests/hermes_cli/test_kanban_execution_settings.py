"""Automatic dispatch is board-owned; a disabled board never admits a new automatic claim."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from hermes_cli import kanban_db as kb, kanban_db_connect as kbc, kanban_db_dispatch as dispatch
from hermes_cli import kanban_execution as execution


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    monkeypatch.setenv('HERMES_KANBAN_HOME', str(tmp_path))
    monkeypatch.setattr(dispatch, '_profile_exists_fn', lambda: lambda _: True)
    return tmp_path


def tick(conn, **kwargs):
    return dispatch.dispatch_once(conn, spawn_fn=lambda *_a, **_kw: None, max_in_progress=1,
                                  max_in_progress_per_profile=1, reconcile_orphans=False, **kwargs)


def test_settings_default_closed_survive_reopen_and_manual_run_does_not_enable(home):
    with kbc.connect_closing() as conn:
        task = kb.create_task(conn, title='任务', assignee='default')
        assert execution.read(conn) == {'enabled': False, 'revision': 0, 'updated_at': None}
        assert not tick(conn, automatic=True).spawned
        assert kb.get_task(conn, task).status == 'ready'
        assert len(tick(conn).spawned) == 1
        assert not execution.read(conn)['enabled']
        assert execution.update(conn, enabled=True, expected_revision=0)['revision'] == 1
        with pytest.raises(execution.ExecutionConflict):
            execution.update(conn, enabled=False, expected_revision=0)
    with kbc.connect_closing() as reopened:
        assert execution.read(reopened)['enabled']
        execution.update(reopened, enabled=False, expected_revision=1)
        assert kb.get_task(reopened, task).status == 'running'


def test_disabling_between_selection_and_claim_prevents_the_spawn(home, monkeypatch):
    selected, proceed = Event(), Event()
    original = kb.claim_task
    def delayed_claim(conn, *args, **kwargs):
        selected.set()
        assert proceed.wait(10)
        return original(conn, *args, **kwargs)
    with kbc.connect_closing() as conn:
        identity = kb.create_task(conn, title='竞态', assignee='default')
        execution.update(conn, enabled=True, expected_revision=0)
    monkeypatch.setattr(kb, 'claim_task', delayed_claim)
    def run():
        with kbc.connect_closing() as conn:
            return tick(conn, automatic=True)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run)
        try:
            assert selected.wait(10)
            with kbc.connect_closing() as conn:
                execution.update(conn, enabled=False, expected_revision=1)
        finally:
            proceed.set()
        assert not future.result(timeout=10).spawned
    with kbc.connect_closing() as conn:
        assert kb.get_task(conn, identity).status == 'ready'
        assert conn.execute('SELECT count(*) FROM task_runs').fetchone()[0] == 0


def test_boards_share_one_capacity_but_not_execution_permission(home):
    kb.create_board('alpha')
    kb.create_board('beta')
    with kbc.connect_closing(board='alpha') as a, kbc.connect_closing(board='beta') as b:
        first = kb.create_task(a, title='A', assignee='default')
        second = kb.create_task(b, title='B', assignee='default')
        execution.update(a, enabled=True, expected_revision=0)
        assert not tick(b, board='beta', automatic=True).spawned
        assert len(tick(a, board='alpha', automatic=True).spawned) == 1
        execution.update(b, enabled=True, expected_revision=0)
        assert not tick(b, board='beta', automatic=True).spawned
        assert kb.complete_task(a, first, result='已完成隔离测试', force=True)
        assert len(tick(b, board='beta', automatic=True).spawned) == 1
        assert kb.get_task(b, second).status == 'running'


@pytest.mark.parametrize('host_local', [True, False])
def test_stop_refuses_surviving_worker_then_parks_confirmed_stop(home, monkeypatch, host_local):
    with kbc.connect_closing() as conn:
        task_id = kb.create_task(conn, title='可停止任务', assignee='default')
        tick(conn)
        task = kb.get_task(conn, task_id)
        monkeypatch.setattr(kb, '_terminate_reclaimed_worker', lambda *a, **kw: {
            'host_local': host_local, 'prev_pid': 999, 'termination_attempted': True, 'terminated': False})
        assert not execution.stop_run(conn, task_id, task.current_run_id)
        assert kb.get_task(conn, task_id).status == 'running'
        monkeypatch.setattr(kb, '_terminate_reclaimed_worker', lambda *a, **kw: {
            'host_local': True, 'prev_pid': 999, 'termination_attempted': True, 'terminated': True})
        assert execution.stop_run(conn, task_id, task.current_run_id)
        assert kb.get_task(conn, task_id).status == 'blocked'
        execution.update(conn, enabled=True, expected_revision=0)
        assert not tick(conn, automatic=True).spawned
        assert not execution.stop_run(conn, task_id, task.current_run_id)


def test_import_never_carries_execution_authorization(home, tmp_path):
    from hermes_cli import kanban_transfer
    kb.create_board('source')
    with kbc.connect_closing(board='source') as conn:
        kb.create_task(conn, title='仍是同一任务', assignee='default')
        execution.update(conn, enabled=True, expected_revision=0)
    archive = kanban_transfer.export_board('source', str(tmp_path / 'transfer.tar.gz'))
    imported = kanban_transfer.import_board(archive['archive'])
    with kbc.connect_closing(board=imported['board']) as conn:
        assert not execution.read(conn)['enabled']
        assert conn.execute('SELECT title FROM tasks').fetchone()[0] == '仍是同一任务'
    with kbc.connect_closing(board='source') as conn:
        assert execution.read(conn)['enabled']


def test_gateway_health_and_tick_share_board_permission(home, monkeypatch):
    from gateway.kanban_watchers_dispatcher import _KanbanDispatcher, _resolve_dispatcher_settings
    with kbc.connect_closing() as conn:
        task_id = kb.create_task(conn, title='定时任务', assignee='default')
    spawned = []
    monkeypatch.setattr(dispatch, '_default_spawn', lambda task, *a, **kw: spawned.append(task.id))
    settings = _resolve_dispatcher_settings({}, kb)
    watcher = _KanbanDispatcher(kb, settings)
    assert settings.max_in_progress == settings.max_in_progress_per_profile == 1
    assert not watcher.ready_nonempty()
    watcher.tick_once_for_board('default')
    assert not spawned
    with kbc.connect_closing() as conn:
        execution.update(conn, enabled=True, expected_revision=0)
    assert watcher.ready_nonempty()
    watcher.tick_once_for_board('default')
    assert spawned == [task_id]
