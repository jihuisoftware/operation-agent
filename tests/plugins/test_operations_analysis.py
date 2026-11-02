"""Analysis/import contracts with real SQLite and temporary profile data."""
import base64
from copy import deepcopy
from datetime import date, timedelta
from io import BytesIO
from zipfile import ZipFile

import pytest

from plugins.operations import analytics, industry, business_store as business, analysis_config, analysis_views, analysis_runs
from plugins.operations.business_files import rows
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.store import Store
from tests.plugins.operations_support import prepare_materials


@pytest.fixture
def configured(tmp_path):
    store = Store(tmp_path / 'analysis.db')
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='收纳', goal='有依据的运营')
    policy['modules'].update(research=True, organize=True, analytics=True, industry=True, topics=True, content=True)
    store.configure(policy, 0)
    return store, policy, local_day(policy)


def import_csv(store, text, **extra):
    upload = business.upload(store, {'name': '业务.csv', 'data': base64.b64encode(text.encode()).decode()})
    body = {'upload_id': upload['upload_id'], 'sheet': 'CSV', 'template': 'sales',
            'mapping': {'day': '日期', 'key': '订单号', 'revenue': '销售额', 'quantity': '销量', 'note': '备注'},
            'date_format': '%Y-%m-%d', 'currency': 'CNY', 'definition': '支付金额不含运费', 'semantics': 'increment',
            'dedupe': True, 'model_mode': 'summary', 'detail_fields': [], 'public_metrics': [], **extra}
    headers = upload['headers']
    body['mapping'] = {k: v for k, v in body['mapping'].items() if v in headers}
    preview = business.preview(store, body)
    return body | {'preview_token': preview['preview_token']}, preview


def finding(data):
    return {'findings': [{'view': 'content', 'dimension': '需求', 'title': '关注具体使用需求', 'text': '样本提示可验证这一方向',
                         'evidence_ids': [data['evidence'][0]['id']], 'scope': '本次样本', 'counter': '未找到反向证据', 'unknowns': '不能外推全行业'}]}


def test_import_idempotency_invalid_rows_and_comparable_statistics(configured):
    store, policy, day = configured
    earlier = (date.fromisoformat(day) - timedelta(days=7)).isoformat()
    text = f'日期,订单号,销售额,销量\n{earlier},old,50,1\n{day},one,100,\n{day},one,100,\n{day},two,,2\n错误,bad,12,1\n'
    body, preview = import_csv(store, text)
    assert (preview['valid'], preview['invalid']) == (4, 1)
    with pytest.raises(ValueError, match='无效行'):
        business.confirm(store, body)
    receipt = business.confirm(store, body | {'exclude_invalid': True})
    assert (receipt['inserted'], receipt['duplicates'], receipt['invalid']) == (3, 1, 1)
    retry, _ = import_csv(store, text)
    assert business.confirm(Store(store.path), retry | {'exclude_invalid': True})['id'] == receipt['id']
    analytics.analyze(store, policy, day, 1)
    report = store.objects('analytics_report')[0]
    money = next(m for m in report['metrics'] if m['key'] == 'revenue')
    assert (money['value'], money['previous'], money['growth_percent'], money['missing']) == ('100', '50', '100', 1)
    assert report['datasets'][0]['batches'] == [receipt['id']]
    assert Store(store.path.parent / 'other.db').objects('analytics_report') == []


def test_four_templates_and_snapshots_preserve_missing_units(configured):
    store, policy, day = configured
    for template, metric in [('sales', 'revenue'), ('products', 'quantity'), ('leads', 'leads'), ('content', 'views')]:
        text = f'日期,指标\n{day},3\n'
        body, _ = import_csv(store, text, template=template, mapping={'day': '日期', metric: '指标'}, dedupe=False,
                             semantics='snapshot', currency='USD')
        business.confirm(store, body)
    analytics.analyze(store, policy, day, 1)
    metrics = store.objects('analytics_report')[0]['metrics']
    assert len(metrics) == 4 and all(m['value'] == '3' and m['growth_percent'] is None for m in metrics)
    assert next(m for m in metrics if m['key'] == 'revenue')['unit'] == 'USD'


