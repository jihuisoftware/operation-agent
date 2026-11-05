"""Review sees attributable evidence; bounded revisions preserve drafts and approval boundaries."""
from copy import deepcopy

import pytest

from plugins.operations import content
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.store import Store
from tests.plugins.operations_support import prepare_materials


def configured(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store(tmp_path / 'repair.db')
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='工程实践', goal='准确分享')
    policy['modules'].update(content=True, organize=True)
    store.configure(policy, 0)
    day = local_day(policy)
    store.put('source', {'day': day, 'scope_topic': policy['topic'], 'text': '旧文发布于2026-09-29。Skill Space 与 Skill Runtime 需要分别验证。',
                        'state': 'read', 'title': '工程资料', 'url': 'https://example.org/article'}, 'source')
    prepare_materials(store, policy, day, monkeypatch)
    return store, policy, day


def test_review_reads_middle_evidence_and_does_not_treat_unpublished_drafts_as_releases(tmp_path, monkeypatch):
    store, policy, day = configured(tmp_path, monkeypatch)
    source = {'id': 'source', 'text': '背景\n' * 1700 + '\nSkill Space 与 Skill Runtime 不相同。\n' + '结尾\n' * 1700, 'truncated': False}
    other = [{'id': f'other-{i}', 'text': '其他资料\n' * 1000, 'truncated': False} for i in range(3)]
    draft = {'id': 'current', 'title': '核对工程能力', 'body': 'Skill Space 与 Skill Runtime 不相同。', 'source_ids': ['source', *[row['id'] for row in other]], 'asset_ids': ['cover']}
    store.put('asset', {'authorized': True, 'name': '自动文字封面.png', 'generated_typography': True, 'cover_title': draft['title']}, 'cover')
    store.put('content', {**draft, 'id': 'old', 'ready': False, 'quality': {'pass': False}}, 'old')
    def check(*args):
        data = args[-1]
        assert 'Skill Space 与 Skill Runtime' in data['sources'][0]['text']
        assert not data['sources'][0]['text_truncated']
        assert not data['history']
        assert data['assets'][0]['generated_typography'] is True
        return {'pass': True, 'reason': '可核对'}
    monkeypatch.setattr(content, 'generate', check)
    assert content.check_content(store, policy, day, 1, draft, [source, *other])['pass'] is True


def test_failed_review_revises_and_rechecks_without_mutating_parent_or_repeating_work(tmp_path, monkeypatch):
    store, policy, day = configured(tmp_path, monkeypatch)
    calls = []
    def generate(*args):
        data = args[-1]
        calls.append(data)
        if data.get('task') == 'revise_content':
            assert '日期' in str(data['review'])
            return {'title': '工程来源核对', 'body': '根据已采集资料整理，原文发布时间并不等于采集时间。', 'source_ids': ['source'], 'asset_ids': data['draft']['asset_ids']}
        return {'title': '工程能力核对', 'body': '这些文章都是今天发布的。', 'source_ids': ['source'], 'asset_ids': []}
    checked = []
    def check(_store, _policy, _day, _version, draft, _sources):
        checked.append(draft['body'])
        return {'pass': '今天发布' not in draft['body'], 'reason': '修正日期，区分发布时间和采集时间'}
    monkeypatch.setattr(content, 'generate', generate)
    monkeypatch.setattr(content, 'check_content', check)
    outcome = content.produce_content(store, policy, day, 1)
    assert outcome['ready'] is True and outcome['revision_count'] == 1
    rows = {row['id']: row for row in store.objects('content')}
    revised = rows[outcome['content_id']]
    parent = rows[revised['parent_content_id']]
    assert parent['body'] == '这些文章都是今天发布的。' and parent['quality']['pass'] is False
    assert revised['body'] != parent['body']
    assert revised['asset_ids'] != parent['asset_ids']
    cover = next(row for row in store.objects('asset') if row['id'] == revised['asset_ids'][0])
    assert cover['cover_title'] == revised['title']
    assert len(calls) == len(checked) == 2
    assert content.produce_content(store, policy, day, 1)['content_id'] == outcome['content_id']
    assert len(calls) == len(checked) == 2
    assert not store.snapshot()['actions']


def test_revision_cap_survives_new_calls_and_never_forces_review_to_pass(tmp_path, monkeypatch):
    store, policy, day = configured(tmp_path, monkeypatch)
    calls = []
    def generate(*args):
        calls.append(args[-1])
        return {'title': '工程核对', 'body': f'仍待核实的说法{len(calls)}', 'source_ids': ['source'], 'asset_ids': []}
    monkeypatch.setattr(content, 'generate', generate)
    monkeypatch.setattr(content, 'check_content', lambda *_: {'pass': False, 'reason': '证据不足'})
    result = content.produce_content(store, policy, day, 1)
    assert not result['ready'] and result['revision_count'] == 2
    assert len(calls) == 3 and len(store.objects('content')) == 3
    assert not content.produce_content(store, policy, day, 1)['ready']
    assert len(calls) == 3
    assert all(not row['ready'] for row in store.objects('content'))


