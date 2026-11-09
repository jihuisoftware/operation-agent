"""Model requests use bounded evidence without resending nested stored snapshots."""
from copy import deepcopy
import json

from plugins.operations import analytics, content, industry, topics
from plugins.operations.policy import DEFAULT, local_day, now_iso
from plugins.operations.store import Store
from tests.plugins.operations_support import prepare_materials


def test_generation_and_review_bound_inputs_but_keep_full_saved_lineage(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store(tmp_path / 'inputs.db')
    policy = deepcopy(DEFAULT)
    policy.update(image_mode='basic', enabled=True, topic='输入复用', goal='有依据地生成内容', knowledge=['不得进入公开内容的内部回复知识'])
    policy['modules'].update(research=True, organize=True, analytics=True, industry=True, topics=True, content=True)
    store.configure(policy, 0)
    day = local_day(policy)
    for index in range(5):
        store.put('source', {'day': day, 'scope_topic': policy['topic'], 'title': f'来源{index}',
                            'text': f'原始正文{index}' * 1500 + '结尾限定条件', 'url': f'https://example.org/{index}', 'state': 'read'}, str(index))
    prepare_materials(store, policy, day, monkeypatch)
    analytics.analyze(store, policy, day, 1)
    base = store.objects('analytics_report')[0]
    finding = {'view': 'content', 'dimension': '趋势', 'title': '有依据的结论', 'text': '结论' * 500,
               'scope': '只适用于当前样本', 'counter': '仍有反向证据', 'unknowns': '存在待核实事项', 'visibility': 'public', 'evidence_ids': ['0']}
    findings = [{**finding, 'title': f'结论{index}'} for index in range(111)]
    store.put('industry_report', {**base, 'created': now_iso(), 'findings': findings, 'pending': 0})
    context = industry.production_context(store, policy, day)
    for index in range(15):
        store.put('content', {'title': f'历史稿件{index}', 'body': '历史正文', 'day': day, 'source_ids': ['0'],
                             'asset_ids': [], 'analysis_context': context, 'organized_evidence': [{'nested': '重复快照' * 20000}]}, f'old-{index}')
    original = store.objects('content')
    captured = []

    def generate(*args):
        data = args[-1]
        captured.append(data)
        if 'content' in data:
            return {'pass': True, 'reason': '已核对引用'}
        if 'assets' in data:
            return {'title': '新内容', 'body': '依据公开来源的正文', 'asset_ids': [], 'source_ids': ['0']}
        return {'topics': [{'title': '新选题', 'source_ids': ['0'], 'reason': '有来源'}]}

    monkeypatch.setattr(topics, 'generate', generate)
    monkeypatch.setattr(content, 'generate', generate)
    topics.generate_topics(store, policy, day, 1)
    produced = content.produce_content(store, policy, day, 1)
    assert len(captured) == 3
    assert all(len(json.dumps(data, ensure_ascii=False)) < 80000 for data in captured)
    assert all('analysis_context' not in row and 'organized_evidence' not in row for row in captured[0]['recent_content'])
    assert 'knowledge' not in captured[1]['policy']
    assert len(captured[0]['analysis']['findings']) < len(findings)
    assert all(row['counter'] and row['unknowns'] and row['scope'] for row in captured[0]['analysis']['findings'])
    assert [row['id'] for row in captured[2]['sources']] == ['0']
    assert 'analysis_context' not in captured[2]['content']
    saved = next(row for row in store.objects('content') if row['id'] == produced['content_id'])
    assert saved['analysis_context'] == context
    assert [row for row in store.objects('content') if row['id'].startswith('old-')] == original
