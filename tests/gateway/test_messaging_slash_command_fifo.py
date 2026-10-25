"""A slash command that becomes a turn (``/queue``, ``/steer``, ``/plan``, a skill) joins the chat's
durable FIFO like text, so it runs after the turns already admitted, never inside the running one.

Real GatewayRunner, DiscordAdapter, SessionAuthority and drain over SQLite. The turn body
(``_handle_message_with_agent``) is a stand-in; the running turn calls the real post-run drain
step ``_run_agent_drain_pending``, so anything left in the in-process slot shows up "inside A".
"""
from types import SimpleNamespace

import pytest





class _Agent:
    interrupted = False

    def interrupt(self, *args, **kwargs):
        self.interrupted = True


def _skill(monkeypatch):
    """One installed skill, ``/demo``, without a skills directory."""
    import agent.skill_bundles as bundles
    import agent.skill_commands as skills
    from agent import skill_utils

    monkeypatch.setattr(skills, 'get_skill_commands', lambda: {'/demo': {'name': 'demo'}})
    monkeypatch.setattr(skills, 'resolve_skill_command_key', lambda command, **_: '/demo' if command == 'demo' else None)
    monkeypatch.setattr(skills, 'split_stacked_skill_commands', lambda rest, **_: ([], rest))
    monkeypatch.setattr(skills, 'build_skill_invocation_message', lambda key, text='', **_: f'[demo skill] {text}')
    monkeypatch.setattr(bundles, 'resolve_bundle_command_key', lambda command: None)
    monkeypatch.setattr(skill_utils, 'get_disabled_skill_names', lambda **_: set())




def _rows(rig):
    from hermes_state_runtime import list_session_admissions
    sid = rig.runner.session_store.peek_session_id(rig.key)
    return [row['request_id'] for row in list_session_admissions(rig.authority.db, session_id=sid, pending_only=False)]












@pytest.mark.asyncio
@pytest.mark.parametrize('command', ['/queue C', '/steer C'])  # no agent can steer: the queue fallback
async def test_queued_turn_keeps_the_relay_callback(monkeypatch, command):
    """The rebuilt turn carries the command's authenticated relay callback, so a relay-fronted chat
    can queue; the strict identity check in ``capture_provenance`` still holds."""
    from pathlib import Path
    from unittest.mock import AsyncMock
    from gateway import session_ingress_context as ctx
    from gateway.config import Platform
    from gateway.platforms.event import MessageEvent, MessageType
    from gateway.run_busy import GatewayBusySessionMixin
    from gateway.session import SessionSource

    accepted, transport, home = [], object(), Path.cwd()

    class Runner(GatewayBusySessionMixin):
        session_authority = SimpleNamespace(route_epoch=lambda route: 0)

        def _peek_session_state(self, key):
            return None

        def _delivery_adapter_for(self, source):
            return adapter

        def _queue_depth(self, *args, **kwargs):
            return 0
    runner = Runner()

    async def handler(event):  # the observer's message handler: native callback, then provenance
        with ctx.native_callback(runner, event, home):
            ctx.capture_provenance(runner, event)
        accepted.append(event.text)
    adapter = SimpleNamespace(_transport=transport, _background_tasks=set(), gateway_runner=None, name='relay',
                              _message_handler=handler, _release_turn_marker=AsyncMock(),
                              _unwrap_ephemeral=lambda response: (response, 0))
    monkeypatch.setattr(ctx, '_binding', lambda *a: (adapter, home, home, {'relay': 'seal'}))
    source = SessionSource(platform=Platform.TELEGRAM, chat_id='42', user_id='42', chat_type='dm',
                           delivered_via_upstream_relay=True)
    original = MessageEvent(text=command, message_type=MessageType.COMMAND, source=source, message_id='C')
    method = runner._busy_queue_command if command.startswith('/queue') else runner._busy_steer_command
    with ctx.relay_callback(transport, original), ctx.native_callback(runner, original, home):
        await method(original, 'chat', source)
    assert accepted == ['C']








