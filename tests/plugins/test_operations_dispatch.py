"""Action dispatch is atomic and incomplete external receipts remain incomplete."""
from copy import deepcopy
import sqlite3
import pytest
from plugins.operations.policy import DEFAULT
from plugins.operations.store import Store
from plugins.operations.outcomes import describe


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path / 'dispatch.db')
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='测试', goal='可靠执行', account_id='me')
    policy['modules']['comments'] = True
    store.configure(policy, 0)
    return store


def action(target='note'):
    return {'kind': 'comment', 'target': target, 'account_id': 'me', 'text': '测试评论'}


def test_reservation_already_has_a_command_and_command_failure_rolls_back(store):
    with store.connection() as db:
        db.execute("CREATE TRIGGER reject_command BEFORE INSERT ON commands BEGIN SELECT RAISE(ABORT, 'queue failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match='queue failure'):
        store.reserve_action(action(), 1)
    assert not store.snapshot()['actions']
    with store.connection() as db:
        db.execute('DROP TRIGGER reject_command')
    identity = store.reserve_action(action(), 1)
    restarted = Store(store.path)
    command = restarted.claim('desktop')
    assert command['id'] == store.enqueue('interact', action(), identity)
    assert restarted.claim('another') is None


def test_blocked_capability_does_not_reserve_or_consume_quota(store):
    store.put('block', {'kind': 'comment', 'version': 1})
    with pytest.raises(ValueError, match='暂停'):
        store.reserve_action(action(), 1)
    assert not store.snapshot()['actions']




@pytest.mark.parametrize('receipt', [{'state': 'submitted'}, {'state': 'unknown'}, [{'state': 'confirmed', 'evidence': '回执'}, {'state': 'unknown'}]])
def test_unconfirmed_external_work_is_not_complete(receipt):
    assert describe('publish' if isinstance(receipt, dict) else 'comments', receipt)[0] == 'needs_attention'
