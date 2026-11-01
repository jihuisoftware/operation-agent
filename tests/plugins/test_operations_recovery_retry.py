"""Independent read-only recovery retries transient failures without resubmission."""
from copy import deepcopy
from datetime import datetime, timedelta, UTC
from plugins.operations.policy import DEFAULT
from plugins.operations.store import Store
from plugins.operations.recovery import reconcile_pending


def test_transient_reconciliation_retries_after_backoff_and_never_sends(tmp_path):
    store = Store(tmp_path / 'recovery.db')
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='测试', goal='核对', account_id='me')
    policy['modules']['publish'] = True
    store.configure(policy, 0)
    action = {'kind': 'publish', 'account_id': 'me', 'target': 'note', 'content': {'title': '测试', 'body': '摘要'}}
    identity = store.reserve_action(action, 1)
    command = store.claim('desktop')
    store.acknowledge(command['id'], 'desktop', {'state': 'submitted', 'url': 'https://www.xiaohongshu.com/explore/test'})
    verify = store.claim('desktop')
    assert verify['kind'] == 'verify' and verify['id'] != command['id']
    store.acknowledge(verify['id'], 'desktop', {'state': 'unknown', 'error': '暂时离线'})
    now = datetime.now(UTC)
    reconcile_pending(store, policy, '2026-11-01', now)
    assert store.claim('desktop') is None
    reconcile_pending(store, policy, '2026-11-01', now + timedelta(minutes=6))
    second = store.claim('desktop')
    assert second['kind'] == 'verify'
    store.acknowledge(second['id'], 'desktop', {'state': 'published', 'evidence': '公开链接及作者、正文一致'})
    assert store.snapshot()['actions'][0]['state'] == 'published'
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM commands WHERE action_id=?", (identity,)).fetchone()[0] == 1
