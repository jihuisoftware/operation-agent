"""A newly reviewed version can replace a cancelled, explicitly unsubmitted attempt."""
from datetime import timedelta

from plugins.operations import content_release, publication_plan, service
from plugins.operations.content import content_digest
from plugins.operations.content_versions import create
from plugins.operations.store import encoded
from tests.plugins import test_operations_content_review as support

manuscript = support.manuscript


def test_identical_new_version_can_run_after_old_attempt_and_retry_were_cancelled(manuscript, monkeypatch):
    store, _, day, original = manuscript
    due, _, approved = support.approve(store, original)
    store.execution_now = due
    store.current_run_id = store.start_run(day, 'publish', 'old-release', 1)
    action = {'kind': 'publish', 'account_id': 'me', 'target': content_digest(original), 'content': original, 'human_review': approved['revision']}
    old = store.reserve_action(action, 1, day)
    receipt = {'state': 'blocked', 'submitted': False, 'dispatch_state': 'read_only', 'error': '网页窗口中断，尚未提交'}
    with store.connection() as db:
        db.execute("UPDATE actions SET state='blocked',result=? WHERE id=?", (encoded(receipt), old))
        db.execute("UPDATE commands SET state='done',worker='desktop',result=? WHERE action_id=?", (encoded(receipt), old))
    service.resolve_action(store, old, 'confirmed_not_published', '人工核对没有发布')
    service.retry_action(store, old)
    service.cancel_action(store, old)
    with store.connection() as db:
        release = content_release.load(db, original['id'])
        release['state'] = 'paused'
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(release), 'content-release:' + original['id']))
        old_row = dict(db.execute('SELECT * FROM actions WHERE id=?', (old,)).fetchone())
    child = create(store, original['id'], {'request_id': 'new-copy', 'version': 1, 'content_revision': content_release.fingerprint(original)})
    new_content = content_release.manuscript(store, child['id'])
    new_due, _, _ = support.approve(store, new_content)
    store.execution_now = new_due + timedelta(seconds=1)
    seen = support.desktop(store, monkeypatch)
    assert publication_plan.publish_due(store, store.execution_now)
    assert len(seen) == 1 and seen[0]['payload']['content']['id'] == child['id']
    with store.connection() as db:
        assert dict(db.execute('SELECT * FROM actions WHERE id=?', (old,)).fetchone()) == old_row
        assert content_release.load(db, child['id'])['state'] == 'published'
        assert db.execute("SELECT sum(amount) FROM directory.charges WHERE kind='publish'").fetchone()[0] == 1
    assert publication_plan.publish_due(store, store.execution_now) is False
