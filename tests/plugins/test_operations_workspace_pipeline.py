"""Two businesses and four topics run the real pipeline with simulated model/web I/O."""
from copy import deepcopy
import json

from plugins.operations.policy import DEFAULT
from plugins.operations.store import Store
from plugins.operations.workspaces import Workspaces, bind_scope


def test_four_topic_pipelines_are_traceable_and_do_not_cross_records(tmp_path, monkeypatch, record_property):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text('development:\n  operations_debug: true\n')
    from agent import auxiliary_client
    from tools import web_tools
    from tests.plugins.test_operations_workflow import fake_model
    from devtools.operations_debug import execute
    def model(**kwargs):
        response = fake_model(**kwargs)
        data = json.loads(kwargs['messages'][1]['content'])
        if 'assets' in data and 'content' not in data:
            from plugins.operations.workspaces import ACTIVE_SCOPE
            content = json.loads(response.choices[0].message.content)
            content['title'] += ACTIVE_SCOPE.get()[1][:6]
            response.choices[0].message.content = json.dumps(content)
        return response
    monkeypatch.setattr(auxiliary_client, 'call_llm', model)
    monkeypatch.setattr(web_tools, 'web_search_tool', lambda *a, **k: json.dumps({'data': {'web': []}}))
    async def extract(urls, **kwargs):
        return json.dumps({'results': [{'content': '原始资料介绍步行路线开放时间，适合整理和核对。'}]})
    monkeypatch.setattr(web_tools, 'web_extract_tool', extract)
    directory = Workspaces()
    original = directory.store()
    policy = deepcopy(DEFAULT)
    policy['limits']['publish'] = 2
    original.configure(policy, 0)
    scopes = []
    for _ in range(2):
        first = directory.create('同名业务')
        scopes.extend([first, directory.create('同名主题', business=first['business_id'])])
    for scope in scopes:
        store = directory.store(scope['business_id'], scope['topic_id'])
        policy = deepcopy(DEFAULT)
        policy.update(enabled=True, topic='步行', goal='路线信息', sources=['https://example.org/walk'], knowledge=['开放时间为九点。'], follow_terms=['步行'])
        policy['allowed'] = {k: True for k in policy['allowed']}
        policy['modules'] = {k: True for k in policy['modules']}
        store.configure(policy, store.policy()[0])
        store.put('asset', {'authorized': True, 'name': '模拟图片.png'}, 'image')
    original_command = Store.command
    submissions = []
    def simulated_web(store, identity):
        command = store.claim('simulated-desktop')
        assert command and command['id'] == identity
        payload = command['payload']
        if command['kind'] == 'account':
            result = {'account_id': store.scope['business_id']}
        elif command['kind'] == 'inbox':
            result = {'items': [{'id': store.scope['id'] + ':' + payload['kind'], 'text': '步行，开放时间？', 'inbound': True, 'follows_me': True}], 'evidence': '模拟网页条目'}
        else:
            submissions.append((store.scope['business_id'], store.scope['id'], payload['kind']))
            result = {'state': 'confirmed', 'evidence': '模拟网页已核对', 'url': 'https://example.org/result'}
        store.acknowledge(identity, 'simulated-desktop', result)
        return original_command(store, identity)
    monkeypatch.setattr(Store, 'command', simulated_web)
    receipts = []
    for scope in scopes:
        with bind_scope(scope['business_id'], scope['topic_id']):
            store = Store()
            store.claim('simulated-desktop', busy=True)
            request = {'task': 'pipeline', 'version': store.policy()[0], 'request_id': 'same-request'}
            result = execute(request)
            assert result['state'] == 'completed', result['detail']
            assert execute(request) == result
            assert store.objects('content')[0]['analysis_context']['industry_id']
            assert len(store.objects('report')) == 1
            assert all(r['topic_id'] == scope['topic_id'] for r in store.objects('source'))
            assert len(store.snapshot()['actions']) == 5
            receipts.append({'scope': scope, 'run': result, 'report': store.objects('report')[0]})
    assert len(submissions) == 20
    assert len({topic for _, topic, _ in submissions}) == 4
    record_property('acceptance', json.dumps(receipts, ensure_ascii=False))
