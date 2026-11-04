"""One-run production grants cannot be borrowed by ordinary work or survive owner changes."""
from copy import deepcopy
import shutil

import pytest

from devtools.operations_authorization import create
from devtools.operations_debug import DebugStore, new_record
from plugins.operations.debug_authorization import grant_id
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.store import Store
from plugins.operations.workspaces import Workspaces


def active(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = DebugStore('debug:once')
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='实测授权', goal='验证单次范围')
    policy['modules']['comments'] = True
    policy['allowed'] = dict.fromkeys(policy['allowed'], False)
    store.configure(policy, 0)
    assert store.lease(store.debug_id)
    data = new_record(store.debug_id, 'comment', '主动评论', 1, local_day(policy))
    data.update(mode='quick', action_mode='execute_once')
    store.put('debug_run', data, data['id'])
    store.manual_run_id = data['id']
    create(store, data)
    store.start_run(data['day'], 'comments', data['id'], 1)
    return store


def test_ordinary_work_cannot_borrow_an_active_debug_grant(tmp_path, monkeypatch):
    store = active(tmp_path, monkeypatch)
    normal = Store(store.path, workspace=store.workspace, scope=store.scope)
    forged = {'kind': 'comment', 'target': 'target', 'account_id': 'me', 'text': '评论',
              'debug_authorization': grant_id(store.debug_id), 'manual_run_id': store.debug_id}
    with pytest.raises(ValueError, match='未授权'):
        normal.reserve_action(forged, 1)
    with pytest.raises(ValueError, match='授权已失效'):
        store.reserve_action({**forged, 'kind': 'reply'}, 1)
    assert not store.snapshot()['actions']


@pytest.mark.parametrize('change', ('lease', 'account', 'policy'))
def test_grant_is_invalid_after_lease_account_or_policy_changes(tmp_path, monkeypatch, change):
    store = active(tmp_path, monkeypatch)
    if change == 'lease':
        store.release(store.debug_id)
    elif change == 'account':
        from plugins.operations.workspace_execution import link_account
        other = store.workspace.create('其他业务')
        account = store.workspace.resolve(other['business_id'], other['topic_id'])['account']
        link_account(store.workspace, store.scope['business_id'], account)
    else:
        version, policy = store.policy()
        store.configure({**policy, 'paused': True}, version)
    with pytest.raises(ValueError):
        store.reserve_action({'kind': 'comment', 'target': 'target', 'account_id': 'me', 'text': '评论'}, store.policy()[0])
    assert not store.snapshot()['actions']


def test_copied_workspace_cannot_dispatch_the_original_grant(tmp_path, monkeypatch):
    store = active(tmp_path, monkeypatch)
    identity = store.reserve_action({'kind': 'comment', 'target': 'target', 'account_id': 'me', 'text': '评论'}, 1)
    clone = tmp_path / 'cloned-workspace'
    shutil.copytree(store.workspace.root, clone)
    directory = Workspaces(clone)
    copied = directory.store(store.scope['business_id'], store.scope['id'])
    assert copied.claim('other-profile-worker') is None
    with copied.connection() as db:
        assert db.execute('SELECT state FROM actions WHERE id=?', (identity,)).fetchone()[0] == 'cancelled'
    with store.connection() as db:
        assert db.execute('SELECT state FROM actions WHERE id=?', (identity,)).fetchone()[0] == 'queued'
