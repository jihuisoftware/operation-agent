"""Time-window analytics and scoped private HTTP use the same durable receipts."""
from datetime import datetime, UTC
from types import SimpleNamespace
import csv
import io

import pytest
from starlette.testclient import TestClient
from agent import token_ledger as ledger
from plugins.operations.token_usage import UsageQuery, window
from plugins.operations.workspaces import Workspaces


def stamp(value):
    return datetime.fromisoformat(value).timestamp()


def record(directory, scope, when, *, identity='run', total=20, state='completed'):
    context = ledger.start_task(identity, business_id=scope['business_id'], topic_id=scope['topic_id'],
                                run_id=identity, stage='content', task_name='内容生产')
    with ledger.bind(context):
        call = ledger.Attempt(model='model', provider='provider', purpose='content')
        call.finish(SimpleNamespace(usage={'prompt_tokens': total, 'completion_tokens': 5}))
    if state != 'running':
        ledger.finish_task(context, state)
    with ledger.connection() as db:
        db.execute('UPDATE token_usage_calls SET started=?,received=? WHERE id=?', (when - 10, when, call.id))
    return call


@pytest.fixture
def directory(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text('{}')
    return Workspaces()


def test_windows_use_receipt_time_and_local_calendar_with_dst(directory):
    scope = directory.create('同名')
    end = stamp('2026-10-31T17:30:00+00:00')
    record(directory, scope, end - 1800, identity='recent')
    record(directory, scope, end - 4000, identity='earlier')
    record(directory, scope, end - 90000, identity='yesterday')
    assert UsageQuery(period='hour', until=end, tz='Asia/Shanghai').summary()['totals']['total_tokens'] == 25
    assert UsageQuery(period='day', until=end, tz='Asia/Shanghai').summary()['totals']['total_tokens'] == 50
    for period in ('week', 'month'):
        assert UsageQuery(period=period, until=end, tz='Asia/Shanghai').summary()['totals']['total_tokens'] == 75
    with ledger.connection() as db:
        db.execute('UPDATE token_usage_tasks SET started=0')
    assert UsageQuery(period='hour', until=end, tz='Asia/Shanghai').summary()['totals']['total_tokens'] == 25
    start, finish, _ = window('day', 'America/New_York', stamp('2026-03-09T03:59:59+00:00'))
    assert finish - start == 23 * 3600 - 1
    with pytest.raises(ValueError):
        window('day', 'bad-zone')


def test_same_names_scope_live_unknown_and_export_match(directory):
    one = directory.create('同名')
    two = directory.create('同名')
    now = datetime.now(UTC).timestamp()
    record(directory, one, now - 60, identity='one', state='running')
    record(directory, two, now - 60, identity='two')
    with ledger.bind(ledger.start_task('unknown', business_id=one['business_id'], topic_id=one['topic_id'])):
        missing = ledger.Attempt()
        missing.finish(SimpleNamespace(usage=None))
        ledger.Attempt()
    query = UsageQuery(selected={'business': one['business_id']})
    summary = query.summary()
    assert summary['totals']['total_tokens'] == 25
    assert summary['totals']['unknown'] == 1
    assert summary['totals']['running'] == 1
    assert UsageQuery(period='live').summary()['totals']['total_tokens'] == 25
    tasks = query.tasks()['items']
    assert sum(t['total_tokens'] for t in tasks) == summary['totals']['total_tokens']
    assert query.calls('two')['items'] == []
    exported = list(csv.DictReader(io.StringIO(''.join(query.export()).lstrip('\ufeff'))))
    assert sum(int(r['total_tokens'] or 0) for r in exported) == 25
    assert {r['business_id'] for r in exported} == {one['business_id']}
    with pytest.raises(ValueError):
        UsageQuery(selected={'business': one['business_id'], 'topic': two['topic_id']})


def test_call_cursor_and_profile_private_http(directory):
    scope = directory.create('业务')
    now = datetime.now(UTC).timestamp()
    call = record(directory, scope, now - 5)
    from hermes_cli import web_server
    with TestClient(web_server.app) as client:
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        base = '/api/plugins/operations/usage'
        params = {'period': 'day', 'tz': 'UTC', 'filter_business': scope['business_id']}
        summary = client.get(base + '/summary', params=params)
        assert summary.status_code == 200, summary.text
        assert summary.json()['totals']['total_tokens'] == 25
        tasks = client.get(base + '/tasks', params=params).json()['items']
        assert tasks[0]['run_id'] == 'run'
        assert client.get(base + '/tasks/run/calls', params=params).json()['items'][0]['id'] == call.id
        assert client.get(base + '/summary', params={**params, 'filter_topic': 'foreign'}).status_code == 400
        export = client.get(base + '/export', params={**params, 'transport': 'json'})
        assert 'total_tokens' in export.json()['csv']
        assert client.get(base + '/tasks', params={**params, 'cursor': 'invalid'}).status_code == 400


def test_pagination_and_archived_scope_preserve_totals(directory):
    scope = directory.create('业务')
    context = ledger.start_task('run', business_id=scope['business_id'], topic_id=scope['topic_id'])
    with ledger.bind(context):
        for _ in range(102):
            ledger.Attempt().finish(SimpleNamespace(usage={'prompt_tokens': 1, 'completion_tokens': 0}))
    query = UsageQuery()
    first = query.calls('run')
    second = query.calls('run', first['cursor'])
    assert len(first['items']) == 100 and len(second['items']) == 2
    assert not ({r['id'] for r in first['items']} & {r['id'] for r in second['items']})
    with directory.connection() as db:
        db.execute('UPDATE topics SET archived=1 WHERE id=?', (scope['topic_id'],))
    assert query.summary()['totals']['total_tokens'] == 102
