"""Direct page navigation keeps search totals and existing cursor reads consistent."""
from starlette.testclient import TestClient


def test_source_pages_search_bounds_and_cursor_compatibility(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    from plugins.operations.store import Store
    from hermes_cli import web_server
    store = Store()
    for index in range(49):
        store.put('source', {'title': f'资料{index}', 'text': '匹配' if index < 25 else '其他'}, f's{index}')
    with TestClient(web_server.app) as client:
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        def read(**params):
            response = client.get('/api/plugins/operations/sources', params=params)
            assert response.status_code == 200, response.text
            return response.json()
        first = read(page=1)
        last = read(page=3)
        middle = read(page=2)
        assert (first['total'], first['total_pages'], first['page']) == (49, 3, 1)
        assert [row['id'] for row in last['items']] == ['s0']
        assert len(middle['items']) == 24 and middle['items'][0]['id'] == 's24'
        assert read(cursor=first['next_cursor'])['items'] == middle['items']
        assert read(page=999)['items'] == last['items']
        filtered = read(page=3, q='匹配')
        assert (filtered['total'], filtered['total_pages'], filtered['page']) == (25, 2, 2)
        empty = read(page=3, q='没有这个词')
        assert (empty['total'], empty['total_pages'], empty['page'], empty['items']) == (0, 1, 1, [])
        assert client.get('/api/plugins/operations/sources?page=0').status_code == 422
