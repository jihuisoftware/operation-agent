"""Takeover follows its live window; stale owners must not block all account topics."""
from copy import deepcopy
import time

import pytest

from plugins.operations import readiness
from plugins.operations.policy import DEFAULT
from plugins.operations.store import Store
from plugins.operations.workspace_broker import poll
from plugins.operations.workspace_execution import check_running
from plugins.operations.workspaces import Workspaces


def configured(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    directory = Workspaces()
    store = directory.store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='接管状态', goal='验证窗口归属')
    policy['modules']['comments'] = True
    store.configure(policy, 0)
    return directory, store


def test_expired_account_takeover_is_released_without_unpausing_plan(tmp_path, monkeypatch):
    directory, store = configured(tmp_path, monkeypatch)
    readiness.takeover(store, 'closed-window', True)
    with directory.connection() as db:
        db.execute('UPDATE account_holds SET seen=?', (time.time() - 3600,))
    with store.connection() as db:
        assert not readiness.web_held(db)
    check_running(store, web=True)
    with directory.connection() as db:
        assert db.execute('SELECT held FROM accounts').fetchone()[0] == 0
        assert not db.execute('SELECT 1 FROM account_holds').fetchone()
    version, policy = store.policy()
    store.configure({**policy, 'paused': True}, version)
    readiness.takeover(store, 'current-window', False)
    assert store.policy()[1]['paused']


def test_heartbeat_keeps_live_owner_and_release_cannot_be_undone_by_late_poll(tmp_path, monkeypatch):
    directory, store = configured(tmp_path, monkeypatch)
    account = store.scope['account']
    readiness.takeover(store, 'owner', True)
    response = poll(directory, account, 'owner', True, takeover=True)
    assert response['takeover'] == {'held': True, 'owned': True}
    with pytest.raises(ValueError, match='另一执行窗口'):
        readiness.takeover(store, 'other-window', False)
    other = poll(directory, account, 'other-window', False, takeover=False)
    assert other['takeover'] == {'held': True, 'owned': False}
    readiness.takeover(store, 'owner', False)
    late = poll(directory, account, 'owner', True, takeover=True)
    assert late['takeover'] == {'held': False, 'owned': False}
    with store.connection() as db:
        assert not readiness.web_held(db)


def test_account_conflict_is_not_reported_as_manual_takeover(tmp_path, monkeypatch):
    from plugins.operations.readiness import web_block_reason
    directory, store = configured(tmp_path, monkeypatch)
    with directory.connection() as db:
        db.execute("UPDATE accounts SET conflict='duplicate'")
    with store.connection() as db:
        assert readiness.web_held(db)
        assert '账号' in web_block_reason(db) and '人工接管' not in web_block_reason(db)


def test_legacy_hold_expires_after_its_window_disappears(tmp_path):
    store = Store(tmp_path / 'legacy.db')
    readiness.takeover(store, 'closed-window', True)
    with store.connection() as db:
        db.execute("UPDATE objects SET data=json_set(data,'$.seen',?),created='2000-01-01T00:00:00+00:00' WHERE kind='web_hold'", (time.time() - 3600,))
        db.execute('UPDATE workers SET seen=?', (time.time() - 3600,))
        assert not readiness.web_held(db)
