"""Review settings use the real private plugin mount and do not change operating policy revisions."""
from pathlib import Path
import pytest
from fastapi.testclient import TestClient


def test_review_settings_private_api_and_topic_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME',str(tmp_path))
    from hermes_cli import web_server as ws
    from plugins.operations.store import Store
    from plugins.operations.workspaces import Workspaces
    directory=Workspaces()
    scope=directory.create('审核测试')
    path='/api/plugins/operations/review-policy'
    query={'business_id':scope['business_id'],'topic_id':scope['topic_id']}
    with TestClient(ws.app) as client:
        assert client.get(path,params=query).status_code==401
        client.headers[ws._SESSION_HEADER_NAME]=ws._SESSION_TOKEN
        before=directory.store(query['business_id'],query['topic_id']).policy()
        response=client.get(path,params=query)
        assert response.status_code==200,response.text
        assert response.json()=={'mode':'manual','threshold':85,'revision':0}
        response=client.put(path,params=query,json={'mode':'score','threshold':85,'expected_revision':0})
        assert response.status_code==200,response.text
        assert response.json()['revision']==1
        assert client.put(path,params=query,json={'mode':'manual','threshold':85,'expected_revision':0}).status_code==409
        assert directory.store(query['business_id'],query['topic_id']).policy()==before
        other=directory.create('其他主题',business=scope['business_id'])
        assert client.get(path,params={'business_id':other['business_id'],'topic_id':other['topic_id']}).json()['mode']=='manual'
