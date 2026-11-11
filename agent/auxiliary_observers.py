"""Scoped, observer-only access to physical auxiliary requests and receipts."""
from contextlib import contextmanager
from contextvars import ContextVar
import logging

_OBSERVER = ContextVar('auxiliary_request_observer', default=None)
log = logging.getLogger(__name__)


@contextmanager
def observe(callback):
    token = _OBSERVER.set(callback)
    try:
        yield
    finally:
        _OBSERVER.reset(token)


def notify(event, hooks, **fields):
    callback = _OBSERVER.get()
    if callback is None or hooks.usage_record is None:
        return
    try:
        callback(event, attempt=hooks.usage_record, request=hooks.kwargs,
                 metadata=hooks.base, **fields)
    except Exception:
        # Recording must never turn a successful paid request into a retry.
        log.exception('Could not record auxiliary request detail')
