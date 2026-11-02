"""Shared account queues, holds and message transfers retain topic ownership."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import time

import pytest

from plugins.operations.policy import DEFAULT
from plugins.operations.workspaces import Workspaces


def account_topics(tmp_path):
    directory = Workspaces(tmp_path)
    first = directory.create('业务')
    second = directory.create('同名主题', business=first['business_id'])
    stores = [directory.store(s['business_id'], s['topic_id']) for s in (first, second)]
    for store in stores:
        policy = deepcopy(DEFAULT)
        policy.update(topic=store.scope['name'], goal='测试', enabled=True)
        policy['modules']['research'] = True
        store.configure(policy, store.policy()[0])
    return directory, stores


def test_shared_account_claim_is_atomic_and_poll_heartbeats_all_topics(tmp_path):
    from plugins.operations.workspace_broker import poll
    directory, (a, b) = account_topics(tmp_path)
    for index, store in enumerate((a, b)):
        with store.connection() as db:
            db.execute("INSERT INTO commands VALUES (?,NULL,'account','{}','queued',NULL,?,'{}')", (str(index), time.time() + 120))
    with ThreadPoolExecutor(2) as executor:
        results = list(executor.map(lambda store: store.claim(store.scope['id']), (a, b)))
    assert sum(result is not None for result in results) == 1
    owner = a if results[0] else b
    claimed = next(result for result in results if result)
    owner.acknowledge(claimed['id'], owner.scope['id'], {'state': 'confirmed'})
    result = poll(directory, a.scope['account'], 'desktop', False)
    assert result['command']['scope']['topic_id'] != owner.scope['id']
    for store in (a, b):
        with store.connection() as db:
            assert db.execute("SELECT 1 FROM workers WHERE id='desktop'").fetchone()


def test_shared_takeover_cannot_be_released_from_another_live_window(tmp_path):
    from plugins.operations.readiness import takeover
    from plugins.operations.workspace_execution import check_running
    directory, (a, b) = account_topics(tmp_path)
    takeover(a, 'first-window', True)
    check_running(b)  # Independent collection and analysis remain available.
    with pytest.raises(ValueError, match='接管'):
        check_running(b, web=True)
    with pytest.raises(ValueError, match='另一执行窗口'):
        takeover(b, 'second-window', False)
    takeover(b, 'first-window', False)
    check_running(a, web=True)
    directory.update_state('profile', None, 'pause')
    takeover(a, 'first-window', False)
    with pytest.raises(ValueError, match='暂停'):
        check_running(a)


def test_transferring_received_message_does_not_enqueue_or_cross_accounts(tmp_path):
    from plugins.operations.workspace_inbox import transfer, candidates
    directory, (a, b) = account_topics(tmp_path)
    identity = a.put('inbox', {'id': 'received-1', 'kind': 'dm', 'state': 'needs_review', 'text': '请问价格？'}, 'inbox-1')
    other = directory.create('独立业务')
    with pytest.raises(ValueError, match='共用'):
        transfer(a, {**other, 'id': identity})
    transfer(a, {'business_id': b.scope['business_id'], 'topic_id': b.scope['id'], 'id': identity})
    assert a.objects('inbox')[0]['state'] == 'transferred'
    assert b.objects('inbox')[0]['state'] == 'needs_review'
    assert not candidates(a, 'dm', [{'id': 'received-1'}])
    assert candidates(b, 'dm', [{'id': 'received-1'}])
    with b.connection() as db:
        assert not db.execute('SELECT 1 FROM commands').fetchone()


def test_duplicate_scanned_account_requires_explicit_link(tmp_path):
    from plugins.operations.workspace_execution import observe_account, check_running, link_account
    directory, (a, _) = account_topics(tmp_path)
    other = directory.create('第二业务')
    b = directory.store(other['business_id'], other['topic_id'])
    observed = {'platform': 'xiaohongshu', 'state': 'logged_in', 'account_id': 'actual-account'}
    observe_account(a, observed)
    observe_account(b, observed)
    with pytest.raises(ValueError, match='已有账号重复'):
        check_running(b, web=True)
    link_account(directory, b.scope['business_id'], a.scope['account'])
    check_running(b, web=True)


def test_manual_request_ids_are_topic_local_and_persist_across_reopen(tmp_path):
    from plugins.operations.workspace_runtime import request_run
    _, (a, b) = account_topics(tmp_path)
    for store in (a, a, b):
        request_run(store, 'same-request')
    with Workspaces(tmp_path).connection() as db:
        rows = db.execute('SELECT topic_id,state FROM requests').fetchall()
    assert {(row['topic_id'], row['state']) for row in rows} == {(a.scope['id'], 'pending'), (b.scope['id'], 'pending')}
    from plugins.operations.upcoming import upcoming, cancel
    planned = upcoming(a)
    step = planned['manual'][0]
    cancel(a, {**step, 'version': planned['version']})
    assert upcoming(a)['manual'][0]['state'] == 'cancelled'
    assert upcoming(b)['manual'][0]['state'] == 'pending'
