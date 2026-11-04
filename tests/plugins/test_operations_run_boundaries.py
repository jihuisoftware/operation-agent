"""Durable resumption, account ownership and per-run reporting/budget contracts."""
from copy import deepcopy
from types import SimpleNamespace
import time

import pytest

from plugins.operations import analytics, industry, login_status, model
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.report import daily_report
from plugins.operations.store import Store
from plugins.operations.workspaces import Workspaces
from tests.plugins.operations_support import prepare_materials


def configured(tmp_path, calls=10):
    store = Store(tmp_path / 'operations.db')
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='开发实践', goal='分享有依据的经验', model_calls=calls)
    policy['modules'].update(research=True, organize=True, analytics=True, industry=True)
    store.configure(policy, 0)
    return store, policy, local_day(policy)


def test_industry_resumes_successful_batches_after_restart(tmp_path, monkeypatch):
    store, policy, day = configured(tmp_path, calls=50)
    for index in range(45):
        store.put('source', {'day': day, 'scope_topic': policy['topic'], 'title': str(index),
                            'url': f'https://example.org/{index}', 'text': f'资料{index}', 'state': 'read'}, str(index))
    prepare_materials(store, policy, day, monkeypatch)
    analytics.analyze(store, policy, day, 1)
    assert len(store.objects('analytics_report')[0]['evidence']) == 45
    attempts = []

    def generate(*args):
        ids = {row['id'] for row in args[-1]['evidence']}
        attempts.append(ids)
        if len(attempts) == 2:
            raise RuntimeError('模拟进程中断')
        return {'findings': []}

    monkeypatch.setattr(industry, 'generate', generate)
    with pytest.raises(RuntimeError, match='模拟进程中断'):
        industry.analyze(store, policy, day, 1)
    reopened = Store(store.path)
    industry.analyze(reopened, policy, day, 1)
    report = reopened.objects('industry_report')[0]
    assert report['pending'] == 0
    assert report['model_calls'] == 2
    assert all(not attempts[0] & ids for ids in attempts[2:])
    assert len(report['covered_ids']) == 45
    industry.analyze(reopened, policy, day, 1)
    assert len(attempts) == 4


def test_industry_retries_failed_batch_and_invalidates_changed_scope(tmp_path, monkeypatch):
    from plugins.operations import analysis_config
    from tests.plugins.operations_support import industry_response
    store, policy, day = configured(tmp_path, calls=50)
    for index in range(25):
        store.put('source', {'day': day, 'scope_topic': policy['topic'], 'title': str(index),
                            'url': f'https://example.org/{index}', 'text': f'资料{index}', 'state': 'read'}, str(index))
    prepare_materials(store, policy, day, monkeypatch)
    analytics.analyze(store, policy, day, 1)
    attempts = []

    def generate(*args):
        attempts.append(args[-1])
        if len(attempts) == 1:
            raise TimeoutError('首次批次超时')
        return industry_response(args[-1])

    monkeypatch.setattr(industry, 'generate', generate)
    industry.analyze(store, policy, day, 1)
    assert store.objects('industry_report')[0]['pending'] == 20
    # A single remaining call must retry the failed batch and retain the later checkpoint.
    store.run_options = {'model_calls': 1}
    industry.analyze(store, policy, day, 1)
    report = store.objects('industry_report')[0]
    assert report['pending'] == 0 and report['model_calls'] == 1
    assert attempts[0] == attempts[2]
    assert len(report['findings']) == 2
    store.run_options = None
    analysis_config.configure(store, {'version': 0, 'config': {'region': '华东'}})
    analytics.analyze(store, policy, day, 1)
    industry.analyze(store, policy, day, 1)
    assert len(attempts) == 5 and attempts[-1]['region'] == '华东'


def test_relinked_account_never_inherits_topic_login_evidence(tmp_path):
    from plugins.operations.workspace_execution import link_account
    directory = Workspaces(tmp_path)
    a, b = directory.create('业务 A'), directory.create('业务 B')
    store = directory.store(a['business_id'], a['topic_id'])
    other = directory.store(b['business_id'], b['topic_id'])
    original_account = store.scope['account']
    with store.connection() as db:
        db.execute('INSERT INTO workers VALUES (?,?)', ('desktop', time.time()))
    login_status.observe(store, {'platform': 'xiaohongshu', 'worker': 'desktop', 'state': 'logged_in', 'account_id': 'account-a'})
    link_account(directory, a['business_id'], other.scope['account'])
    row = login_status.catalog(store)['platforms'][0]
    assert row['state'] == 'unchecked'
    assert row['account_id'] == '' and row['confirmed_at'] is None
    link_account(directory, a['business_id'], original_account)
    assert login_status.catalog(store)['platforms'][0]['account_id'] == 'account-a'


