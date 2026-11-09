"""Daily source settings preserve usage and respect topic/Profile boundaries."""
import pytest
from starlette.testclient import TestClient

from plugins.operations import collection_settings
from plugins.operations.collection_ledger import save as save_record
from plugins.operations.policy import local_day
from plugins.operations.store import Store


def test_limit_save_preserves_usage_and_other_rules_and_rejects_stale_writes(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    version, before = store.policy()
    day = local_day(before)
    save_record(store, 'collection_budget', 'collection-budget:' + day, {'day': day, 'used': 180})
    updated = collection_settings.save(store, {'version': version, 'limit': 100})
    assert updated['limit'] == 100 and updated['used'] == 180 and updated['remaining'] == 0
    assert updated['shared_limit'] == 100
    _, after = store.policy()
    assert after == {**before, 'limits': {**before['limits'], 'source': 100}}
    assert not store.snapshot()['runs'] and not store.objects('quick_run')
    with pytest.raises(ValueError, match='配置已变更'):
        collection_settings.save(store, {'version': version, 'limit': 1000})
    for invalid in (99, 10001, True, 100.5, '500'):
        with pytest.raises(ValueError, match='100到10000'):
            collection_settings.save(store, {'version': updated['version'], 'limit': invalid})
    assert collection_settings.save(store, {'version': updated['version'], 'limit': 10000})['limit'] == 10000


def test_multiple_topics_do_not_silently_raise_shared_limit(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    first = Store()
    initial = collection_settings.save(first, {'version': first.policy()[0], 'limit': 100})
    directory = first.workspace
    created = directory.create('另一个主题', business=first.scope['business_id'])
    other = directory.store(created['business_id'], created['topic_id'])
    old_other = other.policy()
    updated = collection_settings.save(first, {'version': initial['version'], 'limit': 10000})
    assert updated['shared_limit'] == 100 and updated['remaining'] == 100
    assert other.policy() == old_other


def test_private_settings_endpoint_requires_auth_and_owning_topic(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text('{}')
    from hermes_cli import web_server
    path = '/api/plugins/operations/collection-budget'
    with TestClient(web_server.app) as client:
        assert client.get(path).status_code in (401, 403)
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        scope = client.post('/api/plugins/operations/workspaces', json={'action': 'create', 'name': '采集设置'}).json()
        initial = client.get(path, params=scope).json()
        saved = client.put(path, params=scope, json={'version': initial['version'], 'limit': 500})
        assert saved.status_code == 200 and saved.json()['limit'] == 500
        assert client.get(path, params=scope).json()['limit'] == 500
        assert client.get(path, params={**scope, 'topic_id': 'foreign'}).status_code == 404
        assert client.put(path, params=scope, json={'version': saved.json()['version'], 'limit': 50}).status_code == 400
