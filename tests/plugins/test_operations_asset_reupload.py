"""An explicitly authorized re-upload restores a withdrawn image without duplicating it."""
from io import BytesIO

import pytest
from PIL import Image

from plugins.operations import service
from plugins.operations.workspaces import Workspaces


def test_reupload_restores_asset_and_shared_topic_without_reauthorizing_other_business(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    directory = Workspaces()
    store = directory.store()
    peer = directory.create('同业务主题', business=store.scope['business_id'])
    other = directory.create('其他业务')
    other_store = directory.store(other['business_id'], other['topic_id'])
    image = BytesIO()
    Image.new('RGB', (2, 2), 'white').save(image, format='PNG')
    raw = image.getvalue()
    identity = store.add_asset('荷兰猪.png', raw, True)
    other_store.add_asset('荷兰猪.png', raw, True)
    service.revoke_asset(store, identity)
    service.revoke_asset(other_store, identity)
    with pytest.raises(ValueError):
        store.add_asset('荷兰猪.png', raw, False)
    assert store.objects('asset')[0]['revoked'] is True
    assert store.add_asset('荷兰猪.png', raw, True) == identity
    assert store.add_asset('荷兰猪.png', raw, True) == identity
    original = directory.store(store.scope['business_id'], store.scope['id'])
    for active in (original, directory.store(peer['business_id'], peer['topic_id'])):
        assets = active.objects('asset')
        assert len(assets) == 1
        assert assets[0]['authorized'] is True and not assets[0].get('revoked')
    assert directory.store(other['business_id'], other['topic_id']).objects('asset')[0]['revoked'] is True