def record_batch(store, day, batch, label):
    from plugins.operations.collection_ledger import save
    store.manual_run_id = batch
    run = store.start_run(day, 'research', batch + ':research', 1)
    save(store, 'source', batch + ':source', {'day': day, 'title': label + '来源',
                                            'url': 'https://example.org/' + batch, 'text': '原始资料', 'state': 'read'})
    store.put('task', {'day': day, 'text': label + '任务'})
    store.put('brief', {'day': day, 'result': {'note': label + '结论'}})
    store.put('inbox', {'day': day, 'kind': 'dm', 'state': 'needs_review', 'reason': label + '私信'})
    store.put('metric', {'day': day, 'name': label + '指标', 'value': 1})
    store.event('analysis_fallback', {'day': day, 'reason': label + '降级'})
    store.event('pipeline_error', {'error': label + '错误'})
    store.finish_run(run, 'completed', label + '步骤')
    return run


def test_debug_report_scopes_all_artifacts_and_counts_failed_calls(tmp_path):
    store, _, day = configured(tmp_path)
    record_batch(store, day, 'debug:batchX1', '其他')
    store.put('source', {'day': day, 'title': '同日历史来源', 'url': 'https://example.org/history', 'state': 'read'}, 'old')
    current = record_batch(store, day, 'debug:batch_1', '当前')
    store.put('content', {'day': day, 'source_ids': ['old']})
    # model_call historically bypassed DebugStore.event and carried only run_id.
    with store.connection() as db:
        for _ in range(2):
            db.execute("INSERT INTO events(at,kind,data) VALUES ('now','model_call',json_object('day',?,'run_id',?))", (day, current))
    store.event('usage', {'day': day, 'run_id': current, 'tokens': {'total_tokens': 12}})
    snapshot = daily_report(store, day)
    report = snapshot['markdown']
    full = next(row['markdown'] for row in store.objects('report_detail') if row['id'] == snapshot['details_id'])
    for value in (report, full):
        assert not any('其他' + suffix in value for suffix in ('来源', '任务', '结论', '私信', '指标', '降级', '步骤', '错误'))
    assert all('当前' + suffix in full for suffix in ('来源', '任务', '结论', '私信', '指标', '降级', '步骤', '错误'))
    assert all('当前' + suffix in report for suffix in ('来源', '步骤', '错误'))
    assert '模型调用 2 次' in report
    assert '历史资料复用 1 条' in report
    assert not any(row['id'] == f'review:{day}' for row in store.objects('review'))
    store.manual_run_id = None
    assert '其他任务' in daily_report(store, day)['markdown']
    store.manual_run_id = 'debug:batch_1'
    store.put('brief', {'day': day, 'result': {'note': '后续追加的结论'}})
    assert daily_report(store, day)['markdown'] == report
    assert next(row['markdown'] for row in store.objects('report_detail') if row['id'] == snapshot['details_id']) == full


def response():
    return SimpleNamespace(usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))])


def test_quick_budget_cannot_raise_daily_limit(tmp_path, monkeypatch):
    store, policy, day = configured(tmp_path, calls=2)
    store.manual_run_id = 'debug:budget'
    store.run_options = {'quick': True, 'model_calls': 12}
    monkeypatch.setattr('agent.auxiliary_client.call_llm', lambda **kwargs: response())
    for _ in range(2):
        model.generate(store, policy, day, '测试', {})
    with pytest.raises(ValueError, match='额度'):
        model.generate(store, policy, day, '测试', {})


def test_quick_budget_is_shared_by_steps_but_not_previous_batches(tmp_path, monkeypatch):
    store, policy, day = configured(tmp_path, calls=5)
    store.run_options = {'quick': True, 'model_calls': 2}
    monkeypatch.setattr('agent.auxiliary_client.call_llm', lambda **kwargs: response())
    store.manual_run_id = 'debug:previous'
    for _ in range(2):
        model.generate(store, policy, day, '测试', {})
    store.manual_run_id = 'debug:current'
    run = store.start_run(day, 'research', 'debug:current:research', 1)
    monkeypatch.setattr('agent.auxiliary_client.call_llm', lambda **kwargs: (_ for _ in ()).throw(TimeoutError('提供方超时')))
    from plugins.operations.model_errors import ModelServiceUnavailable
    with pytest.raises(ModelServiceUnavailable) as failure:
        model.generate(store, policy, day, '测试', {})
    assert isinstance(failure.value.__cause__, TimeoutError)
    store.finish_run(run, 'failed', '提供方超时')
    store.start_run(day, 'industry', 'debug:current:industry', 1)
    monkeypatch.setattr('agent.auxiliary_client.call_llm', lambda **kwargs: response())
    model.generate(store, policy, day, '测试', {})
    with pytest.raises(ValueError, match='额度'):
        model.generate(store, policy, day, '测试', {})

    store.finish_run(store.current_run_id, 'completed', '完成本轮')
    store.manual_run_id = 'debug:next'
    model.generate(store, policy, day, '测试', {})
    with pytest.raises(ValueError, match='额度'):
        model.generate(store, policy, day, '测试', {})
