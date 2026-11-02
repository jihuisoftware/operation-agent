"""Workspace boundaries use real SQLite files and shared transactional reservations."""
from copy import deepcopy
import json
import pytest

from plugins.operations.workspaces import Workspaces
from plugins.operations.policy import DEFAULT


def test_same_names_isolate_settings_records_and_profile(tmp_path):
    directory = Workspaces(tmp_path / 'first')
    left = directory.create('同名业务')
    right = directory.create('同名业务')
    a, b = directory.store(left['business_id'], left['topic_id']), directory.store(right['business_id'], right['topic_id'])
    a.put('source', {'title': '只属于甲'}, 'same-id')
    b.put('source', {'title': '只属于乙'}, 'same-id')
    assert a.objects('source')[0]['title'] == '只属于甲'
    assert b.objects('source')[0]['title'] == '只属于乙'
    directory.rename('topics', left['topic_id'], '新名称')
    assert directory.resolve(business=left['business_id'], topic=left['topic_id'])['name'] == '新名称'
    assert a.objects('source')[0]['id'] == 'same-id'
    with pytest.raises(ValueError, match='不存在'):
        directory.store(left['business_id'], right['topic_id'])
    with pytest.raises(ValueError, match='不存在'):
        Workspaces(tmp_path / 'second').store(left['business_id'], left['topic_id'])


def test_shared_budget_does_not_reset_on_new_topic(tmp_path):
    from plugins.operations.workspace_execution import charge
    directory = Workspaces(tmp_path)
    first = directory.create('业务')
    second = directory.create('主题二', business=first['business_id'])
    with directory.connection() as db:
        db.execute("UPDATE preferences SET data=? WHERE id='limits'", (json.dumps({'source': 1}),))
    a = directory.store(first['business_id'], first['topic_id'])
    b = directory.store(second['business_id'], second['topic_id'])
    with a.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        charge(a, db, '2026-11-02', 'source')
    with b.connection() as db, pytest.raises(ValueError, match='总额度'):
        charge(b, db, '2026-11-02', 'source')
    with b.connection() as db:
        charge(b, db, '2026-11-03', 'source')


def test_account_shared_claim_and_pause_boundary(tmp_path):
    from plugins.operations.workspace_execution import reserve_action, link_account, check_running
    directory = Workspaces(tmp_path)
    first, second = directory.create('甲'), directory.create('乙')
    a = directory.store(first['business_id'], first['topic_id'])
    b = directory.store(second['business_id'], second['topic_id'])
    link_account(directory, second['business_id'], a.scope['account'])
    action = {'kind': 'reply', 'target': 'received-message', 'account_id': 'scanned'}
    with a.connection() as db:
        assert reserve_action(a, db, action, 'one', '2026-11-02')
    with b.connection() as db:
        assert not reserve_action(b, db, action, 'two', '2026-11-02')
    directory.update_state('businesses', first['business_id'], 'pause')
    with pytest.raises(ValueError, match='暂停'):
        check_running(a)
    check_running(b)
    directory.update_state('profile', None, 'pause')
    with pytest.raises(ValueError, match='暂停'):
        check_running(b)


def test_legacy_migration_keeps_provenance_and_quarantines_unknown_rows(tmp_path):
    from plugins.operations.store import Store
    original = Store(tmp_path / 'data.db')
    policy = deepcopy(DEFAULT)
    policy.update(topic='历史主题', goal='研究')
    original.configure(policy, 0)
    original.put('source', {'scope_topic': '历史主题', 'day': '2026-11-02', 'text': '甲'}, 'historical')
    policy['topic'] = '当前主题'
    original.configure(policy, 1)
    original.put('source', {'scope_topic': '当前主题', 'day': '2026-11-02', 'text': '乙'}, 'current')
    original.put('source', {'text': '归属不明'}, 'unassigned')
    directory = Workspaces(tmp_path)
    current = directory.store()
    assert {s['id'] for s in current.objects('source')} == {'current'}
    topics = directory.catalog()['topics']
    archive = next(t for t in topics if t['name'] == '历史主题')
    unknown = next(t for t in topics if t['name'] == '历史待归属')
    assert archive['archived'] and unknown['archived']
    assert directory.store(archive['business_id'], archive['id']).objects('source')[0]['id'] == 'historical'
    assert directory.store(unknown['business_id'], unknown['id']).objects('source')[0]['id'] == 'unassigned'
    assert (tmp_path / 'before-workspaces.db').exists()
    again = Workspaces(tmp_path)
    assert len(again.catalog()['topics']) == len(topics)
    assert again.store().objects('source')[0]['id'] == 'current'


