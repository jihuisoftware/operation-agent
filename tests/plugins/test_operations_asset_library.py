"""图片素材按仍可见的图片分页。"""
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from plugins.operations.dashboard.library_api import router
from plugins.operations.store import Store


@pytest.mark.parametrize('visible_count', [7, 100, 101])
def test_asset_pages_count_only_visible_images(tmp_path, monkeypatch, visible_count):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    visible = [f'image-{index}' for index in range(visible_count)]
    with store.connection() as db:
        db.executemany("INSERT INTO objects VALUES (?, 'asset', ?, '2026-11-20')",
                       [(identity, '{}') for identity in visible] +
                       [(f'removed-{index}', '{"revoked":true}') for index in range(100)])

    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        newest = client.get('/library/assets').json()
        expected = visible[::-1]
        assert [image['id'] for image in newest['asset']] == expected[:100]
        if visible_count > 100:
            older = client.get('/library/assets', params={'before': newest['next']}).json()
            assert [image['id'] for image in older['asset']] == expected[100:]
            assert older['next'] is None
        else:
            assert newest['next'] is None


def test_design_candidates_remain_readable_without_entering_asset_library(tmp_path, monkeypatch):
    from base64 import b64decode
    from io import BytesIO
    from PIL import Image
    from plugins.operations.content_cover import ensure_cover
    from plugins.operations.dashboard.plugin_api import router as operations_router

    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    photo = BytesIO()
    Image.new('RGB', (3, 3), 'green').save(photo, format='PNG')
    photo_id = store.add_asset('生活照.png', photo.getvalue(), True)
    draft = ensure_cover(store, {'title': '荷兰猪日常', 'asset_ids': []})
    app = FastAPI()
    app.include_router(operations_router)
    with TestClient(app) as client:
        assert [item['id'] for item in client.get('/library/assets').json()['asset']] == [photo_id]
        expected = {item['asset_id'] for item in draft['cover_candidates']}
        covers = client.get('/library/assets', params={'filter': 'covers'})
        assert covers.status_code == 200, covers.text
        assert {item['id'] for item in covers.json()['asset']} == expected
        for candidate in draft['cover_candidates']:
            url = '/assets/' + candidate['asset_id']
            assert client.get(url, params={'thumbnail': True}).status_code == 200
            assert Image.open(BytesIO(b64decode(client.get(url).json()['data']))).size == (1080, 1440)
