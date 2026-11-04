"""Failed model checks preserve drafts; abandoned budgets become reconcilable."""
from copy import deepcopy
import pytest
from plugins.operations import content, model
from plugins.operations.model_budget_settings import read, save
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.store import Store
from plugins.operations.workspaces import Workspaces
from tests.plugins.operations_support import prepare_materials


@pytest.mark.parametrize('change_policy', [False, True])
def test_provider_failure_preserves_draft_and_retry_only_checks(tmp_path, monkeypatch, change_policy):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store(tmp_path / 'review.db')
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='检查', goal='测试')
    policy['modules'].update(organize=True, content=True, topics=False, industry=False, analytics=False)
    store.configure(policy, 0)
    day = local_day(policy)
    store.put('source', {'day': day, 'scope_topic': policy['topic'], 'title': '来源', 'text': '真实来源正文', 'url': 'https://example.org/a', 'state': 'read'}, 'source')
    prepare_materials(store, policy, day, monkeypatch)
    generated = []
    def provider(*args):
        if 'content' in args[-1]:
            raise TimeoutError('质检服务超时')
        generated.append(True)
        return {'title': '已写完的草稿', 'body': '根据来源整理的正文', 'asset_ids': [], 'source_ids': ['source']}
    monkeypatch.setattr(content, 'generate', provider)
    with pytest.raises(TimeoutError):
        content.produce_content(store, policy, day, 1)
    drafts = store.objects('content')
    assert len(drafts) == 1 and not drafts[0]['ready']
    if change_policy:
        policy['style'] = '新的写作风格'
        store.configure(policy, 1)
    def recovered(*args):
        return {'pass': True, 'reason': '检查通过'} if 'content' in args[-1] else provider(*args)
    monkeypatch.setattr(content, 'generate', recovered)
    result = content.produce_content(store, policy, day, store.policy()[0])
    assert (result['content_id'] == drafts[0]['id']) is (not change_policy)
    assert len(generated) == (2 if change_policy else 1)
    assert len(store.objects('content')) == (2 if change_policy else 1)
    saved = next(row for row in store.objects('content') if row['id'] == result['content_id'])
    assert saved['quality']['pass'] is True


def test_legacy_interrupted_budget_becomes_unknown_after_reopen(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    directory = Workspaces()
    store = directory.store()
    version, policy = store.policy()
    policy.update(enabled=True, topic='预算检查', goal='测试')
    policy['modules']['content'] = True
    store.configure(policy, version)
    current = read(store)
    save(store, {'version': current['version'], 'config': {'mode': 'tokens', 'calls': 200, 'tokens': 100000}})
    day = local_day(policy)
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute("INSERT INTO directory.model_budget_usage VALUES (?,?,?,?,?,0,0)", ('legacy-orphan', store.scope['id'], day, day, 'pending'))
    reopened = directory.store(store.scope['business_id'], store.scope['id'])
    monkeypatch.setattr('agent.auxiliary_client.call_llm', lambda **kw: pytest.fail('Should be blocked before provider'))
    with pytest.raises(ValueError, match='未确认'):
        model.generate(reopened, reopened.policy()[1], day, '测试', {})
    assert read(reopened)['usage']['pending'] == 0
    assert read(reopened)['usage']['unknown'] == 1


@pytest.mark.parametrize('has_receipt', [True, False])
def test_dead_process_reservation_recovers_receipt_or_requires_reconciliation(tmp_path, monkeypatch, has_receipt):
    import os
    import subprocess
    import sys
    from types import SimpleNamespace

    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Workspaces().store()
    version, policy = store.policy()
    policy.update(enabled=True, topic='中断恢复', goal='测试', model_budget_mode='tokens', model_tokens=100)
    policy['modules']['content'] = True
    store.configure(policy, version)
    script = '''
import os
from agent import auxiliary_client, token_ledger
from plugins.operations import model
from plugins.operations.store import Store
from plugins.operations.policy import local_day
store = Store()
def provider(**kwargs):
    attempt = token_ledger.Attempt()
    if os.environ['REVIEW_HAS_RECEIPT'] == '1':
        attempt.finish(normalized={'total_tokens': 6})
    os._exit(0)
auxiliary_client.call_llm = provider
policy = store.policy()[1]
model.generate(store, policy, local_day(policy), '隔离模拟', {})
'''
    result = subprocess.run([sys.executable, '-c', script], env={**os.environ, 'REVIEW_HAS_RECEIPT': str(int(has_receipt))},
                            capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    reopened = Workspaces().store()
    usage = read(reopened)['usage']
    assert usage['pending'] == 0
    assert usage['tokens'] == (6 if has_receipt else 0)
    assert usage['unknown'] == (0 if has_receipt else 1)
    monkeypatch.setattr('agent.auxiliary_client.call_llm', lambda **kw: SimpleNamespace(
        usage={'total_tokens': 4}, choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))]))
    if has_receipt:
        assert model.generate(reopened, policy, local_day(policy), '恢复后调用', {}) == {}
        assert read(reopened)['usage']['tokens'] == 10
    else:
        with pytest.raises(ValueError, match='未确认'):
            model.generate(reopened, policy, local_day(policy), '恢复后调用', {})
