"""Reports keep readable summaries and immutable on-demand diagnostic details."""
from plugins.operations.report import daily_report
from plugins.operations.store import Store


def test_summary_bounds_findings_and_keeps_full_details_and_resume_snapshots(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store(tmp_path / 'reports.db')
    store.manual_run_id = 'debug:summary'
    run = store.start_run('2026-11-04', 'industry', 'debug:summary:industry', 0)
    store.event('usage', {'day': '2026-11-04', 'tokens': {'total_tokens': 123, 'prompt_tokens': 100, 'completion_tokens': 23}})
    store.finish_run(run, 'completed', '完成分析')
    findings = [{'title': f'结论{i}', 'text': '详细依据' * 100, 'scope': '当前资料', 'counter': '反向证据', 'unknowns': '仍需确认'} for i in range(152)]
    store.put('brief', {'day': '2026-11-04', 'debug_id': store.manual_run_id, 'result': {'analysis_context': {'findings': findings}, 'topics': []}})
    store.report_phase = 'paused'
    paused = daily_report(store, '2026-11-04')
    store.report_phase = 'completed'
    report = daily_report(store, '2026-11-04')
    assert report['id'] != paused['id']
    assert len(report['markdown']) < 12000
    assert '行业分析' in report['markdown'] and '123' in report['markdown']
    assert '结论4' in report['markdown'] and '结论5' not in report['markdown']
    saved = store.objects('report_detail')[0]
    assert '结论151' in saved['markdown']
    store.resume_attempt = 1
    resumed = daily_report(store, '2026-11-04')
    assert resumed['id'] != report['id']
    assert next(row for row in store.objects('report') if row['id'] == report['id'])['markdown'] == report['markdown']


def test_report_details_private_scope_and_list_does_not_expand_details(tmp_path, monkeypatch):
    from starlette.testclient import TestClient
    from hermes_cli import web_server
    from plugins.operations.workspaces import Workspaces
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text('{}')
    directory = Workspaces()
    first = directory.create('日报甲')
    other = directory.create('日报乙')
    store = directory.store(first['business_id'], first['topic_id'])
    record = daily_report(store, '2026-11-04')
    path = '/api/plugins/operations/reports/' + record['id'] + '/details'
    with TestClient(web_server.app) as client:
        assert client.get(path, params=first).status_code in (401, 403)
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        response = client.get(path, params=first)
        assert response.status_code == 200 and response.json()['markdown'].startswith('# 2026-11-04')
        assert client.get(path, params=other).status_code == 404
        rows = client.get('/api/plugins/operations/library/reports', params=first).json()['report']
        assert rows[0]['details_id'] == record['details_id']
        assert 'details' not in rows[0] and 'full_markdown' not in rows[0]


def test_summary_counts_all_provider_attempts_once_and_retains_unknown_usage(tmp_path, monkeypatch):
    from copy import deepcopy
    from types import SimpleNamespace
    import pytest
    from agent import token_ledger
    from plugins.operations import model
    from plugins.operations.model_errors import ModelServiceUnavailable
    from plugins.operations.policy import DEFAULT, local_day
    from plugins.operations.run_scope import ReportScope
    from plugins.operations.report_summary import consumption

    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='用量汇总', goal='累计所有实际尝试')
    policy['modules']['industry'] = True
    store.configure(policy, 0)
    store.debug_id = store.manual_run_id = 'debug:attempts'
    day = local_day(policy)
    store.start_run(day, 'industry', 'debug:attempts:industry', 1)

    def complete(**kwargs):
        for tokens in (7, 11):
            token_ledger.Attempt().finish(normalized={'total_tokens': tokens})
        return SimpleNamespace(usage={'total_tokens': 11}, choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))])
    monkeypatch.setattr('agent.auxiliary_client.call_llm', complete)
    model.generate(store, policy, day, '模拟多个尝试', {})

    def incomplete(**kwargs):
        token_ledger.Attempt().finish(normalized={'total_tokens': 5})
        token_ledger.Attempt().finish(error=TimeoutError('提供方未返回用量'))
        raise TimeoutError('中断')
    monkeypatch.setattr('agent.auxiliary_client.call_llm', incomplete)
    with pytest.raises(ModelServiceUnavailable):
        model.generate(store, policy, day, '模拟缺失回执', {})
    store.event('usage', {'day': day, 'tokens': {'total_tokens': 3}})  # Pre-budget legacy receipt.
    result = '\n'.join(consumption(ReportScope(store, day)))
    assert '已知 Token 合计：26' in result
    assert '行业分析：调用 3 次，已知 Token 26，另有 1 次用量待核对' in result
