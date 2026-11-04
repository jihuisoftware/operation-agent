"""Continuation reads captured artifacts rather than newer outputs from another execution."""
from copy import deepcopy

import pytest

from plugins.operations import analytics, industry, topics, analysis_config
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.store import Store
from tests.plugins.operations_support import prepare_materials


def frozen_store(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store(tmp_path / 'frozen.db')
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='冻结依据', goal='继续原批次')
    policy['modules'].update(organize=True, analytics=True, industry=True, topics=True, content=True)
    store.configure(policy, 0)
    day = local_day(policy)
    store.put('source', {'day': day, 'scope_topic': policy['topic'], 'title': '来源', 'text': '完整且未改变的文档',
                         'url': 'https://example.org/source', 'state': 'read'}, 'source')
    prepare_materials(store, policy, day, monkeypatch)
    analytics.analyze(store, policy, day, 1)
    finding = {'view': 'content', 'dimension': '需求', 'title': '原批次结论', 'text': '原批次依据', 'scope': '这份文档',
               'counter': '反证待查', 'unknowns': '不外推', 'evidence_ids': ['source'], 'visibility': 'public'}
    monkeypatch.setattr(industry, 'generate', lambda *_: {'findings': [finding]})
    industry.analyze(store, policy, day, 1)
    monkeypatch.setattr(topics, 'generate', lambda *_: {'topics': [{'title': '原批次题目', 'source_ids': ['source']}]})
    topics.generate_topics(store, policy, day, 1)
    store.resume_artifacts = {'brief_id': topics.catalog(store)['brief_id'],
                             'analytics_report_id': store.objects('analytics_report')[0]['id'],
                             'industry_report_id': store.objects('industry_report')[0]['id'],
                             'selected_topic_snapshot': None}
    return store, policy, day


def test_newer_outputs_cannot_replace_frozen_topic_and_analysis(tmp_path, monkeypatch):
    store, policy, day = frozen_store(tmp_path, monkeypatch)
    captured = dict(store.resume_artifacts)
    del store.resume_artifacts
    analytics.analyze(store, policy, day, 1)
    newer = store.objects('industry_report')[0]
    newer = {key: value for key, value in newer.items() if key != 'id'}
    newer['analytics_id'] = store.objects('analytics_report')[0]['id']
    newer['findings'] = [{**newer['findings'][0], 'title': '别的批次新结论'}]
    store.put('industry_report', newer)
    monkeypatch.setattr(topics, 'generate', lambda *_: {'topics': [{'title': '别的批次新题目', 'source_ids': ['source']}]})
    topics.generate_topics(store, policy, day, 1, force=True)
    store.resume_artifacts = captured
    assert topics.production_topic(store, policy, day)['title'] == '原批次题目'
    context = industry.production_context(store, policy, day)
    assert context['industry_id'] == captured['industry_report_id']
    assert context['analytics_id'] == captured['analytics_report_id']
    assert context['findings'][0]['title'] == '原批次结论'


def test_changed_selection_or_scope_rejects_frozen_continuation(tmp_path, monkeypatch):
    store, policy, day = frozen_store(tmp_path, monkeypatch)
    topics.select(store, {'version': 1, 'title': '用户新指定题目'})
    with pytest.raises(ValueError, match='选题.*变化'):
        topics.production_topic(store, policy, day)
    analysis_config.configure(store, {'version': 0, 'config': {'period': '30'}})
    with pytest.raises(ValueError, match='分析.*变化'):
        industry.production_context(store, policy, day)


def test_missing_frozen_record_never_falls_back_to_latest(tmp_path, monkeypatch):
    store, policy, day = frozen_store(tmp_path, monkeypatch)
    store.resume_artifacts['industry_report_id'] = 'missing-record'
    with pytest.raises(ValueError, match='不存在'):
        industry.production_context(store, policy, day)
    store.resume_artifacts['industry_report_id'] = None
    assert industry.production_context(store, policy, day)['industry_id'] is None