def test_model_privacy_publication_permissions_and_revocation(configured, monkeypatch):
    store, policy, day = configured
    store.put('source', {'day': day, 'scope_topic': policy['topic'], 'title': '公开资料', 'url': 'https://example.org/a', 'text': '公开方法', 'state': 'read'}, 'source')
    prepare_materials(store, policy, day, monkeypatch)
    body, preview = import_csv(store, f'日期,订单号,销售额,备注\n{day},secret-order,100,联系 13812345678 a@example.org\n', model_mode='details', detail_fields=['note'])
    assert '13812345678' not in str(preview['model_sample']) and 'a@example.org' not in str(preview['model_sample'])
    receipt = business.confirm(store, body)
    calls = []
    monkeypatch.setattr(industry, 'generate', lambda *args: calls.append(args[-1]) or finding(args[-1]))
    analytics.analyze(store, policy, day, 1)
    industry.analyze(store, policy, day, 1)
    assert len(calls) == 2
    assert 'secret-order' not in str(calls) and '13812345678' not in str(calls)
    assert all('dataset:' not in e['id'] for e in calls[0]['evidence'])
    context = industry.production_context(store, policy, day)
    assert context['metrics'] == [] and all(f['visibility'] == 'public' for f in context['findings'])
    dataset = business.datasets(store)[0]
    change = {'version': dataset['version'], 'active': True, 'model_mode': 'summary', 'detail_fields': [], 'public_metrics': ['revenue']}
    preview = business.permission_preview(store, dataset['id'], change)
    business.update_dataset(store, dataset['id'], change | {'preview_token': preview['preview_token']})
    with pytest.raises(ValueError, match='权限已变化'):
        industry.check_public_context(store, {'analysis_context': context}, policy, day)
    analytics.analyze(store, policy, day, 1)
    assert industry.production_context(store, policy, day)['metrics'][0]['value'] == '100'
    assert receipt['id'] in store.objects('analytics_report')[0]['datasets'][0]['batches']


def test_full_coverage_more_than_forty_and_model_budget(configured, monkeypatch):
    store, policy, day = configured
    for i in range(45):
        store.put('source', {'day': day, 'scope_topic': policy['topic'], 'title': str(i), 'url': f'https://example.org/{i}', 'text': f'资料{i}', 'state': 'read'}, str(i))
    prepare_materials(store, policy, day, monkeypatch)
    policy['model_calls'] = 4  # Three downstream calls reserved, one analysis batch.
    store.configure(policy, 1)
    analytics.analyze(store, policy, day, 2)
    monkeypatch.setattr(industry, 'generate', lambda *args: finding(args[-1]))
    result = industry.analyze(store, policy, day, 2)
    report = store.objects('industry_report')[0]
    assert len(store.objects('analytics_report')[0]['evidence']) == 45
    assert len(report['covered_ids']) == 20 and report['pending'] == 25 and result['state'] == 'needs_attention'
    policy['model_calls'] = 50
    store.configure(policy, 2)
    industry.analyze(store, policy, day, 3)
    assert store.objects('industry_report')[0]['pending'] == 0


def test_manual_retry_cancel_and_scope_migration(configured, monkeypatch):
    store, policy, day = configured
    original = analytics.analyze
    def cancelled(store, policy, day, version):
        analysis_runs.cancel(store, store.current_run_id)
        return original(store, policy, day, version)
    monkeypatch.setattr(analytics, 'analyze', cancelled)
    first = analysis_runs.run(store, 'analytics', {'version': 1, 'request_id': 'cancel-one'})
    assert first['state'] == 'cancelled' and not store.objects('analytics_report')
    assert analysis_runs.run(store, 'analytics', {'version': 1, 'request_id': 'cancel-one'})['id'] == first['id']
    assert analysis_runs.logs(store, first['id'])['errors']
    monkeypatch.setattr(analytics, 'analyze', original)
    assert analysis_runs.run(store, 'analytics', {'version': 1, 'request_id': 'new'})['state'] == 'completed'
    analysis_config.configure(store, {'version': 0, 'config': {'period': '30'}})
    assert analytics.latest(store, 'analytics_report', policy, day) is None
    assert industry.production_context(store, policy, day) is None
    assert store.objects('analytics_report')


