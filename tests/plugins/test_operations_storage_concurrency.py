"""Read-heavy recovery and account guards cooperate with active SQLite transactions."""
from concurrent.futures import ThreadPoolExecutor

from plugins.operations import execution_pause, execution_resume
from plugins.operations.workspaces import Workspaces


def test_empty_recovery_can_read_while_another_writer_is_active(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Workspaces().store()
    with ThreadPoolExecutor(max_workers=1) as pool, store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute("INSERT INTO events(at,kind,data) VALUES ('now','writer','{}')")
        pending = pool.submit(execution_resume.recover, store)
        try:
            pending.result(timeout=3)
        finally:
            db.rollback()
    assert not store.objects('execution_resume')


def test_block_uses_account_binding_from_its_own_transaction(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Workspaces().store()
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute("INSERT INTO directory.accounts(id) VALUES ('changed-in-transaction')")
        db.execute("UPDATE directory.businesses SET account='changed-in-transaction' WHERE id=?", (store.scope['business_id'],))
        execution_pause.set_block(store, db, {'error_code': 'AUTH_REQUIRED', 'error': '等待重新登录'})
        assert db.execute("SELECT 1 FROM directory.preferences WHERE id='execution-block:changed-in-transaction'").fetchone()
        execution_pause.clear_block(store, db)
        assert not db.execute("SELECT 1 FROM directory.preferences WHERE id='execution-block:changed-in-transaction'").fetchone()


def test_waiting_command_poll_is_read_only_until_a_command_expires(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Workspaces().store()
    command = store.enqueue('account', {})
    with ThreadPoolExecutor(max_workers=1) as pool, store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute("INSERT INTO events(at,kind,data) VALUES ('now','writer','{}')")
        pending = pool.submit(store.command, command)
        try:
            result = pending.result(timeout=3)
        finally:
            db.rollback()
    assert result['state'] == 'queued'
