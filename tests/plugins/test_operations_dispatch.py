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


def test_readonly_timeout_does_not_permanently_pause_interactions(store):
    command_id = store.enqueue('inbox', {'kind': 'reply', 'account_id': 'me'})
    assert store.claim('desktop')['id'] == command_id
    store.acknowledge(command_id, 'desktop', {'state': 'blocked', 'submitted': False,
        'error_code': 'PAGE_NOT_READY', 'error': '等待网页就绪超时，未执行后续提交'})
    assert not store.blocked('reply', 1)
    retry = store.enqueue('inbox', {'kind': 'reply', 'account_id': 'me'})
    assert retry != command_id


def test_legacy_proven_pre_submit_timeout_can_recover_but_unknown_blocks_stay(store):
    from plugins.operations.browser_evidence import record_step
    identity = store.reserve_action(action(), 1)
    command = store.claim('desktop')
    error = 'interaction：等待网页就绪超时，未执行后续提交'
    record_step(store, command['id'], 'desktop', {'sequence': 1, 'phase': 'started', 'name': 'prepare_interaction'})
    record_step(store, command['id'], 'desktop', {'sequence': 1, 'phase': 'failed', 'name': 'prepare_interaction', 'error': error})
    store.acknowledge(command['id'], 'desktop', {'state': 'blocked', 'error': error})
    store.put('block', {'kind': 'comment', 'version': 1, 'error': error}, 'legacy-block')
    assert not store.blocked('comment', 1)
    assert store.snapshot()['actions'][0]['id'] == identity
    store.put('block', {'kind': 'comment', 'version': 1, 'error': '未能确认是否已经提交'}, 'uncertain-block')
    assert store.blocked('comment', 1)


def test_submit_evidence_prevents_readiness_error_from_clearing_a_block(store):
    from plugins.operations.browser_evidence import record_step
    store.reserve_action(action(), 1)
    command = store.claim('desktop')
    record_step(store, command['id'], 'desktop', {'sequence': 1, 'phase': 'started', 'name': 'submit_interaction'})
    store.acknowledge(command['id'], 'desktop', {'state': 'blocked', 'submitted': False,
        'error_code': 'PAGE_NOT_READY', 'error': '等待网页就绪超时，未执行后续提交'})
    assert store.blocked('comment', 1)