def test_long_evidence_selects_relevant_middle_and_marks_excerpt_separately():
    from plugins.operations.content_evidence import review_sources, REVIEW_CHARACTERS
    text = '背景资料\n' * 12000 + '\nSkill Runtime 必须单独验证。\n' + '其他资料\n' * 12000
    rows = review_sources({'title': 'Skill Runtime', 'body': 'Skill Runtime 必须单独验证。', 'source_ids': ['long']},
                          [{'id': 'long', 'text': text, 'truncated': False}])
    assert 'Skill Runtime 必须单独验证' in rows[0]['text']
    assert rows[0]['excerpted'] and not rows[0]['source_truncated']
    assert sum(end - start for start, end in rows[0]['review_ranges']) <= REVIEW_CHARACTERS


def test_interrupted_recheck_resumes_saved_revision_without_generating_it_again(tmp_path, monkeypatch):
    from plugins.operations.model_errors import ModelServiceUnavailable
    store, policy, day = configured(tmp_path, monkeypatch)
    calls, checks = [], []
    def generate(*args):
        calls.append(args[-1])
        return {'title': '工程核对', 'body': '修订后的中性表述' if args[-1].get('task') == 'revise_content' else '今天发布的资料', 'source_ids': ['source'], 'asset_ids': []}
    def check(*args):
        draft = args[-2]
        checks.append(draft['id'])
        if draft.get('revision_index'):
            raise ModelServiceUnavailable('临时超时')
        return {'pass': False, 'reason': '修正日期'}
    monkeypatch.setattr(content, 'generate', generate)
    monkeypatch.setattr(content, 'check_content', check)
    with pytest.raises(ModelServiceUnavailable):
        content.produce_content(store, policy, day, 1)
    saved = next(row for row in store.objects('content') if row.get('revision_index') == 1)
    assert saved['review_pending'] and not saved['ready']
    monkeypatch.setattr(content, 'check_content', lambda *_: {'pass': True, 'reason': '已确认'})
    result = content.produce_content(store, policy, day, 1)
    assert result['content_id'] == saved['id'] and result['ready']
    assert len(calls) == 2 and len(store.objects('content')) == 2


def test_rule_change_during_revision_does_not_save_new_content(tmp_path, monkeypatch):
    store, policy, day = configured(tmp_path, monkeypatch)
    def generate(*args):
        if args[-1].get('task') == 'revise_content':
            store.configure({**policy, 'paused': True}, 1)
        return {'title': '工程核对', 'body': '待核对正文', 'source_ids': ['source'], 'asset_ids': []}
    monkeypatch.setattr(content, 'generate', generate)
    monkeypatch.setattr(content, 'check_content', lambda *_: {'pass': False, 'reason': '证据不足'})
    with pytest.raises(ValueError, match='规则'):
        content.produce_content(store, policy, day, 1)
    assert len(store.objects('content')) == 1
    assert not store.objects('content')[0]['ready']


def test_passed_check_reuses_exact_inputs_but_a_new_publication_invalidates_it(tmp_path, monkeypatch):
    from plugins.operations.store import encoded
    store, policy, day = configured(tmp_path, monkeypatch)
    draft = {'id': 'draft', 'title': '工程核对', 'body': '原文发布时间需要核对。', 'source_ids': ['source'], 'asset_ids': []}
    calls = []
    def check(*args):
        calls.append(args[-1])
        return {'pass': not args[-1]['history'], 'reason': '已发布内容比较'}
    monkeypatch.setattr(content, 'generate', check)
    sources = store.objects('source')
    assert content.check_content(store, policy, day, 1, draft, sources)['pass']
    assert content.check_content(store, policy, day, 1, draft, sources)['pass']
    assert len(calls) == 1
    with store.connection() as db:
        db.execute("INSERT INTO actions VALUES ('published',?,1,'publish','target','published',?,'{}','now')",
                   (day, encoded({'content': {**draft, 'id': 'published'}})))
    assert not content.check_content(store, policy, day, 1, draft, sources)['pass']
    assert len(calls) == 2 and calls[-1]['history'][0]['id'] == 'published'


def test_low_budget_preserves_draft_without_starting_revision(tmp_path, monkeypatch):
    store, policy, day = configured(tmp_path, monkeypatch)
    policy['model_calls'] = 1
    store.configure(policy, 1)
    calls = []
    monkeypatch.setattr(content, 'generate', lambda *args: calls.append(args[-1]) or {
        'title': '工程核对', 'body': '待核实内容', 'source_ids': ['source'], 'asset_ids': []})
    monkeypatch.setattr(content, 'check_content', lambda *_: {'pass': False, 'reason': '证据不足'})
    result = content.produce_content(store, policy, day, 2)
    assert not result['ready'] and result['revision_count'] == 0
    assert '额度不足' in result['reason']
    assert len(calls) == 1 and not store.objects('content_revision_attempt')
