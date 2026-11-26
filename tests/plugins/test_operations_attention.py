"""Each overview link lists exactly the records behind its badge, across pages."""
import pytest

from plugins.operations import attention, content_library
from plugins.operations.overview import overview
from plugins.operations.policy import local_day
from plugins.operations.store import Store


def test_counts_match_filtered_lists_and_processing_is_topic_local(tmp_path):
    store = Store(tmp_path / 'one.db')
    day = local_day(store.policy()[1])
    for i in range(28):
        store.put('inbox', {'state': 'needs_review', 'kind': 'dm', 'inbound':True, 'id': f'platform-{i}', 'account_id':'me', 'text': str(i)}, f'm{i}')
    store.put('inbox', {'state': 'proposed'}, 'other')
    store.put('content', {'state': 'needs_review'}, 'review')
    store.put('content', {'state': 'needs_material'}, 'material')
    store.put('content', {'state': 'pending_review'}, 'ready')
    with store.connection() as db:
        for name, kind, state in [('note', 'publish', 'unknown'), ('reply', 'reply', 'submitted'), ('done', 'dm', 'confirmed')]:
            db.execute('INSERT INTO actions VALUES (?,?,1,?,?,?,\'{}\',\'{}\',?)', (name, day, kind, name, state, day))
        for name, at, state in [('error', day, 'failed'), ('ok', day, 'completed'), ('old', '2000-01-01', 'failed')]:
            db.execute('INSERT INTO runs VALUES (?,?,\'research\',?,1,?,\'详情\',?,NULL)', (name, at, name, state, at))
    assert overview(store)['pending'] == {'inbox': 28, 'content': 2, 'unverified': 2, 'failed_today': 1}
    page = attention.listing(store, 'inbox')
    older = attention.listing(store, 'inbox', page['next'])
    assert page['total'] == older['total'] == len({r['id'] for r in page['items'] + older['items']}) == 28
    assert {r['id'] for r in attention.listing(store, 'unverified')['items']} == {'note', 'reply'}
    assert [r['id'] for r in attention.listing(store, 'failed_today', day=day)['items']] == ['error']
    assert [r['id'] for r in attention.listing(store, 'failed_today', day='2000-01-01')['items']] == ['old']
    assert {r['id'] for r in content_library.listing(store, filter='needs_work', compact=True)['content']} == {'material', 'review'}

    other = Store(tmp_path / 'two.db')
    with pytest.raises(KeyError):
        attention.handle_inbox(other, 'm0')
    for _ in range(2):
        assert attention.handle_inbox(store, 'm0') == {'state': 'handled'}
    assert overview(store)['pending']['inbox'] == attention.listing(store, 'inbox')['total'] == 27
    with store.connection() as db:
        assert db.execute('SELECT count(*) FROM commands').fetchone()[0] == 0


def test_scoped_inbox_api_and_content_filter(tmp_path, monkeypatch):
    from starlette.testclient import TestClient
    from hermes_cli import web_server
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    scope = {'business_id': store.scope['business_id'], 'topic_id': store.scope['id']}
    store.put('inbox', {'text': '咨询正文','kind':'dm','inbound':True,'account_id':'me','id':'question', 'state': 'needs_review'}, 'dm:/question')
    store.put('content', {'state': 'needs_material', 'title': '待补图'}, 'draft')
    prefix = '/api/plugins/operations'
    with TestClient(web_server.app) as client:
        assert client.get(prefix + '/attention/inbox', params=scope).status_code in (401, 403)
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        def pending():
            return client.get(prefix + '/overview', params=scope).json()['pending']
        assert client.get(prefix + '/attention/inbox', params=scope).json()['total'] == pending()['inbox'] == 1
        assert client.post(prefix + '/attention/inbox/handled', params={**scope, 'topic_id': 'other'},
                           json={'id': 'dm:/question'}).status_code == 404
        assert client.post(prefix + '/attention/inbox/handled', params=scope, json={'id': 'dm:/question'}).json() == {'state': 'handled'}
        assert pending()['inbox'] == 0
        page = client.get(prefix + '/library/content', params={**scope, 'compact': 'true', 'filter': 'needs_work'}).json()
        assert page['counts']['needs_work'] == pending()['content'] == 1
        assert page['content'][0]['id'] == 'draft'
