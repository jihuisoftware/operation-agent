"""Separate publications share a browser lease, not a blanket historical-result fence."""
import json

import pytest

from plugins.operations.store import Store
from plugins.operations.workspaces import Workspaces
from tests.plugins.test_operations import enable


def manuscript(target):
    return {'kind': 'publish', 'account_id': 'me', 'target': target,
            'content': {'title': target, 'body': '独立稿件', 'asset_ids': []}}


@pytest.mark.parametrize('state', ['submitted', 'unknown', 'failed', 'queued', 'executing'])
def test_new_publication_is_independent_but_pending_same_content_cannot_resubmit(tmp_path, state):
    store = Store(tmp_path / 'topic.db')
    version, _ = enable(store, limits={**store.policy()[1]['limits'], 'publish': 10})
    store.manual_run_id = 'old'
    old = store.reserve_action(manuscript('旧稿'), version)
    with store.connection() as db:
        db.execute('UPDATE actions SET state=? WHERE id=?', (state, old))
        db.execute("UPDATE commands SET state='done' WHERE action_id=?", (old,))
    store.manual_run_id = 'new'
    new = store.reserve_action(manuscript('新稿'), version)
    assert new != old and new
    assert store.reserve_action(manuscript('新稿'), version) is None
    store.manual_run_id = 'another'
    if state != 'failed':
        from plugins.operations.action_admission import ActionDeferred
        with pytest.raises(ActionDeferred) as caught:
            store.reserve_action(manuscript('旧稿'), version)
        assert caught.value.result['blocking_action']['id'] == old
        assert '本次未执行' in str(caught.value)
    else:
        assert store.reserve_action(manuscript('旧稿'), version)


def test_shared_account_allows_distinct_posts_but_serializes_browser_commands(tmp_path):
    directory = Workspaces(tmp_path)
    first = directory.create('业务')
    second = directory.create('第二主题', business=first['business_id'])
    a = directory.store(first['business_id'], first['topic_id'])
    b = directory.store(second['business_id'], second['topic_id'])
    va, _ = enable(a, limits={**a.policy()[1]['limits'], 'publish': 10})
    vb, _ = enable(b, limits={**b.policy()[1]['limits'], 'publish': 10})
    with directory.connection() as db:
        limits = json.loads(db.execute("SELECT data FROM preferences WHERE id='limits'").fetchone()[0])
        limits['publish'] = 10
        db.execute("UPDATE preferences SET data=? WHERE id='limits'", (json.dumps(limits),))
    one = a.reserve_action(manuscript('第一篇'), va)
    a.claim('worker-a')
    two = b.reserve_action(manuscript('第二篇'), vb)
    assert one and two
    assert b.claim('worker-b') is None
    with a.connection() as db:
        command = db.execute('SELECT id FROM commands WHERE action_id=?', (one,)).fetchone()[0]
    a.acknowledge(command, 'worker-a', {'state': 'submitted', 'evidence': '等待独立核对'})
    assert b.claim('worker-b')['kind'] == 'publish'
    from plugins.operations.action_admission import ActionDeferred
    with pytest.raises(ActionDeferred) as caught:
        b.reserve_action(manuscript('第一篇'), vb)
    assert caught.value.result['blocking_action']['topic_id'] == first['topic_id']


def test_review_keeps_confirmed_facts_but_does_not_combine_old_checks_into_success(tmp_path):
    from plugins.operations.review_queue import request_check
    from plugins.operations.publication_status import complete
    from tests.plugins.test_operations_publication_evidence import prepared
    store, action, command = prepared(tmp_path / 'review.db')
    prior = {'state': 'submitted', 'evidence': '此前已核对全文', 'note_id': 'note',
             'publication': {'execution': 'verified', 'platform': 'reviewing', 'content': 'matched'}}
    store.acknowledge(command['id'], 'desktop', prior)
    request_check(store, action)
    probe = store.claim('desktop')
    current = {'state': 'submitted', 'evidence': '笔记详情尚未加载',
               'publication': {'execution': 'submitted', 'platform': 'published', 'content': 'unknown'}}
    store.acknowledge(probe['id'], 'desktop', current)
    row = store.snapshot()['actions'][0]
    result = json.loads(row['result'])
    assert result['publication'] == {'execution': 'verified', 'platform': 'published', 'content': 'matched'}
    assert result['last_check']['evidence'] == current['evidence']
    assert result['verification_stale'] is True
    assert row['state'] == 'submitted' and not complete(row)
    request_check(store, action)
    probe = store.claim('desktop')
    store.acknowledge(probe['id'], 'desktop', {**prior, 'publication': {
        'execution': 'verified', 'platform': 'published', 'content': 'matched'}})
    assert complete(store.snapshot()['actions'][0])


