"""Known-unsubmitted attempts never permanently fence a new approved publication."""
import json

import pytest

from plugins.operations import service
from plugins.operations.store import Store, encoded
from tests.plugins.test_operations import enable
from tests.plugins.test_operations_publication_independence import manuscript


def prepared(tmp_path):
    store = Store(tmp_path / 'posts.db')
    version, _ = enable(store, limits={**store.policy()[1]['limits'], 'publish': 1})
    store.current_run_id = 'old-run'
    action = manuscript('same-copy')
    action['content']['id'] = 'old-content'
    identity = store.reserve_action(action, version)
    return store, version, action, identity


def test_new_run_can_publish_cancelled_unclaimed_copy_without_deleting_history(tmp_path):
    store, version, action, old = prepared(tmp_path)
    service.cancel_action(store, old)
    with store.connection() as db:
        original = dict(db.execute('SELECT * FROM actions WHERE id=?', (old,)).fetchone())
    store.current_run_id = 'new-run'
    action = {**action, 'content': {**action['content'], 'id': 'new-content'}}
    new = store.reserve_action(action, version)
    assert new and new != old
    assert store.reserve_action(action, version) is None
    with store.connection() as db:
        assert dict(db.execute('SELECT * FROM actions WHERE id=?', (old,)).fetchone()) == original
        assert db.execute("SELECT count(*) FROM commands WHERE action_id=? AND state='queued'", (new,)).fetchone()[0] == 1
    store.current_run_id = 'third-run'
    with pytest.raises(ValueError, match='未核对'):
        store.reserve_action(action, version)


@pytest.mark.parametrize('state', ['failed', 'blocked', 'confirmed_not_published'])
def test_known_unsubmitted_failure_reuses_topic_allowance(state, tmp_path):
    store, version, action, old = prepared(tmp_path)
    receipt = {'state': state, 'submitted': False, 'dispatch_state': 'read_only'}
    with store.connection() as db:
        db.execute('UPDATE actions SET state=?,result=? WHERE id=?', (state, encoded(receipt), old))
        db.execute("UPDATE commands SET state='done',worker='desktop',result=? WHERE action_id=?", (encoded(receipt), old))
    store.current_run_id = 'new-run'
    assert store.reserve_action(action, version)
    with pytest.raises(ValueError, match='每日动作额度'):
        store.reserve_action(manuscript('different-copy'), version)


@pytest.mark.parametrize('state', ['published', 'confirmed', 'unknown', 'submitted', 'executing', 'queued'])
def test_completed_or_uncertain_copy_cannot_publish_in_a_new_batch(state, tmp_path):
    store, version, action, old = prepared(tmp_path)
    with store.connection() as db:
        db.execute('UPDATE actions SET state=?,result=? WHERE id=?', (state, encoded({'state': state, 'submitted': True}), old))
        db.execute("UPDATE commands SET state='done',worker='desktop',result=? WHERE action_id=?", (encoded({'submitted': True}), old))
    store.current_run_id = 'new-run'
    with pytest.raises(ValueError, match='已发布|未核对'):
        store.reserve_action(action, version)


def test_cancelled_label_alone_does_not_hide_submission_evidence(tmp_path):
    store, version, action, old = prepared(tmp_path)
    with store.connection() as db:
        db.execute("UPDATE actions SET state='cancelled',result=? WHERE id=?", (encoded({'submitted': False, 'dispatch_state': 'read_only'}), old))
        db.execute("UPDATE commands SET state='done',worker='desktop',result=? WHERE action_id=?", (encoded({'submitted': True, 'dispatch_state': 'submission_started'}), old))
    store.current_run_id = 'new-run'
    with pytest.raises(ValueError, match='未核对'):
        store.reserve_action(action, version)


def shared_stores(tmp_path):
    from plugins.operations.workspaces import Workspaces
    directory = Workspaces(tmp_path)
    first = directory.create('业务')
    second = directory.create('第二主题', business=first['business_id'])
    a = directory.store(first['business_id'], first['topic_id'])
    b = directory.store(second['business_id'], second['topic_id'])
    for store in (a, b):
        enable(store, limits={**store.policy()[1]['limits'], 'publish': 1})
    return directory, a, b