def test_topic_rename_keeps_organized_evidence_and_references(tmp_path):
    from plugins.operations.organization import material_id, materials
    directory = Workspaces(tmp_path)
    scope = directory.create('原主题')
    store = directory.store(scope['business_id'], scope['topic_id'])
    source = {'scope_topic': '原主题', 'day': '2026-11-02', 'text': '内容', 'url': 'https://example.org', 'title': '原文'}
    identity = store.put('source', source, 'source')
    source['id'] = identity
    material = material_id(store.policy()[1], source)
    store.put('organized_source', {'scope_topic': '原主题', 'source_id': identity, 'relevant': True}, material)
    directory.rename('topics', scope['topic_id'], '新主题')
    reopened = directory.store(scope['business_id'], scope['topic_id'])
    assert reopened.policy()[1]['topic'] == '新主题'
    assert materials(reopened, reopened.policy()[1], '2026-11-02')[0][1]['id'] == material


def test_new_topic_inherits_business_resources_without_enabling_or_expanding_limits(tmp_path):
    directory = Workspaces(tmp_path)
    first = directory.create('业务', category='business-personal')
    a = directory.store(first['business_id'], first['topic_id'])
    version, policy = a.policy()
    policy.update(knowledge=['已确认的服务说明'], brand='品牌说明', account_id='required-account')
    policy['limits']['source'] = 7
    policy['allowed']['dm'] = False
    a.configure(policy, version)
    second = directory.create('另一个主题', business=first['business_id'])
    b = directory.store(second['business_id'], second['topic_id'])
    version, saved = b.policy()
    assert version == 0 and not saved['enabled']
    assert saved['knowledge'] == ['已确认的服务说明'] and saved['brand'] == '品牌说明'
    assert saved['business_theme'] == policy['business_theme']
    assert saved['limits']['source'] == 7 and not saved['allowed']['dm']
    copied = directory.create('复制主题', business=first['business_id'], copy_topic=first['topic_id'])
    assert directory.store(copied['business_id'], copied['topic_id']).policy()[1]['account_id'] == 'required-account'
    directory.update_state('topics', second['topic_id'], 'archive')
    policy['knowledge'] = ['更新知识']
    a.configure(policy, a.policy()[0])
    assert directory.store(second['business_id'], second['topic_id']).policy()[1]['knowledge'] == ['已确认的服务说明']


def test_explicit_source_reference_preserves_picture_and_origin_only_inside_business(tmp_path):
    from plugins.operations.workspace_topics import reference_source
    directory = Workspaces(tmp_path)
    first = directory.create('业务')
    second = directory.create('主题二', business=first['business_id'])
    other = directory.create('其他业务')
    a, b = [directory.store(scope['business_id'], scope['topic_id']) for scope in (first, second)]
    a.put('source_image', {'path': 'reference-pictures/original.png', 'source_id': 'source'}, 'picture')
    a.put('source', {'text': '正文', 'scope_topic': '业务', 'url': 'https://example.org', 'images': [{'id': 'picture'}]}, 'source')
    result = reference_source(b, first['topic_id'], 'source')
    assert b.objects('source')[0]['id'] == result['id']
    assert b.objects('source')[0]['origin']['topic_id'] == first['topic_id']
    assert b.objects('source_image')[0]['path'] == 'reference-pictures/original.png'
    with pytest.raises(ValueError, match='不存在'):
        reference_source(directory.store(other['business_id'], other['topic_id']), first['topic_id'], 'source')


def test_failed_migration_preserves_original_and_can_retry(tmp_path, monkeypatch):
    from plugins.operations.store import Store
    from plugins.operations import workspace_migration
    original = Store(tmp_path / 'data.db')
    original.configure({**deepcopy(DEFAULT), 'topic': '当前主题'}, 0)
    original.put('source', {'scope_topic': '历史主题', 'text': '保留的来源'}, 'historical')
    directory = Workspaces(tmp_path)
    def fail_prune(*args):
        raise RuntimeError('模拟迁移写入中断')
    with monkeypatch.context() as patch:
        patch.setattr(workspace_migration, 'prune', fail_prune)
        with pytest.raises(RuntimeError, match='迁移写入中断'):
            directory.store()
        with directory.connection() as db:
            assert not db.execute("SELECT 1 FROM preferences WHERE id='migration-complete'").fetchone()
        assert original.objects('source')[0]['id'] == 'historical'
    directory.store()
    archive = next(topic for topic in directory.catalog()['topics'] if topic['name'] == '历史主题')
    assert directory.store(archive['business_id'], archive['id']).objects('source')[0]['id'] == 'historical'
