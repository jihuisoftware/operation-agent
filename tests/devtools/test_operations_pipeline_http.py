"""Full private-HTTP workflow with real storage/claims and simulated providers/Desktop receipts."""
import base64
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from starlette.testclient import TestClient

from plugins.operations.policy import DEFAULT
from tests.plugins.operations_support import organized_response
from tests.waiting import wait_until


def model(**kwargs):
    data = json.loads(kwargs['messages'][1]['content'])
    if data.get('task') == 'industry_analysis':
        from tests.plugins.operations_support import industry_response as finding
        result = finding(data)
    elif data.get('task') == 'organize_sources':
        result = organized_response(data)
    elif 'candidates' in data:
        result = {'actions': [{'id': data['candidates'][0]['id'], 'text': '开放时间为九点。', 'knowledge_ids': [0]}]}
    elif 'content' in data:
        result = {'pass': True, 'reason': '来源与授权图片一致'}
    elif 'assets' in data:
        result = {'title': '步行路线', 'body': '开放时间为九点。', 'asset_ids': [data['assets'][0]['id']],
                  'source_ids': [data['sources'][0]['id']]}
    else:
        result = {'topics': [{'title': '步行路线', 'reason': '有可追溯资料', 'source_ids': [data['sources'][0]['id']]}]}
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(result)))], usage=None)


def providers(monkeypatch):
    from tools import web_tools
    from agent import auxiliary_client
    monkeypatch.setattr(web_tools, 'web_search_tool', lambda *a, **k: '{"data":{"web":[]}}')
    async def extract(*args, **kwargs):
        return json.dumps({'results': [{'title': '步行开放资料', 'content': '步行路线开放时间为九点。', 'author': '模拟资料作者'}]})
    monkeypatch.setattr(web_tools, 'web_extract_tool', extract)
    monkeypatch.setattr(auxiliary_client, 'call_llm', model)


def test_blueprint_to_report_through_authenticated_profile_http(tmp_path, monkeypatch, record_property):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    dev = tmp_path / 'profiles' / 'acceptance'
    dev.mkdir(parents=True)
    for home in (tmp_path, dev):
        (home / 'config.yaml').write_text('development:\n  operations_debug: true\n')
    providers(monkeypatch)
    from hermes_cli import web_server
    with TestClient(web_server.app) as client:
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        trace = []
        def request(method, path, body=None):
            response = client.request(method, '/api/plugins/operations' + path, params={'profile': 'acceptance'}, json=body)
            assert response.status_code == 200, response.text
            result = response.json() if 'application/json' in response.headers.get('content-type', '') else response.text
            if path != '/worker/poll' or result.get('command'):
                trace.append({'method': method, 'path': path, 'result': result})
            return result
        policy = deepcopy(DEFAULT)
        policy.update(enabled=True, topic='步行', goal='整理路线信息并运营测试号', account_id='me',
                      sources=['https://example.org/walk'], knowledge=['开放时间为九点。'], follow_terms=['步行'])
        policy['modules'] = {key: True for key in policy['modules']}
        policy['allowed'] = {key: True for key in policy['allowed']}
        catalog = request('GET', '/blueprints')
        cover = BytesIO()
        Image.new('RGB', (32, 32), 'white').save(cover, format='PNG')
        asset = request('POST', '/assets', {'name': '原创测试封面.png', 'data': base64.b64encode(cover.getvalue()).decode(), 'authorized': True})
        applied = request('POST', '/blueprints/apply', {
            'version': catalog['version'], 'policy': policy, 'request_id': 'apply-acceptance', 'mode': 'enable'})
        version = applied['version']
        request('POST', '/worker/poll', {'worker': 'simulated-desktop', 'busy': True})
        body = {'task': 'pipeline', 'version': version, 'request_id': 'http-acceptance'}
        commands = []
        live_seen = set()
        def pump():
            response = request('POST', '/worker/poll', {'worker': 'simulated-desktop'})
            command = response['command']
            if command:
                commands.append(command)
                live = request('GET', '/debug/debug:http-acceptance')
                live_seen.update(step['id'] for step in live['run']['steps'] if step['state'] == 'running')
                payload = command['payload']
                assert payload['policy_version'] == version
                if command['kind'] == 'inbox':
                    answer = {'items': [{'id': payload['kind'] + ':1', 'text': '步行，开放时间？', 'inbound': True, 'follows_me': True}]}
                else:
                    assert payload['account_id'] == 'me'
                    if command['kind'] == 'publish':
                        assert payload['content']['asset_ids'] == [asset['id']]
                        picture = request('GET', '/assets/' + asset['id'])
                        assert base64.b64decode(picture['data']) == cover.getvalue()
                    answer = {'state': 'published' if command['kind'] == 'publish' else 'confirmed',
                              'evidence': '模拟桌面核对成功', 'url': 'https://example.org/result'}
                request('POST', '/worker/ack', {'id': command['id'], 'worker': 'simulated-desktop', 'result': answer})
            return pending.done()
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(request, 'POST', '/debug/run', body)
            wait_until(pump, timeout=60, interval=0.02, what='完整运营 HTTP 链路完成')
            result = pending.result(timeout=5)
        detail = request('GET', '/debug/' + result['id'])
        report = request('GET', '/reports/' + result['day'])
        record_property('acceptance', json.dumps({'mode': 'simulated', 'detail': detail, 'http_trace': trace, 'report': report}, ensure_ascii=False))
        assert result['state'] == 'completed', result['detail']
        assert all(step['state'] == 'completed' for step in result['steps'])
        assert result['external_actions'] == {'total': 5, 'confirmed': 5}
        assert live_seen >= {'publish', 'comment', 'reply', 'dm', 'follow'}
        assert len(request('GET', '/sources')['items']) == 1
        assert request('GET', '/organized-sources')['usable'] == 1
        assert '已核对成功 5 次' in report
        published = next(command for command in commands if command['kind'] == 'publish')
        assert published['payload']['content']['id'] == result['content_id']
        assert published['payload']['content']['organization_ids']
        assert request('POST', '/debug/run', body) == result
        assert request('POST', '/worker/poll', {'worker': 'simulated-desktop'})['command'] is None
        assert client.get('/api/plugins/operations/debug/' + result['id']).status_code == 404
        assert client.get('/api/plugins/operations/state').json()['policy']['topic'] == ''