def test_shared_allowance_and_cross_topic_history_survive_new_attempts(tmp_path):
    directory, a, b = shared_stores(tmp_path)
    action = manuscript('same-copy')
    a.current_run_id = 'old'
    old = a.reserve_action(action, 1)
    service.cancel_action(a, old)
    b.current_run_id = 'new'
    new = b.reserve_action(action, 1)
    assert new and new != old
    with directory.connection() as db:
        assert db.execute("SELECT sum(amount) FROM charges WHERE kind='publish'").fetchone()[0] == 1
    a.current_run_id = 'third'
    with pytest.raises(ValueError, match='未核对'):
        a.reserve_action(action, 1)
    command = b.claim('desktop')
    b.acknowledge(command['id'], 'desktop', {'state': 'published', 'evidence': '隔离平台确认发布'})
    with pytest.raises(ValueError, match='已发布'):
        a.reserve_action(action, 1)
    with a.connection() as db:
        assert db.execute('SELECT state FROM actions WHERE id=?', (old,)).fetchone()[0] == 'cancelled'


def test_same_topic_reuses_existing_shared_charge_without_refunding_it(tmp_path):
    directory, a, _ = shared_stores(tmp_path)
    action = manuscript('same-copy')
    a.current_run_id = 'old'
    old = a.reserve_action(action, 1)
    service.cancel_action(a, old)
    a.current_run_id = 'new'
    new = a.reserve_action(action, 1)
    with directory.connection() as db:
        assert db.execute("SELECT count(*),sum(amount) FROM charges WHERE kind='publish'").fetchone()[:] == (1, 1)
    with a.connection() as db:
        data = json.loads(db.execute('SELECT data FROM actions WHERE id=?', (new,)).fetchone()[0])
    assert data['publication_charge_id'] == a.scope['id'] + ':' + old


def test_human_correction_before_dispatch_stops_a_reserved_copy(tmp_path):
    store, version, action, old = prepared(tmp_path)
    service.cancel_action(store, old)
    store.current_run_id = 'new'
    new = store.reserve_action(action, version)
    service.resolve_action(store, old, 'published', '人工随后发现同文已在平台发布')
    assert store.claim('desktop') is None
    with store.connection() as db:
        row = db.execute('SELECT state,result FROM actions WHERE id=?', (new,)).fetchone()
        result = json.loads(row['result'])
        assert row['state'] == 'blocked' and result['error_code'] == 'ALREADY_PUBLISHED'
        assert result['submitted'] is False


def test_manual_confirmation_only_covers_the_attempt_that_was_checked(tmp_path):
    store, version, action, old = prepared(tmp_path)
    command = store.claim('desktop')
    store.acknowledge(command['id'], 'desktop', {'state': 'unknown', 'submitted': True, 'evidence': '结果待核对'})
    service.resolve_action(store, old, 'confirmed_not_published', '核对平台后确认没有发布')
    service.retry_action(store, old)
    service.cancel_action(store, old)
    store.current_run_id = 'new'
    assert store.reserve_action(action, version)


def test_shared_account_racing_retries_reserve_one_new_attempt(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    directory, a, b = shared_stores(tmp_path)
    action = manuscript('same-copy')
    a.current_run_id = 'old'
    old = a.reserve_action(action, 1)
    service.cancel_action(a, old)
    # Older installations indexed a single raw content fingerprint.
    with directory.connection() as db:
        db.execute("UPDATE account_claims SET target=? WHERE action_id=?", (action['target'], old))
    a.current_run_id, b.current_run_id = 'retry-a', 'retry-b'
    def reserve(store):
        from plugins.operations.action_admission import ActionDeferred
        try:
            return store.reserve_action(action, 1)
        except ActionDeferred:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, (a, b)))
    assert sum(bool(value) for value in results) == 1
    with directory.connection() as db:
        assert db.execute("SELECT sum(amount) FROM charges WHERE kind='publish'").fetchone()[0] == 1


def test_human_correction_after_claim_stops_submit_step(tmp_path):
    from plugins.operations.browser_evidence import record_step
    store, version, action, old = prepared(tmp_path)
    service.cancel_action(store, old)
    store.current_run_id = 'new'
    store.reserve_action(action, version)
    command = store.claim('desktop')
    service.resolve_action(store, old, 'published', '检查后确认同文已经发布')
    with pytest.raises(ValueError, match='已发布'):
        record_step(store, command['id'], 'desktop', {'sequence': 1, 'name': 'submit', 'phase': 'started'})
    assert not store.objects('browser_step')
