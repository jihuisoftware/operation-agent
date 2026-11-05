"""Drill-down preserves task/batch ownership and complete cursor-based evidence."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from devtools import operations_debug as debug, operations_task_details as details
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.store import Store


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text('development:\n  operations_debug: true\n')
    store = debug.DebugStore('debug:trace')
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='调试证据', goal='核对执行过程')
    policy['modules'].update(comments=True, topics=True)
    store.configure(policy, 0)
    store.manual_run_id = 'debug:trace'
    data = debug.new_record('debug:trace', 'pipeline', '两个互动步骤', 1, local_day(policy))
    data.update(state='completed', steps=[{'id': key, 'title': key, 'state': 'completed', 'detail': key} for key in ['comment', 'reply']])
    store.put('debug_run', data, data['id'])
    for task in ['comment', 'reply']:
        store.debug_step = task
        run = store.start_run(data['day'], 'comments', data['id'] + ':' + task, 1)
        store.put('model_trace', {'state': 'completed', 'input': {'purpose': task}, 'result': {'text': task}}, 'trace:' + task)
        for index in range(205):
            store.event('progress', {'detail': task + str(index)})
        store.finish_run(run, 'completed', task)
    return store, data


def test_task_pages_do_not_mix_sibling_steps_and_export_all_paginated_events(environment):
    store, data = environment
    first = details.view(store, data['id'], 'comment')
    assert first['more'] and len(first['events']) == 200
    second = details.view(store, data['id'], 'comment', first['cursor'])
    assert not second['more']
    full = details.view(store, data['id'], 'comment', full=True)
    assert [row['id'] for row in full['events']] == [row['id'] for row in first['events'] + second['events']]
    assert all(row['data']['step_id'] == 'comment' for row in full['events'])
    assert [row['id'] for row in first['artifacts']] == ['trace:comment']
    assert 'data' not in first['artifacts'][0]
    assert details.artifact(store, data['id'], 'comment', 'trace:comment')['data']['input']['purpose'] == 'comment'
    with pytest.raises(HTTPException, match='不属于'):
        details.artifact(store, data['id'], 'comment', 'trace:reply')
    with pytest.raises(HTTPException, match='未执行'):
        details.view(store, data['id'], 'publish')
    assert len(details.history(store, 'comment')['runs']) == 1
    assert not details.history(store, 'publish')['runs']


def test_human_notes_are_idempotent_and_do_not_approve_or_change_execution(environment):
    store, data = environment
    body = {'text': '已经对照网页检查，输入框未出现', 'request_id': 'note-one'}
    saved = details.note(store, data['id'], 'comment', body)
    assert details.note(store, data['id'], 'comment', body) == saved
    with pytest.raises(HTTPException, match='不能修改'):
        details.note(store, data['id'], 'comment', {**body, 'text': '不同结论'})
    assert details.view(store, data['id'], 'comment')['notes'] == [saved]
    assert details.view(store, data['id'], 'reply')['notes'] == []
    assert debug.record(store, data['id'])['state'] == 'completed'
    assert not store.snapshot()['actions']


def test_model_snapshots_are_debug_only_redacted_and_keep_original_provider_input(environment, monkeypatch):
    from plugins.operations import model
    from plugins.operations.model_errors import ModelServiceUnavailable
    store, data = environment
    store.debug_step = 'comment'
    store.start_run(data['day'], 'comments', data['id'] + ':comment:resume:1', 1)
    seen = []
    def provider(**kwargs):
        seen.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))], usage=None)
    monkeypatch.setattr('agent.auxiliary_client.call_llm', provider)
    assert model.generate(store, store.policy()[1], data['day'], '检查结构', {'api_key': 'fixture-secret', 'sources': ['依据']}) == {'ok': True}
    assert json.loads(seen[0]['messages'][1]['content'])['api_key'] == 'fixture-secret'
    rows = [row for row in store.objects('model_trace') if row.get('budget_id')]
    assert len(rows) == 1 and rows[0]['input']['api_key'] == '[已隐藏]'
    assert rows[0]['raw_response'] == '{"ok":true}' and rows[0]['state'] == 'completed'
    normal = Store(store.path, workspace=store.workspace, scope=store.scope)
    model.generate(normal, normal.policy()[1], data['day'], '普通请求', {})
    assert len(store.objects('model_trace')) == 3
    def fail(**_):
        raise TimeoutError('模拟等待超时')
    monkeypatch.setattr('agent.auxiliary_client.call_llm', fail)
    with pytest.raises(ModelServiceUnavailable):
        model.generate(store, store.policy()[1], data['day'], '失败请求', {})
    failed = next(row for row in store.objects('model_trace') if row.get('state') == 'failed')
    assert failed['ended'] and '超时' in failed['error']


def test_task_http_requires_authentication_scope_and_debug_flag(environment, monkeypatch):
    from starlette.testclient import TestClient
    from hermes_cli import web_server
    store, data = environment
    scope = {'business_id': store.scope['business_id'], 'topic_id': store.scope['id']}
    path = f"/api/plugins/operations/debug/{data['id']}/tasks/comment"
    with TestClient(web_server.app) as client:
        assert client.get(path, params=scope).status_code in (401, 403)
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        assert client.get(path, params=scope).status_code == 200
        assert client.get(path, params={**scope, 'topic_id': 'foreign'}).status_code == 404
        with monkeypatch.context() as disabled:
            disabled.setattr(debug, 'load_config_readonly', dict)
            assert client.get(path, params=scope).status_code == 404
