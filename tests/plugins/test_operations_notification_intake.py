"""Read-only notifications share the actual inbox and do not dispatch replies."""
from fastapi import FastAPI
from starlette.testclient import TestClient

from plugins.operations import messages, notification_intake
from plugins.operations.dashboard.message_api import router
from plugins.operations.store import Store


def test_sync_lists_three_categories_and_preserves_direct_messages(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    version, policy = store.policy()
    policy.update(enabled=True, paused=False, topic='主题', goal='收件', account_id='me')
    policy['modules']['comments'] = True
    store.configure(policy, version)
    messages.read_items(store, 'dm', 'me', [{'id': 'old', 'inbound': True}], auto=False, day='2026-11-27')

    def read(owner, kind, payload):
        assert kind == 'inbox' and owner.lease_token
        source = payload['notification_source']
        return {'notification_source': source, 'account_id': 'me',
                'items': [{'id': 'target', 'text': source, 'follows_me': source == 'follow'}]}

    monkeypatch.setattr(notification_intake, 'browser', read)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        for _ in range(2):
            response = client.post('/messages/sync-notifications', json={})
            assert response.status_code == 200, response.text
            assert response.json() == {'reply': 1, 'reaction': 1, 'follow': 1}
        for kind in ('reply', 'reaction', 'follow', 'dm'):
            page = client.get('/messages', params={'source': kind}).json()
            assert [item['kind'] for item in page['items']] == [kind]


def test_platform_order_crosses_pages_and_missing_platform_time_is_last(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    for day in range(28, 0, -1):
        messages.read_items(store, 'reply', 'me', [{'id': str(day), 'platform_time': f'2025-05-{day:02d}',
            'platform_time_sort': day}], auto=False, day='2026-11-27')
    messages.read_items(store, 'follow', 'me', [{'id': 'unknown', 'follows_me': True}], auto=False, day='2026-11-27')
    page = messages.listing(store, account_view=True)
    rest = messages.listing(store, before=page['next'], account_view=True)
    assert [r['target'] for r in page['items'] + rest['items']] == [str(n) for n in range(28, 0, -1)] + ['unknown']
    assert page['items'][0]['platform_time'] == '2025-05-28'
    assert not rest['items'][-1]['platform_time']


def test_platform_clock_prefers_timestamp_and_respects_date_precision():
    from datetime import datetime
    from plugins.operations.message_time import platform_fields

    now = datetime.fromisoformat('2026-01-02T12:17:00+08:00')
    def clock(label, exact=''):
        return platform_fields({'time_label': label, 'time_absolute': exact}, now)

    assert clock('昨天', '2026-01-01T03:25:00Z')['platform_time'] == '2026-01-01 11:25:00'
    assert clock('12-31')['platform_time'] == '2025-12-31'
    assert clock('2025-05-13')['platform_time'] == '2025-05-13'
    assert clock('昨天 9:06')['platform_time'] == '2026-01-01 09:06'
    assert clock('6小时前')['platform_time'] == '约 2026-01-02 06时'
    assert clock('') == {}


def test_receive_again_after_interrupted_read_keeps_account_interlock(tmp_path, monkeypatch):
    from plugins.operations.execution_pause import block
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    version, policy = store.policy()
    policy.update(enabled=True, paused=False, topic='通知', goal='收件', account_id='me')
    policy['modules']['comments'] = True
    store.configure(policy, version)
    command = store.enqueue('inbox', {'kind': 'reaction', 'account_id': 'me', 'notification_source': 'reaction'})
    assert store.claim('viewer')['id'] == command
    store.acknowledge(command, 'viewer', {'state': 'blocked', 'error_code': 'BROWSER_UNAVAILABLE',
        'dispatch_state': 'read_only', 'submitted': False, 'error': '网页执行窗口中断'})
    existing = block(store)

    def read(owner, kind, payload):
        assert kind == 'account' and payload['resume_probe'] and payload['account_id'] == 'me'
        retry = owner.enqueue(kind, payload)
        assert owner.claim('viewer')['id'] == retry
        result = {'state': 'logged_in', 'account_id': 'me', 'notification_source': payload['notification_source'], 'items': []}
        owner.acknowledge(retry, 'viewer', result)
        return result

    monkeypatch.setattr(notification_intake, 'browser', read)
    assert notification_intake.sync(store) == dict.fromkeys(notification_intake.SOURCES, 0)
    assert block(store) == existing


def test_zhihu_sync_merges_three_sources_independently_of_xhs(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    version, policy = store.policy()
    policy.update(enabled=True, paused=False, topic='通知', goal='读取', account_id='xhs-user')
    policy['modules']['comments'] = True
    store.configure(policy, version)
    messages.read_items(store, 'reply', 'xhs-user', [{'id': 'same', 'text': '原评论'}], auto=False, day='2026-11-27')

    def receive(owner, command, payload):
        assert command == 'account' and payload['readonly_inventory'] == 'zhihu_notifications'
        return {'notification_platform': 'zhihu', 'platform_identity': 'zhihu-user',
                'groups': {kind: [{'id': 'same', 'text': kind, 'time_label': '2026-11-26'}]
                           for kind in ('reply', 'reaction', 'follow')}}
    monkeypatch.setattr(notification_intake, 'browser', receive)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        for _ in range(2):
            result = client.post('/messages/sync-notifications', json={'platform': 'zhihu'})
            assert result.json() == {'reply': 1, 'reaction': 1, 'follow': 1}, result.text
        assert client.get('/messages').json()['total'] == 4
        xhs, = client.get('/messages', params={'platform': 'xiaohongshu'}).json()['items']
        assert (xhs['text'], xhs['platform']) == ('原评论', 'xiaohongshu')
        for source in ('reply', 'reaction', 'follow'):
            row, = client.get('/messages', params={'platform': 'zhihu', 'source': source}).json()['items']
            assert (row['kind'], row['platform'], row['platform_time']) == (source, 'zhihu', '2026-11-26')
            assert client.get('/messages/' + row['id']).json()['account'] == 'zhihu-user'
