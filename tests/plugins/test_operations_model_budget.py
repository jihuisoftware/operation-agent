"""Editable model budgets persist usage, serialize token calls and exempt development debugging."""
from copy import deepcopy
from threading import Event
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from plugins.operations import model
from plugins.operations.model_budget_settings import read, save
from plugins.operations.policy import DEFAULT, local_day, validate_policy
from plugins.operations.store import Store
from plugins.operations.workspaces import Workspaces


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    directory = Workspaces()
    store = directory.store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='运营预算', goal='验证预算')
    policy['modules']['content'] = True
    store.configure(policy, 0)
    monkeypatch.setattr('agent.auxiliary_client.call_llm', lambda **kwargs: response(6))
    return store


def response(tokens=None):
    return SimpleNamespace(usage=None if tokens is None else {'total_tokens': tokens},
                          choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))])


def configure(store, **changes):
    version, policy = store.policy()
    policy.update(changes)
    store.configure(policy, version)
    return store.policy()[1]


def generate(store):
    policy = store.policy()[1]
    return model.generate(store, policy, local_day(policy), '测试模型预算', {})


def test_new_defaults_and_existing_limits_roundtrip(configured):
    assert configured.policy()[1]['model_calls'] == 200
    configure(configured, model_calls=17)
    assert Store(configured.path).policy()[1]['model_calls'] == 17
    with pytest.raises(ValueError, match='tokens'):
        validate_policy({**configured.policy()[1], 'model_tokens': -1})
    with pytest.raises(ValueError, match='预算方式'):
        validate_policy({**configured.policy()[1], 'model_budget_mode': 'unknown'})


def test_token_budget_uses_receipts_and_survives_mode_changes(configured):
    configure(configured, model_budget_mode='tokens', model_tokens=10, model_calls=0)
    assert generate(configured) == {}
    assert generate(configured) == {}
    with pytest.raises(ValueError, match='Token 预算'):
        generate(configured)
    assert read(configured)['usage']['tokens'] == 12
    configure(configured, model_budget_mode='calls', model_calls=3)
    generate(configured)
    with pytest.raises(ValueError, match='模型调用额度'):
        generate(configured)
    configure(configured, model_budget_mode='tokens')
    with pytest.raises(ValueError, match='Token 预算'):
        generate(configured)


def test_unknown_usage_is_not_free_and_debug_remains_exempt(configured, monkeypatch):
    from devtools.operations_debug import DebugStore
    configure(configured, model_budget_mode='tokens', model_tokens=100)
    monkeypatch.setattr('agent.auxiliary_client.call_llm', lambda **kwargs: response())
    generate(configured)
    with pytest.raises(ValueError, match='未确认'):
        generate(configured)
    debug = DebugStore('debug:token-test')
    assert generate(debug) == {}
    assert read(configured)['usage']['unknown'] == 1
    configure(configured, model_budget_mode='calls', model_calls=2)
    generate(configured)
    with pytest.raises(ValueError, match='模型调用额度'):
        generate(configured)


def test_shared_budget_cannot_be_reset_by_saving_one_topic(configured):
    current = read(configured)
    saved = save(configured, {'version': current['version'], 'config': {'mode': 'tokens', 'calls': 200, 'tokens': 10}})
    with pytest.raises(ValueError, match='已变更'):
        save(configured, {'version': current['version'], 'config': saved['config']})
    configure(configured, model_calls=300)
    assert read(configured)['config'] == saved['config']
    directory = configured.workspace
    other = directory.create('另一个主题', business=configured.scope['business_id'])
    sibling = directory.store(other['business_id'], other['topic_id'])
    configure(sibling, enabled=True, goal='其他主题', modules=configured.policy()[1]['modules'])
    generate(configured)
    generate(sibling)
    with pytest.raises(ValueError, match='全部主题共享每日 Token'):
        generate(configured)
    assert read(configured)['usage']['tokens'] == 12


def test_inflight_token_call_blocks_another_topic_until_receipt(configured, monkeypatch):
    current = read(configured)
    save(configured, {'version': current['version'], 'config': {'mode': 'tokens', 'calls': 200, 'tokens': 100}})
    directory = configured.workspace
    scope = directory.create('并发主题', business=configured.scope['business_id'])
    other = directory.store(scope['business_id'], scope['topic_id'])
    configure(other, enabled=True, goal='验证共享预算', modules=configured.policy()[1]['modules'])
    entered, release = Event(), Event()

    def provider(**kwargs):
        entered.set()
        assert release.wait(10)
        return response(6)

    monkeypatch.setattr('agent.auxiliary_client.call_llm', provider)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(generate, configured)
        try:
            assert entered.wait(10)
            with pytest.raises(ValueError, match='尚未返回'):
                generate(other)
        finally:
            release.set()
        assert pending.result(timeout=10) == {}
    monkeypatch.setattr('agent.auxiliary_client.call_llm', lambda **kwargs: response(6))
    assert generate(other) == {}


def test_existing_usage_is_imported_before_enabling_token_budget(configured):
    day = local_day(configured.policy()[1])
    configured.event('model_call', {'day': day, 'run_id': 'legacy'})
    configured.event('usage', {'day': day, 'run_id': 'legacy', 'tokens': {'prompt_tokens': 8, 'completion_tokens': 4}})
    with configured.connection() as db:
        db.execute('DELETE FROM directory.model_budget_imports')
    reopened = configured.workspace.store(configured.scope['business_id'], configured.scope['id'])
    configure(reopened, model_budget_mode='tokens', model_tokens=10)
    with pytest.raises(ValueError, match='Token 预算'):
        generate(reopened)
    assert read(reopened)['usage']['tokens'] == 12
    reopened_again = configured.workspace.store(configured.scope['business_id'], configured.scope['id'])
    assert read(reopened_again)['usage']['tokens'] == 12


def test_token_budget_counts_all_normalized_provider_attempts(configured, monkeypatch):
    from agent import token_ledger
    configure(configured, model_budget_mode='tokens', model_tokens=10)
    version, policy = configured.policy()
    configured.start_run(local_day(policy), 'content', 'provider-attempts', version)

    def provider(**kwargs):
        for _ in range(2):
            token_ledger.Attempt().finish(normalized={'total_tokens': 6, 'prompt_tokens': 4, 'output_tokens': 2})
        return response(6)

    monkeypatch.setattr('agent.auxiliary_client.call_llm', provider)
    generate(configured)
    assert read(configured)['usage']['tokens'] == 12
    with pytest.raises(ValueError, match='Token 预算'):
        generate(configured)
