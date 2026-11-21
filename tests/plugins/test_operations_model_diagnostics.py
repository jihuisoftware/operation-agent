"""Output failures retain bounded local evidence without retrying or accepting bad JSON."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest

from plugins.operations import model
from plugins.operations.model_errors import ModelOutputError
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.store import Store


@pytest.mark.parametrize('debug', [False, True])
def test_invalid_json_records_coordinates_and_redacted_evidence(tmp_path, monkeypatch, debug):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    if debug:
        store.debug_id = 'debug:diagnostics'
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='诊断', goal='保留失败证据')
    policy['modules']['content'] = True
    store.configure(policy, 0)
    day = local_day(policy)
    run = store.start_run(day, 'content', 'test', 1)
    raw = '  \n```json\n{"title":"中文",\n"api_key":"sk-test-secret-123456789012345678901234",\n"body": }\n```'
    seen = []

    def provider(**kwargs):
        seen.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=raw), finish_reason='length')], usage=None)

    monkeypatch.setattr('agent.auxiliary_client.call_llm', provider)
    with pytest.raises(ModelOutputError, match='第3行'):
        model.generate(store, policy, day, '生成', {})
    with store.connection() as db:
        events = [json.loads(row[0]) for row in db.execute("SELECT data FROM events WHERE kind='model_output_error'")]
    assert len(seen) == len(events) == 1
    event = events[0]
    assert event['run_id'] == run and event['budget_id']
    assert event['finish_reason'] == 'length'
    assert event['parse_error']['line'] == 3 and event['parse_error']['column'] == 9
    assert event['parse_error']['raw_offset'] == raw.index('}', raw.index('"body"'))
    assert event['parse_error']['raw_line'] == 5
    assert event['response_sha256'] == hashlib.sha256(raw.encode()).hexdigest()
    assert event['response_redacted'] and not event['response_truncated']
    assert 'sk-test-secret' not in json.dumps(event)
    assert '"body": }' in event['raw_response']
    assert not store.objects('content')
    if debug:
        trace = store.objects('model_trace')[0]
        assert trace['finish_reason'] == 'length' and trace['diagnostics']['parse_error'] == event['parse_error']
        assert 'sk-test-secret' not in json.dumps(trace)
    else:
        assert not store.objects('model_trace')


@pytest.mark.parametrize('raw', ['x' * 20000, 'x' * 140000, '', None, '[]', '```'],
                         ids=['long', 'oversized', 'empty', 'non-text', 'array', 'fence'])
def test_other_invalid_outputs_are_bounded_and_do_not_invent_parse_positions(tmp_path, monkeypatch, raw):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='诊断', goal='有界证据')
    policy['modules']['content'] = True
    store.configure(policy, 0)
    monkeypatch.setattr('agent.auxiliary_client.call_llm', lambda **kwargs: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=raw))], usage=None))
    with pytest.raises(ModelOutputError):
        model.generate(store, policy, local_day(policy), '生成', {})
    with store.connection() as db:
        event = json.loads(db.execute("SELECT data FROM events WHERE kind='model_output_error'").fetchone()[0])
    assert event['finish_reason'] is None
    assert len(event.get('raw_response') or '') <= 16450
    if raw is None or raw in ('[]', '```'):
        assert 'parse_error' not in event
    if isinstance(raw, str) and len(raw) > 16384:
        assert event['response_truncated']
    if isinstance(raw, str) and len(raw) > 131072:
        assert event['raw_response'] is None and event['response_evidence_omitted'] == 'oversized'
