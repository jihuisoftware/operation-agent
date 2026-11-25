"""A publish decision belongs to one running worker and the saved plan version."""
import json
import time

import pytest

from plugins.operations import model
from plugins.operations.policy import validate_policy
from plugins.operations.publish_decision import choose
from plugins.operations.store import Store


def test_saved_publish_method_controls_worker_decision(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store(tmp_path / 'topic.db')
    version, policy = store.policy()
    assert validate_policy({})['publish_method'] == 'normal'
    with pytest.raises(ValueError, match='发布方式'):
        validate_policy({'publish_method': 'other'})
    policy.update(publish_method='computer_use', enabled=True, topic='话题', goal='目标')
    policy['modules']['publish'] = True
    version = store.configure(policy, version)
    with store.connection() as db:
        db.execute("INSERT INTO commands VALUES ('c', NULL, 'publish', ?, 'running', 'owner', ?, '{}')",
                   (json.dumps({'policy_version': version}), time.time() + 60))
    calls = []
    def generate(store, policy, day, instruction, data):
        calls.append(data)
        return {'action': 'entry'}
    monkeypatch.setattr(model, 'generate', generate)
    body = {'command_id': 'c', 'worker': 'owner', 'controls': ['entry'], 'turn': 1}
    with pytest.raises(ValueError, match='当前执行窗口'):
        choose(store, {**body, 'worker': 'other'})
    assert choose(store, body) == {'action': 'entry'}
    with pytest.raises(ValueError, match='已请求过'):
        choose(store, body)
    store.configure({**policy, 'publish_method': 'normal'}, version)
    with pytest.raises(ValueError, match='规则已变更'):
        choose(store, {**body, 'turn': 2})
    assert len(calls) == 1
