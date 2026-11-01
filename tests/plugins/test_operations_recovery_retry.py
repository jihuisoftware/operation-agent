"""Read-only reconciliation retries transient failures without resubmission."""
from copy import deepcopy
from datetime import datetime, timedelta, UTC
from plugins.operations.policy import DEFAULT
from plugins.operations.store import Store
from plugins.operations.recovery import reconcile_pending
from plugins.operations import workflow


def test_transient_reconciliation_retries_after_backoff_and_never_sends(tmp_path, monkeypatch):
    store = Store(tmp_path / 'recovery.db')
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='测试', goal='核对', account_id='me')
    policy['modules']['publish'] = True
    store.configure(policy, 0)
    action = {'kind':'publish','account_id':'me','target':'note','content':{'title':'测试','body':'摘要'}}
    identity = store.reserve_action(action, 1)
    command = store.enqueue('publish', action, identity)
    store.claim('desktop')
    store.acknowledge(command, 'desktop', {'state':'submitted','url':'https://www.xiaohongshu.com/explore/test'})
    calls=[]
    def browser(store, kind, payload):
        calls.append(kind)
        if len(calls) == 1:
            raise TimeoutError('暂时离线')
        return {'state':'published','evidence':'公开链接及作者、正文一致'}
    monkeypatch.setattr(workflow, 'browser', browser)
    now = datetime(2026,10,31,12,tzinfo=UTC)
    reconcile_pending(store, policy, '2026-10-31', now)
    reconcile_pending(store, policy, '2026-10-31', now+timedelta(seconds=10))
    assert calls == ['verify']
    reconcile_pending(store, policy, '2026-10-31', now+timedelta(minutes=6))
    assert calls == ['verify','verify']
    assert store.snapshot()['actions'][0]['state'] == 'published'
    with store.connection() as db:
        assert db.execute('SELECT count(*) FROM commands WHERE action_id=?',(identity,)).fetchone()[0] == 1
