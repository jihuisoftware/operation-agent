"""Lifecycle adapters for the token ledger, independent of any application plugin."""
from contextlib import contextmanager
from types import SimpleNamespace
import logging
import uuid

from agent import token_ledger as ledger

log = logging.getLogger(__name__)


def run_tracked_turn(call, agent, *args, **kwargs):
    context = None
    state = 'failed'
    try:
        context = ledger.start_task(str(getattr(agent, '_relay_pending_turn_id', '') or uuid.uuid4().hex),
                                    session_id=str(getattr(agent, 'session_id', '') or ''),
                                    turn_id=str(getattr(agent, '_relay_pending_turn_id', '') or ''),
                                    task_name='AI 助手', stage='chat')
    except Exception:
        log.exception('Could not open token usage task')
    try:
        with ledger.bind(context):
            result = call(agent, *args, **kwargs)
        state = 'cancelled' if result.get('interrupted') else 'failed' if result.get('failed') else 'completed'
        return result
    finally:
        close_task(context, state)


def close_task(context, state):
    if context:
        try:
            ledger.finish_task(context, state)
        except Exception:
            log.exception('Could not close token usage task')


@contextmanager
def attempt(**kwargs):
    record = ledger.safe_start(**kwargs)
    result = SimpleNamespace(response=None)
    try:
        yield result
    except BaseException as exc:
        ledger.safe_finish(record, error=exc)
        raise
    else:
        ledger.safe_finish(record, response=result.response)


class UsageStream:
    """Observe an iterator without prefetching or altering its chunks."""
    def __init__(self, stream, record):
        self.stream, self.record = stream, record
        self.iterator = iter(stream)
        self.response = None

    def __iter__(self):
        return self

    def __next__(self):
        try:
            chunk = next(self.iterator)
        except StopIteration:
            ledger.safe_finish(self.record, response=self.response)
            raise
        except BaseException as exc:
            ledger.safe_finish(self.record, response=self.response, error=exc)
            raise
        if getattr(chunk, 'usage', None) is not None:
            self.response = chunk
        return chunk

    def close(self):
        try:
            close = getattr(self.stream, 'close', None)
            if close:
                close()
        finally:
            ledger.safe_finish(self.record, response=self.response, error=InterruptedError())

    def __getattr__(self, key):
        return getattr(self.stream, key)
