"""History clearing is topic-scoped and never removes action or recovery evidence."""
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from devtools import operations_debug as debug, operations_task_details as details
from plugins.operations.policy import local_day
from plugins.operations.workspaces import Workspaces


def test_clear_all_finished_history_keeps_live_batches_and_business_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text('development:\n  operations_debug: true\n')
    directory = Workspaces()
    store = directory.store()
    day = local_day(store.policy()[1])
    for index in range(35):
        record = debug.new_record(f'debug:old-{index}', 'report', '日报', 0, day)
        record['state'] = 'failed' if index % 2 else 'completed'
        store.put('debug_run', record, record['id'])
    for state in ('running', 'paused', 'pending'):
        record = debug.new_record('debug:' + state, 'report', state, 0, day)
        record['state'] = state
        store.put('debug_run', record, record['id'])
    with store.connection() as db:
        db.execute("INSERT OR REPLACE INTO leases VALUES ('account','debug:running',?)", (time.time() + 600,))
        db.execute("INSERT INTO actions VALUES ('published-old',?,0,'publish','target','submitted','{}','{}',?)", (day, day))
    store.put('content', {'title': '仍需保留的草稿'}, 'draft')
    app = FastAPI()
    app.include_router(debug.router)
    client = TestClient(app)
    before = debug.record(store, 'debug:old-0')
    response = client.post('/debug/history/clear')
    assert response.status_code == 200
    assert response.json() == {'cleared': 35, 'retained': 3}
    catalog = client.get('/debug').json()
    assert {row['id'] for row in catalog['runs']} == {'debug:running', 'debug:paused', 'debug:pending'}
    assert {row['id'] for row in details.history(store, 'report')['runs']} == {'debug:running', 'debug:paused', 'debug:pending'}
    assert debug.record(store, 'debug:old-0') == before
    debug.update_record(store, before)
    assert client.post('/debug/history/clear').json()['cleared'] == 0
    with store.connection() as db:
        assert db.execute('SELECT state FROM actions').fetchone()[0] == 'submitted'
    assert store.objects('content')[0]['id'] == 'draft'
    other = directory.create('其他主题', business=store.scope['business_id'])
    second = directory.store(other['business_id'], other['topic_id'])
    second.put('debug_run', before, before['id'])
    assert len(details.history(second, 'report')['runs']) == 1
    # Older batches can still be resumable even before their debug projection
    # has been refreshed from "interrupted" to "paused".
    legacy = {**before, 'id': 'debug:legacy', 'state': 'interrupted'}
    store.put('debug_run', legacy, legacy['id'])
    store.put('execution_pause', {'state': 'paused'}, 'execution-pause:' + legacy['id'])
    from devtools.operations_debug_history import clear_history
    assert clear_history(store)['cleared'] == 0
    with store.connection() as db:
        assert not db.execute('SELECT 1 FROM objects WHERE id=?', ('debug-history-hidden:' + legacy['id'],)).fetchone()


def test_clear_endpoint_requires_development_flag(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text('development:\n  operations_debug: false\n')
    app = FastAPI()
    app.include_router(debug.router)
    assert TestClient(app).post('/debug/history/clear').status_code == 404
