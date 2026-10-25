"""Diagnostic-only metadata survives the canonical FIFO, without inference."""
from types import SimpleNamespace

import pytest

from gateway.config import GatewayConfig
from gateway.platforms.event import MessageEvent
from gateway.run import GatewayRunner
from gateway.session_authority import SessionAuthority, initialize_session_authority
from gateway.session_contract import Principal
from hermes_state_runtime import RuntimeStoreError, get_session_admission, list_session_admissions


async def _authority(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    monkeypatch.setattr(SessionAuthority, '_schedule', lambda self, ref: None)
    monkeypatch.setattr('gateway.session_bot._watch_reply', lambda *args: None)
    runner = GatewayRunner(GatewayConfig(sessions_dir=tmp_path / 'sessions'))
    from hermes_state import SessionDB
    db = SessionDB(tmp_path / 'state.db')
    runner.session_store._db = db
    runner._session_db = db
    authority = await initialize_session_authority(runner, profile_id='default', instance_id='category-fixture',
                                                  db=db)
    return runner, authority


def test_live_delivery_forwards_diagnostic_category(tmp_path, monkeypatch):
    from tools import bot_live_delivery as live
    calls = []
    monkeypatch.setattr(live, 'authority_delivery', lambda home, params: calls.append(params) or {})
    owner = dict(profile_home=str(tmp_path), session_id='bot', canonical=True,
                 lease_id='fixture', live_session_id='bot')
    live.deliver_to_live_owner(tmp_path, owner, 'warning', notification_category='diagnostic')
    assert calls[0]['notification_category'] == 'diagnostic'


@pytest.mark.asyncio
@pytest.mark.parametrize('category', ['result', 'diagnostic'])
async def test_bot_category_is_committed_restored_and_part_of_retry_identity(tmp_path, monkeypatch, category):
    from gateway.session_bot import deliver
    from gateway.session_local import create_local_session
    from gateway.session_local_title import title_new_session
    from gateway.session_automation import restore_local_automation
    _runner, authority = await _authority(tmp_path, monkeypatch)
    actor = Principal('test-owner', 'default', frozenset({'session:create', 'session:submit', 'session:read'}), 'fixture')
    try:
        ref = create_local_session(authority, actor, dict(request_id='bot', source='gui', model='fixture', toolsets=[]))
        title_new_session(authority, ref, 'Bot Chat')
        connection = SimpleNamespace(authority=authority, actor=actor)
        params = dict(id='a' * 32, profile='default', message='notice', notification_category=category)
        first = await deliver(connection, params)
        retry = await deliver(connection, params)
        assert first['admission_id'] == retry['admission_id']
        # Poll the owner's local projection, then explicitly retry its immutable envelope.
        from tools import bot_live_delivery as live
        monkeypatch.setattr(live, 'authority_delivery', lambda *a: pytest.fail('receipt poll opened RPC'))
        replay = live.read_delivery_result(tmp_path, params['id'])
        assert replay is not None
        assert replay.get('notification_category', 'result') == category
        repeated = dict(id=replay['delivery_id'], profile='default', message=replay['message'],
                        notification_category=replay.get('notification_category', 'result'))
        assert (await deliver(connection, repeated))['admission_id'] == first['admission_id']
        row = get_session_admission(authority.db, admission_id=first['admission_id'])
        assert row is not None
        descriptor = row['payload']['local_automation_v1']
        restored = restore_local_automation(authority, ref, row)
        if category == 'diagnostic':
            assert descriptor['notification_category'] == 'diagnostic'
            assert restored.metadata['notification_category'] == 'diagnostic'
        else:
            assert 'notification_category' not in descriptor
            assert 'notification_category' not in restored.metadata
            # Omitted default retains the old request fingerprint.
            assert (await deliver(connection, {k: v for k, v in params.items() if k != 'notification_category'}))['admission_id'] == first['admission_id']
        with pytest.raises(RuntimeStoreError, match='admission_conflict'):
            await deliver(connection, {**params, 'notification_category': 'result' if category == 'diagnostic' else 'diagnostic'})
        assert len(list_session_admissions(authority.db, session_id=ref.session_id, pending_only=False)) == 1
    finally:
        authority.db.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('category', [None, [], {}, 'other'])
async def test_bot_invalid_category_refuses_before_admission(tmp_path, monkeypatch, category):
    from gateway.session_bot import deliver
    _runner, authority = await _authority(tmp_path, monkeypatch)
    actor = Principal('test-owner', 'default', frozenset({'session:submit'}), 'fixture')
    try:
        with pytest.raises(RuntimeStoreError, match='invalid_params'):
            await deliver(SimpleNamespace(authority=authority, actor=actor),
                          dict(id='a' * 32, profile='default', message='notice', notification_category=category))
        assert authority.db.get_session_by_title('Bot Chat') is None
    finally:
        authority.db.close()


@pytest.mark.asyncio
async def test_display_kind_is_a_closed_producer_set(tmp_path, monkeypatch):
    """Only gateway-produced notice kinds ride an automation admission; anything else refuses."""
    from gateway.response_filters import display_kind_for_event, display_metadata_for_event
    from gateway.session_automation import automation_display_metadata
    trusted = {'display_kind': 'process_complete', 'display_text': 'Background Process Finished: true'}
    assert automation_display_metadata(trusted) == trusted
    event = MessageEvent(text='notice', internal=True, metadata=dict(trusted))
    assert display_kind_for_event(event) == 'process_complete'
    assert display_metadata_for_event(event) == {'display_text': trusted['display_text']}
    assert display_kind_for_event(MessageEvent(text='x', metadata=dict(trusted))) is None
    for bad in ({'display_kind': 'hidden', 'display_text': 'x'}, {'display_kind': 'process_complete'},
                {'display_text': 'x'}, {'display_kind': 'process_complete', 'display_text': ''},
                {'display_kind': 'process_complete', 'display_text': 'x' * 2001}):
        with pytest.raises(RuntimeStoreError, match='invalid_params'):
            automation_display_metadata(bad)




_SOURCE = dict(chat_id='42', chat_type='dm', user_id='42', user_name='human')










