"""A chat's inputs reach its FIFO in arrival order, whatever off-loop media capture each needs.

The capture (copy + SHA-256 + fsyncs) runs in a worker thread before the ordered admission write,
so a text sent right after a photo or video must wait for it instead of taking the earlier slot
and running first without the media. Other chats never wait.
"""
import asyncio
import threading

import pytest

from gateway.config import GatewayConfig, Platform
from gateway.platforms.event import MessageEvent, MessageType
from gateway.run import GatewayRunner
from gateway.session_authority import initialize_session_authority
from hermes_state_runtime import list_session_admissions
from tests.gateway.test_shared_busy_receive_loop import Adapter
from tests.waiting import async_wait_until

X, Y = '15551234567@s.whatsapp.net', '15557654321@s.whatsapp.net'


def _order(authority):
    rows = (row for sid in authority.sessions
            for row in list_session_admissions(authority.db, session_id=sid, pending_only=False))
    return [row['request_id'] for row in sorted(rows, key=lambda row: row['seq'])]


def _hold_capture(monkeypatch):
    """The real capture, held on an Event: a large video on a slow disk."""
    import gateway.session_envelope as envelope
    import gateway.session_ingress_media as media
    entered, release = threading.Event(), threading.Event()
    real_capture = media.capture_native_media

    def held(paths):
        entered.set()
        release.wait(15.0)  # outlasts every bound below: an input done within one never waited on it
        return real_capture(paths)
    monkeypatch.setattr(envelope, 'capture_native_media', held)
    return entered, release


def _video(source, mid, clip):
    return MessageEvent(text='', message_type=MessageType.VIDEO, source=source, message_id=mid,
                        media_urls=[str(clip)], media_types=['video/mp4'])


@pytest.mark.asyncio
@pytest.mark.parametrize('busy', [False, True], ids=['idle', 'busy'])
async def test_media_then_quick_text_keep_arrival_order(tmp_path, monkeypatch, busy):
    """The adapter path: an idle video then a busy text, or both while a turn runs."""
    import gateway.session_finite as finite
    monkeypatch.setenv('TELEGRAM_ALLOWED_USERS', 'fixture-user')
    gate = asyncio.Event()

    async def produce(authority, ref, row):
        await gate.wait()
        return 'ok'
    monkeypatch.setattr(finite, 'execute_finite_admission', produce)
    entered, release = _hold_capture(monkeypatch)
    runner = GatewayRunner(GatewayConfig())
    adapter = Adapter()
    runner.adapters = {Platform.TELEGRAM: adapter}
    authority = await initialize_session_authority(runner, profile_id='default', instance_id='order')
    runner._wire_adapter_handlers(adapter)
    source = adapter.build_source(chat_id='order-chat', chat_type='dm', user_id='fixture-user')
    clip = tmp_path / 'clip.mp4'
    clip.write_bytes(b'video-bytes' * 1000)
    expected = ['v1', 't1']
    try:
        if busy:
            await adapter.handle_message(MessageEvent(text='hello', source=source, message_id='h0'))
            await async_wait_until(lambda: _order(authority) == ['h0'], what='the running turn admitted')
            expected.insert(0, 'h0')
        # One task per delivery, as Discord and Slack dispatch them.
        first = asyncio.create_task(adapter.handle_message(_video(source, 'v1', clip)))
        await asyncio.to_thread(entered.wait, 5)
        text = MessageEvent(text='what is this?', source=source, message_id='t1')
        second = asyncio.create_task(adapter.handle_message(text))
        # A serial reader (Signal, IRC) awaits this: it returns once the text queues behind the
        # video, without acknowledging it (main commits the text here, ahead of the video).
        assert second in (await asyncio.wait({second}, timeout=2.0))[0], 'the reader waited for the capture'
        assert 't1' not in _order(authority) and text._gateway_accepted is False
        release.set()
        await asyncio.gather(first, second)
        await async_wait_until(lambda: len(_order(authority)) == len(expected), what='both admitted')
        assert _order(authority) == expected
    finally:
        release.set()
        gate.set()
        await async_wait_until(lambda: not adapter._background_tasks, what='adapter tasks done')
        authority.db.close()