def test_legacy_downgraded_receipt_recovers_facts_without_changing_command_history(tmp_path):
    from plugins.operations.review_queue import request_check
    from tests.plugins.test_operations_publication_evidence import prepared
    store, action, command = prepared(tmp_path / 'legacy.db')
    prior = {'state': 'submitted', 'evidence': '全文核对，图片待确认',
             'publication': {'execution': 'verified', 'platform': 'published', 'content': 'incomplete'}}
    store.acknowledge(command['id'], 'desktop', prior)
    missing = {'state': 'submitted', 'evidence': '页面未加载',
               'publication': {'execution': 'submitted', 'platform': 'unknown', 'content': 'unknown'}}
    with store.connection() as db:
        db.execute('UPDATE actions SET result=? WHERE id=?', (json.dumps(missing), action))
        # The old client already finished its queued check before overwriting
        # the action. Its obsolete revision must not be replayed by this test.
        partial = {**prior, 'publication': {**prior['publication'], 'platform': 'unknown'}}
        db.execute("UPDATE commands SET state='done',result=? WHERE kind='verify'", (json.dumps(partial),))
    request_check(store, action)
    probe = store.claim('desktop')
    store.acknowledge(probe['id'], 'desktop', missing)
    result = json.loads(store.snapshot()['actions'][0]['result'])
    assert result['publication']['execution'] == 'verified'
    assert result['publication']['content'] == 'incomplete'
    assert result['publication']['platform'] == 'published'
    assert result['last_check']['evidence'] == '页面未加载'
    assert store.command(command['id'])['result']['evidence'] == prior['evidence']
    request_check(store, action)
    probe = store.claim('desktop')
    store.acknowledge(probe['id'], 'desktop', {**prior, 'publication': {
        'execution': 'verified', 'platform': 'rejected', 'content': 'mismatch'}})
    result = json.loads(store.snapshot()['actions'][0]['result'])
    assert result['publication']['content'] == 'mismatch'
    assert result['publication']['platform'] == 'rejected'
    assert not result['verification_stale']


def test_debug_reports_same_content_pending_as_not_executed(tmp_path, monkeypatch):
    from devtools.operations_debug import invoke
    from plugins.operations import workflow
    store = Store(tmp_path / 'debug.db')
    version, policy = enable(store)
    store.manual_run_id = 'old'
    action = store.reserve_action(manuscript('原稿'), version)
    store.manual_run_id = 'new'
    store.start_preflight_done = True
    store.claim('desktop', busy=True)
    monkeypatch.setattr(workflow, 'publish', lambda *_args, **_kwargs: store.reserve_action(manuscript('原稿'), version))
    result = invoke(store, 'publish', policy, '2026-11-08', version)
    assert result['state'] == 'skipped'
    assert result['result']['blocking_action']['id'] == action
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM events WHERE kind='debug_exception'").fetchone()[0] == 0


def test_preserved_reviewing_fact_does_not_extend_unavailable_page_retry_budget(tmp_path):
    from plugins.operations.review_queue import save, schedule
    store = Store(tmp_path / 'budget.db')
    with store.connection() as db:
        save(db, 'old', {'attempts': 7})
        tracking = schedule(db, 'old', {'state': 'submitted', 'publication': {'platform': 'reviewing'},
            'verification_stale': True, 'last_check': {'publication': {'platform': 'unknown'}, 'evidence': '页面未加载'}})
    assert tracking['state'] == 'needs_attention' and tracking['next_check_at'] is None