def xlsx(formula=False):
    output = BytesIO()
    with ZipFile(output, 'w') as book:
        book.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="数据" r:id="rId1"/></sheets></workbook>')
        book.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        value = '<f>SUM(1,2)</f>' if formula else '<v>3</v>'
        book.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c r="A1" t="inlineStr"><is><t>指标</t></is></c></row><row><c r="A2">' + value + '</c></row></sheetData></worksheet>')
    return output.getvalue()


def test_xlsx_formula_is_never_executed_and_limits_are_enforced(monkeypatch):
    from plugins.operations import business_files
    assert list(rows(xlsx(), 'data.xlsx', '数据'))[-1][1] == ['3']
    assert '缓存值' in list(rows(xlsx(True), 'data.xlsx', '数据'))[-1][1][0]
    monkeypatch.setattr(business_files, 'MAX_ROWS', 1)
    with pytest.raises(ValueError, match='10 万行'):
        list(rows(b'a\n1\n2\n', 'a.csv'))
    with pytest.raises(ValueError, match='20 MB'):
        list(rows(b'x' * (20 * 1024 * 1024 + 1), 'a.csv'))


def test_import_permissions_require_preview_and_reject_identity_fields(configured):
    store, _, day = configured
    body, _ = import_csv(store, f'日期,手机号,销售额\n{day},13812345678,1\n')
    bad = body | {'mapping': {**body['mapping'], 'note': '手机号'}, 'model_mode': 'details', 'detail_fields': ['note']}
    with pytest.raises(ValueError, match='身份字段'):
        business.preview(store, bad)
    with pytest.raises(ValueError, match='预览已变化'):
        business.confirm(store, body | {'public_metrics': ['revenue']})


