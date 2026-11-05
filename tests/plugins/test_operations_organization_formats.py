"""One malformed model item must not discard unrelated, attributable organization work."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from plugins.operations import organization
from plugins.operations.outcomes import describe
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.store import Store
from tests.plugins.operations_support import organized_response


def configured(tmp_path, sources):
    store = Store(tmp_path / 'formats.db')
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='工程实践', goal='保留可用结果')
    policy['modules']['organize'] = True
    store.configure(policy, 0)
    day = local_day(policy)
    for identity, text in sources.items():
        store.put('source', {'day': day, 'scope_topic': policy['topic'], 'title': identity,
                            'text': text, 'state': 'read', 'url': 'https://example.org/' + identity}, identity)
    return store, policy, day


def test_compatible_fields_and_bad_rows_keep_good_sources_and_continue_later_batches(tmp_path, monkeypatch):
    store, policy, day = configured(tmp_path, {str(i): f'完整原文{i}' for i in range(10)})
    calls = []
    def generate(*args):
        data = args[-1]
        calls.append(data['expected_source_ids'])
        result = organized_response(data)
        duplicate = []
        changes = {
            '0': {'keywords': '缓存、重试;检查', 'relevant': 'true', 'category': ' 方法教程 ', 'facts': '完整事实，条件不能拆散', 'opinions': None},
            '1': {'summary': {'unrecognized': '无可用摘要'}},
            '3': {'keywords': ['有效关键词', {'unsupported': '不能作为关键词'}, 123], 'facts': [{'text': '带有前提的事实陈述'}]},
        }
        for row in result['items']:
            row.update(changes.get(row['source_id'], {}))
            if row['source_id'] == '2':
                duplicate.append({**row, 'summary': '冲突摘要'})
        result['items'].extend([*duplicate, {'source_id': 'foreign'}])
        return result
    monkeypatch.setattr(organization, 'generate', generate)
    outcome = organization.organize(store, policy, day, 1)
    saved = {row['source_id']: row for row in store.objects('organized_source')}
    assert set(saved) == set(map(str, range(10))) - {'1', '2'}
    assert saved['0']['keywords'] == ['缓存', '重试', '检查']
    assert saved['0']['facts'] == ['完整事实，条件不能拆散'] and saved['0']['opinions'] == []
    assert saved['3']['keywords'] == ['有效关键词']
    assert saved['3']['facts'] == ['带有前提的事实陈述']
    assert outcome['pending'] == 2 and outcome['usable'] == 8
    assert describe('organize', outcome)[0] == 'needs_attention'
    assert len(calls) == 5 and calls.count(['1']) == calls.count(['2']) == 1
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM events WHERE kind='organization_format' ").fetchone()[0] > 0


def test_long_document_saves_valid_parts_skips_bad_part_and_only_repairs_missing_part(tmp_path, monkeypatch):
    text = '\n\n'.join(f'## 段落{i}\n' + str(i) * 5000 for i in range(6))
    store, policy, day = configured(tmp_path, {'long': text, 'short': '另一篇有效资料'})
    calls = []
    def invalid_part(*args):
        data = args[-1]
        calls.append(data)
        result = organized_response(data)
        for row in result['items']:
            if row['source_id'].endswith(':1'):
                row['summary'] = []
            else:
                row['keywords'] = '["分段", "恢复"]'
        return result
    monkeypatch.setattr(organization, 'generate', invalid_part)
    first = organization.organize(store, policy, day, 1)
    assert first['organized'] == 1 and first['pending'] == 1
    assert [row['source_id'] for row in store.objects('organized_source')] == ['short']
    saved_parts = {row['segment_id'] for row in store.objects('organization_part')}
    assert saved_parts and not any(identity.endswith(':1') for identity in saved_parts)
    assert not any(call['task'] == 'organize_merge' for call in calls)
    calls.clear()
    monkeypatch.setattr(organization, 'generate', lambda *args: calls.append(args[-1]) or organized_response(args[-1]))
    second = organization.organize(store, policy, day, 1)
    assert second['organized'] == 2 and second['pending'] == 0
    requested_parts = [item['id'] for call in calls if call['task'] == 'organize_sources' for item in call['sources']]
    assert len(requested_parts) == 1 and requested_parts[0].endswith(':1')
    assert not saved_parts.intersection(requested_parts)


@pytest.mark.parametrize('raw', ['```', '{"items":', [], None])
def test_unusable_provider_output_is_skipped_with_bounded_retries(tmp_path, monkeypatch, raw):
    store, policy, day = configured(tmp_path, {'one': '来源一', 'two': '来源二'})
    calls = []
    def provider(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[] if raw is None else [SimpleNamespace(message=SimpleNamespace(content=raw))], usage=None)
    monkeypatch.setattr('agent.auxiliary_client.call_llm', provider)
    result = organization.organize(store, policy, day, 1)
    assert result['organized'] == 0 and result['pending'] == 2
    assert len(calls) == 3
    assert describe('organize', result)[0] == 'needs_attention'


def test_format_tolerance_does_not_swallow_rule_change(tmp_path, monkeypatch):
    store, policy, day = configured(tmp_path, {'one': '来源一'})
    def changed(*_):
        store.configure({**policy, 'paused': True}, 1)
        return {'items': {'source_id': 'one', 'summary': '有效摘要', 'category': '方法教程', 'relevant': True}}
    monkeypatch.setattr(organization, 'generate', changed)
    with pytest.raises(ValueError, match='规则已变更'):
        organization.organize(store, policy, day, 1)
    assert not store.objects('organized_source')


def test_invalid_merge_keeps_parts_and_other_sources_then_retries_only_merge(tmp_path, monkeypatch):
    long = '\n\n'.join(f'## 第{i}段\n' + str(i) * 5000 for i in range(6))
    store, policy, day = configured(tmp_path, {'long': long, 'short': '另一来源'})
    calls = []
    def provider(*args):
        data = args[-1]
        calls.append(data)
        return {'items': [{'source_id': 'long', 'summary': []}]} if data['task'] == 'organize_merge' else organized_response(data)
    monkeypatch.setattr(organization, 'generate', provider)
    first = organization.organize(store, policy, day, 1)
    assert first['organized'] == 1 and first['pending'] == 1
    assert store.objects('organization_part')
    calls.clear()
    monkeypatch.setattr(organization, 'generate', lambda *args: calls.append(args[-1]) or organized_response(args[-1]))
    assert organization.organize(store, policy, day, 1)['pending'] == 0
    assert len(calls) == 1 and calls[0]['task'] == 'organize_merge'
