"""Ordinary generation retains physical requests, retries and scoped HTTP details."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from openai.types.chat import ChatCompletion
from starlette.testclient import TestClient

from agent.auxiliary_hooks import run_with_aux_hooks
from agent.token_ledger import connection
from plugins.operations import model
from plugins.operations.model_call_details import detail
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.token_usage import UsageQuery
from plugins.operations.workspaces import Workspaces


def response(text='{"title":"完成"}', usage=None):
    return ChatCompletion(id='answer', created=1, model='served-model', object='chat.completion',
                          choices=[{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': text}}],
                          usage=usage or {'prompt_tokens': 30, 'completion_tokens': 7, 'total_tokens': 37,
                                          'prompt_tokens_details': {'cached_tokens': 10}, 'cost': 0.012, 'currency': 'USD'})


def physical(kwargs, operation, retry=0):
    return run_with_aux_hooks(operation, aux_task='content', metadata={'retry_count': retry},
                              client=SimpleNamespace(base_url='https://example.invalid/v1'), kwargs=kwargs,
                              provider='test-provider', model='requested-model', api_mode='chat_completions')


@pytest.fixture
def ordinary(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text('{}')
    directory = Workspaces()
    scope = directory.create('业务')
    store = directory.store(scope['business_id'], scope['topic_id'])
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='图文测试', goal='完整记录')
    policy['modules']['content'] = True
    store.configure(policy, 0)
    return directory, scope, store, policy


@pytest.mark.parametrize('with_images', [False, True])
def test_normal_generation_records_retries_and_private_details(ordinary, monkeypatch, tmp_path, with_images):
    directory, scope, store, policy = ordinary
    sent = []

    def provider(**kwargs):
        sent.append(deepcopy(kwargs))

        def failed():
            raise TimeoutError('暂时超时')

        with pytest.raises(TimeoutError):
            physical(kwargs, failed)
        return physical(kwargs, response, retry=1)

    monkeypatch.setattr('agent.auxiliary_client.call_llm', provider)
    images = [{'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,aW1hZ2U='}}] if with_images else []
    assert model.generate(store, policy, local_day(policy), '生成图文', {'text': '资料' * 10000, 'api_key': 'private-value'}, image_parts=images) == {'title': '完成'}
    with connection() as db:
        calls = [dict(row) for row in db.execute('SELECT * FROM token_usage_calls ORDER BY started')]
    assert len(calls) == 2
    assert calls[0]['state'] == 'failed' and calls[0]['total_tokens'] is None
    assert calls[1]['total_tokens'] == 37 and calls[1]['cache_read_tokens'] == 10
    saved = detail(UsageQuery(), calls[1]['id'])
    assert [row['id'] for row in saved['attempts']] == [row['id'] for row in calls]
    assert saved['detail']['request']['messages'][0] == sent[0]['messages'][0]
    sent_content = sent[0]['messages'][1]['content']
    stored_content = saved['detail']['request']['messages'][1]['content']
    sent_text = sent_content[0]['text'] if with_images else sent_content
    stored_text = stored_content[0]['text'] if with_images else stored_content
    assert 'private-value' in sent_text and 'private-value' not in stored_text
    assert json.loads(stored_text)['text'] == '资料' * 10000
    if with_images:
        assert sent_content[1] == images[0]
        assert stored_content[1]['image_url']['url']['media_type'] == 'image/png'
        assert 'aW1hZ2U=' not in json.dumps(stored_content)
    assert saved['detail']['raw_response'] == '{"title":"完成"}'
    assert saved['detail']['parsed_result'] == {'title': '完成'}
    assert saved['detail']['cost'] == {'amount': 0.012, 'currency': 'USD', 'source': 'provider_receipt'}
    assert detail(UsageQuery(), calls[0]['id'])['detail']['error'] == '暂时超时'
    foreign = directory.create('其他业务')
    from hermes_cli import web_server
    with TestClient(web_server.app) as client:
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        url = '/api/plugins/operations/usage/calls/' + calls[1]['id']
        result = client.get(url, params={'filter_topic': scope['topic_id']})
        assert result.status_code == 200, result.text
        assert result.json()['detail']['parsed_result'] == {'title': '完成'}
        assert client.get(url, params={'filter_topic': foreign['topic_id']}).status_code == 404
        assert client.get(url, params={'topic_id': foreign['topic_id']}).status_code == 404
        assert client.get(url, params={'profile': 'missing-profile'}).status_code != 200
        with connection() as db:
            db.execute('UPDATE token_usage_calls SET started=1,received=2')
        history_url = '/api/plugins/operations/usage/tasks/' + calls[1]['task_id'] + '/calls'
        assert client.get(history_url).json()['items'] == []
        history = client.get(history_url, params={'all_time': '1', 'topic_id': scope['topic_id']})
        assert len(history.json()['items']) == 2
        assert client.get(url).status_code == 200
    other = tmp_path / 'other-profile'
    other.mkdir()
    monkeypatch.setenv('HERMES_HOME', str(other))
    with pytest.raises(LookupError):
        detail(UsageQuery(), calls[1]['id'])


def test_parse_failure_retains_original_and_old_receipts_remain_readable(ordinary, monkeypatch):
    _, _, store, policy = ordinary
    monkeypatch.setattr('agent.auxiliary_client.call_llm',
                        lambda **kwargs: physical(kwargs, lambda: response('不是 JSON', {'prompt_tokens': 30, 'completion_tokens': 7, 'total_tokens': 37})))
    with pytest.raises(ValueError, match='JSON'):
        model.generate(store, policy, local_day(policy), '生成图文', {'text': '资料'})
    with connection() as db:
        identity = db.execute('SELECT id FROM token_usage_calls').fetchone()[0]
    saved = detail(UsageQuery(), identity)
    assert saved['detail']['raw_response'] == '不是 JSON'
    assert 'JSON' in saved['detail']['parse_error']
    assert saved['call']['total_tokens'] == 37
    assert saved['detail']['cost']['amount'] is None
    assert saved['detail']['cost']['source'] == 'unknown'
    # An unobserved request represents historical receipts or another caller.
    physical({'messages': []}, response)
    with connection() as db:
        legacy = db.execute('SELECT id FROM token_usage_calls WHERE id!=?', (identity,)).fetchone()[0]
    saved = detail(UsageQuery(), legacy)
    assert saved['detail'] is None and '无法补回' in saved['notice']


def test_detail_recording_failure_does_not_retry_paid_call(ordinary, monkeypatch):
    _, _, store, policy = ordinary
    attempts = []

    def broken(*args, **kwargs):
        raise OSError('记录存储不可用')

    def provider(**kwargs):
        attempts.append(kwargs)
        return physical(kwargs, response)

    monkeypatch.setattr('plugins.operations.model_call_details.record', broken)
    monkeypatch.setattr('agent.auxiliary_client.call_llm', provider)
    assert model.generate(store, policy, local_day(policy), '生成图文', {}) == {'title': '完成'}
    assert len(attempts) == 1