def test_private_api_and_report_export(configured, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from plugins.operations.dashboard import analysis_api
    store, _policy, _day = configured
    monkeypatch.setattr(analysis_api, 'Store', lambda: store)
    app = FastAPI(); app.include_router(analysis_api.router)
    with TestClient(app) as client:
        assert client.get('/analysis').json()['settings']['config']['period'] == '7'
        response = client.post('/analysis/run/analytics', json={'version': 1, 'request_id': 'http'})
        assert response.status_code == 200 and response.json()['state'] == 'completed'
        report = client.get('/analysis').json()['reports'][0]
        assert client.get('/analysis/reports/' + report['id'] + '/export?format=csv').status_code == 200
        assert client.post('/analysis/settings', json={'version': 0, 'config': {'period': '30'}}).status_code == 200
        assert client.get('/analysis/reports/' + report['id'] + '/export?public=true').status_code == 400


def test_permission_change_during_model_call_discards_result(configured, monkeypatch):
    store, policy, day = configured
    body, _ = import_csv(store, f'日期,销售额\n{day},200\n', dedupe=False, public_metrics=['revenue'])
    business.confirm(store, body)
    analytics.analyze(store, policy, day, 1)
    def changed(*args):
        dataset = business.datasets(store)[0]
        options = {'version': dataset['version'], 'active': True, 'model_mode': 'local'}
        preview = business.permission_preview(store, dataset['id'], options)
        business.update_dataset(store, dataset['id'], options | {'preview_token': preview['preview_token']})
        return finding(args[-1])
    monkeypatch.setattr(industry, 'generate', changed)
    with pytest.raises(ValueError, match='权限发生变化'):
        industry.analyze(store, policy, day, 1)
    assert not store.objects('industry_report')


def test_replacement_retains_referenced_batches(configured):
    store, policy, day = configured
    body, _ = import_csv(store, f'日期,订单号,销售额\n{day},one,1\n')
    first = business.confirm(store, body)
    dataset = business.datasets(store)[0]
    new, _ = import_csv(store, f'日期,订单号,销售额\n{day},one,2\n', dataset_id=dataset['id'], dataset_version=dataset['version'], replace=True)
    second = business.confirm(store, new)
    analytics.analyze(store, policy, day, 1)
    assert store.objects('analytics_report')[0]['metrics'][0]['value'] == '2'
    assert business.datasets(store)[0]['batches'] == [second['id']]
    with store.connection() as db:
        assert db.execute('SELECT 1 FROM business_batches WHERE id=?', (first['id'],)).fetchone()


def test_analysis_reuses_historical_evidence_for_next_topic(configured, monkeypatch):
    from plugins.operations import topics
    store, policy, day = configured
    yesterday = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    store.put('source', {'day': yesterday, 'scope_topic': policy['topic'], 'title': '昨日资料', 'url': 'https://example.org/history', 'text': '历史方法资料', 'state': 'read'}, 'history')
    prepare_materials(store, policy, yesterday, monkeypatch)
    analytics.analyze(store, policy, day, 1)
    monkeypatch.setattr(industry, 'generate', lambda *args: finding(args[-1]))
    industry.analyze(store, policy, day, 1)
    def propose(*args):
        assert args[-1]['analysis']['findings'] and args[-1]['sources'][0]['id'] == 'history'
        return {'topics': [{'title': '有历史依据的选题', 'source_ids': ['history']}]}
    monkeypatch.setattr(topics, 'generate', propose)
    topics.generate_topics(store, policy, day, 1)
    assert topics.catalog(store)['candidates'][0]['source_ids'] == ['history']


def test_revoked_public_data_blocks_already_queued_browser_submission(configured):
    from plugins.operations.browser_evidence import record_step
    store, policy, day = configured
    policy['modules']['publish'] = True
    store.configure(policy, 1)
    body, _ = import_csv(store, f'日期,销售额\n{day},123\n', dedupe=False, public_metrics=['revenue'])
    business.confirm(store, body)
    analytics.analyze(store, policy, day, 2)
    context = industry.production_context(store, policy, day)
    action = {'kind': 'publish', 'account_id': 'simulated', 'target': 'approved', 'content': {'title': '统计', 'body': '说明', 'analysis_context': context}}
    identity = store.reserve_action(action, 2, day)
    command = store.claim('simulated-worker')
    record_step(store, command['id'], 'simulated-worker', {'sequence': 1, 'phase': 'started', 'name': 'fill'})
    dataset = business.datasets(store)[0]
    options = {'version': dataset['version'], 'active': True, 'model_mode': 'local'}
    preview = business.permission_preview(store, dataset['id'], options)
    business.update_dataset(store, dataset['id'], options | {'preview_token': preview['preview_token']})
    with pytest.raises(ValueError, match='公开权限已变化'):
        record_step(store, command['id'], 'simulated-worker', {'sequence': 2, 'phase': 'started', 'name': 'submit'})
    with pytest.raises(ValueError, match='公开权限已变化'):
        store.reserve_action(action | {'target': 'new-attempt'}, 2, day)
    assert identity


def test_import_preview_is_bound_to_topic_and_cannot_move_datasets(configured):
    store, policy, day = configured
    text = f'日期,销售额\n{day},100\n'
    first, _ = import_csv(store, text, dedupe=False)
    old_receipt = business.confirm(store, first)
    store.configure({**policy, 'topic': '另一个行业'}, 1)
    with pytest.raises(ValueError, match='预览已变化'):
        business.confirm(store, first)
    second, _ = import_csv(store, text, dedupe=False)
    new_receipt = business.confirm(store, second)
    assert old_receipt['dataset_id'] != new_receipt['dataset_id']
    assert {d['scope_topic'] for d in business.datasets(store)} == {'收纳', '另一个行业'}
