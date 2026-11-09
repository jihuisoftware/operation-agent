"""Account wake probes and lightweight state reads with isolated real databases."""
import json
import time
import pytest

from plugins.operations.store import Store
from plugins.operations.wake_revalidation import revalidate
from plugins.operations.workspace_broker import poll
from tests.plugins.test_operations_execution_pause import configured


def test_wake_probe_does_not_depend_on_first_topic_plan(tmp_path, monkeypatch):
    store = configured(tmp_path, monkeypatch)
    directory = store.workspace
    directory.create('第二主题', business=store.scope['business_id'])
    topics = directory.catalog()['topics']
    first = directory.store(topics[0]['business_id'], topics[0]['id'])
    with first.connection() as db:
        policy = json.loads(db.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])
        policy.update(enabled=False, paused=True)
        db.execute('UPDATE settings SET data=? WHERE id=1', (json.dumps(policy),))
    body = {'account_id': store.scope['account'], 'worker': 'wake', 'wake_epoch': 'epoch', 'request_id': 'request'}
    one = revalidate(directory, body)
    assert one['state'] == 'checking'
    command = poll(directory, store.scope['account'], 'wake', False, wake_only=True)['command']
    assert command['id'] == one['command_id'] and command['kind'] == 'account'
    assert revalidate(directory, body)['command_id'] == one['command_id']
    owner = directory.store(one['business_id'], one['topic_id'])
    owner.acknowledge(command['id'], 'wake', {'state': 'logged_in', 'account_id': 'account'})
    assert revalidate(directory, body)['state'] == 'ready'
    assert not first.policy()[1]['enabled'] and first.policy()[1]['paused']


def test_paused_workspace_only_claims_read_only_wake_probe(tmp_path, monkeypatch):
    store = configured(tmp_path, monkeypatch)
    directory = store.workspace
    ordinary = store.enqueue('account', {})
    directory.update_state('businesses', store.scope['business_id'], 'pause')
    body = {'account_id': store.scope['account'], 'worker': 'wake', 'wake_epoch': 'epoch', 'request_id': 'request'}
    probe = revalidate(directory, body)
    assert poll(directory, store.scope['account'], 'wake', False)['command'] is None
    command = poll(directory, store.scope['account'], 'wake', False, wake_only=True)['command']
    assert command['id'] == probe['command_id']
    assert store.command(ordinary)['state'] == 'queued'


def test_snapshot_limits_documents_before_decoding(tmp_path):
    store = Store(tmp_path / 'topic.db')
    with store.connection() as db:
        db.execute("INSERT INTO objects VALUES ('old','source','broken historical document','2020-01-01')")
        for index in range(100):
            db.execute('INSERT INTO objects VALUES (?,?,?,?)', (f'source-{index}', 'source', json.dumps({'title': str(index)}), f'2026-11-08T00:00:{index:03}'))
    assert len(store.snapshot()['source']) == 100
    assert store.objects('source', limit=1)[0]['title'] == '99'


def test_online_check_does_not_decode_history_and_expires_heartbeat(tmp_path):
    store = Store(tmp_path / 'topic.db')
    with store.connection() as db:
        db.execute("INSERT INTO objects VALUES ('old','source','broken historical document','2020-01-01')")
        db.execute('INSERT INTO workers VALUES (?,?)', ('worker', time.time()))
    assert store.online()
    with store.connection() as db:
        db.execute('UPDATE workers SET seen=?', (time.time() - 20,))
    assert not store.online()


@pytest.mark.parametrize(('platform', 'content', 'expected'), [
    ('published', 'incomplete', '平台已发布；内容核对不完整'),
    ('published', 'mismatch', '平台已发布；内容不一致'),
    ('reviewing', 'matched', '平台审核中；内容核对一致'),
    ('unknown', 'incomplete', '平台发布状态待确认；内容核对不完整'),
])
def test_publication_summary_separates_platform_and_content(platform, content, expected):
    from plugins.operations.outcomes import describe
    from plugins.operations.publication_status import complete
    from plugins.operations.action_details import issue
    receipt = {'state': 'submitted', 'evidence': 'platform receipt',
               'publication': {'execution': 'verified', 'platform': platform, 'content': content}}
    state, detail = describe('publish', receipt)
    assert state == 'needs_attention' and expected in detail
    assert '不重新发布' in detail
    row = {'state': 'submitted', 'result': receipt}
    assert not complete(row)
    if platform == 'published' and content == 'incomplete':
        assert issue(row)['title'] == '平台已发布，内容仍待核对'
