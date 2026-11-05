"""Read-heavy recovery and account guards cooperate with active SQLite transactions."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import pytest

from plugins.operations import execution_pause, execution_resume
from plugins.operations.workspaces import Workspaces


@pytest.mark.parametrize('entry', ['store', 'directory'])
def test_opening_initialized_storage_does_not_wait_for_unrelated_writer(tmp_path, monkeypatch, entry):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    directory = Workspaces()
    store = directory.store()
    def read():
        fresh = Workspaces(directory.root)
        return fresh.store().policy() if entry == 'store' else fresh.catalog()
    with ThreadPoolExecutor(max_workers=1) as pool, store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute("INSERT INTO events(at,kind,data) VALUES ('now','writer','{}')")
        pending = pool.submit(read)
        try:
            result = pending.result(timeout=3)
            assert result
        finally:
            db.rollback()


def test_unchanged_shared_asset_mirror_does_not_acquire_write_lock(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    directory = Workspaces()
    original = directory.store()
    original.put('asset', {'authorized': True, 'name': '已授权素材'}, 'asset')
    from plugins.operations.workspace_resources import save_asset
    save_asset(original, 'asset')
    peer = directory.create('同业务主题', business=original.scope['business_id'])
    assert directory.store(peer['business_id'], peer['topic_id']).objects('asset')[0]['topic_id'] == peer['topic_id']
    with ThreadPoolExecutor(max_workers=1) as pool, original.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        future = pool.submit(lambda: Workspaces(directory.root).store(peer['business_id'], peer['topic_id']).objects('asset'))
        try:
            rows = future.result(timeout=3)
            assert rows[0]['topic_id'] == peer['topic_id']
        finally:
            db.rollback()
    with directory.connection() as db:
        db.execute("UPDATE resources SET data=json_set(data,'$.revoked',1) WHERE id='asset'")
    assert directory.store(peer['business_id'], peer['topic_id']).objects('asset')[0]['revoked'] == 1


def test_attach_failure_closes_the_partially_opened_connection(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Workspaces().store()
    connect = sqlite3.connect
    closed = []
    class LockedAttachment(sqlite3.Connection):
        def execute(self, sql, *args):
            if sql.startswith('ATTACH DATABASE'):
                raise sqlite3.OperationalError('database is locked')
            return super().execute(sql, *args)
        def close(self):
            closed.append(True)
            return super().close()
    monkeypatch.setattr(sqlite3, 'connect', lambda *args, **kwargs: connect(*args, **kwargs, factory=LockedAttachment))
    with pytest.raises(sqlite3.OperationalError, match='locked'), store.connection():
        pytest.fail('不能进入未成功附加共享库的事务')
    assert closed == [True]


def test_http_lock_contention_is_retryable_without_replaying_the_request(tmp_path, monkeypatch):
    from starlette.testclient import TestClient
    from hermes_cli import web_server
    from plugins.operations.store import Store
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text('development:\n  operations_debug: true\n')
    store = Workspaces().store()
    calls = []
    def blocked(self, *args, **kwargs):
        calls.append(True)
        raise sqlite3.OperationalError('database is locked')
    monkeypatch.setattr(Store, '__init__', blocked)
    with TestClient(web_server.app) as client:
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        response = client.get('/api/plugins/operations/debug', params={'business_id': store.scope['business_id'], 'topic_id': store.scope['id']})
    assert response.status_code == 503 and response.headers['retry-after'] == '1'
    assert '不要重复提交' in response.json()['detail']
    assert calls == [True]


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
