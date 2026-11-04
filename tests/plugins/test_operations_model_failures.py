"""Exhausted provider retries preserve partial work without another retry layer."""
from copy import deepcopy
import json
from types import SimpleNamespace

import httpx
from openai import BadRequestError, InternalServerError
import pytest

from plugins.operations import analytics, industry, model, organization
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.store import Store
from tests.plugins.operations_support import organized_response


def busy():
    return InternalServerError('Service is too busy', response=httpx.Response(503, request=httpx.Request('POST', 'https://example.org/chat')), body={'error': {'type': 'service_unavailable_error'}})


def test_service_failure_retains_partial_organization_and_analysis(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='模型失败恢复', goal='保留已完成资料')
    policy['modules'].update(research=True, organize=True, analytics=True, industry=True)
    store.configure(policy, 0)
    day = local_day(policy)
    for index in range(10):
        store.put('source', {'day': day, 'scope_topic': policy['topic'], 'title': str(index), 'text': f'内容 {index}', 'url': f'https://example.org/{index}'}, str(index))
    calls = []

    def provider(**kwargs):
        data = json.loads(kwargs['messages'][-1]['content'])
        calls.append(data)
        if len(calls) > 1:
            raise busy()
        result = organized_response(data)
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(result)))])

    monkeypatch.setattr('agent.auxiliary_client.call_llm', provider)
    result = organization.organize(store, policy, day, 1)
    assert result['added'] == result['usable'] == 4 and result['pending'] == 6
    assert '503' in result['detail'] and '繁忙' in result['detail']
    assert len(calls) == 2
    analytics.analyze(store, policy, day, 1)
    outcome = industry.analyze(store, policy, day, 1)
    assert outcome['state'] == 'needs_attention'
    report = store.objects('industry_report')[0]
    assert report['pending'] and '503' in str(report['errors'])
    assert len(calls) == 3
    seen = []

    def recovered(**kwargs):
        data = json.loads(kwargs['messages'][-1]['content'])
        seen.extend(row['id'] for row in data['sources'])
        return SimpleNamespace(usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(organized_response(data))))])

    monkeypatch.setattr('agent.auxiliary_client.call_llm', recovered)
    resumed = organization.organize(store, policy, day, 1)
    assert resumed['pending'] == 0 and resumed['added'] == 6
    assert len(seen) == 6


def test_invalid_request_is_not_disguised_as_temporary_service_failure(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='错误分类', goal='保留错误')
    policy['modules']['content'] = True
    store.configure(policy, 0)
    error = BadRequestError('invalid parameters', response=httpx.Response(400, request=httpx.Request('POST', 'https://example.org/chat')), body={})

    def invalid(**kwargs):
        raise error

    monkeypatch.setattr('agent.auxiliary_client.call_llm', invalid)
    with pytest.raises(BadRequestError):
        model.generate(store, policy, local_day(policy), '生成', {})
