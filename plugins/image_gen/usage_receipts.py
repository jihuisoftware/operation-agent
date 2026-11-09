"""Optional response receipts for non-chat consumers of image provider plugins."""
from contextlib import contextmanager
from contextvars import ContextVar

_CURRENT = ContextVar('image_usage_receipts', default=None)


@contextmanager
def capture():
    receipts = []
    token = _CURRENT.set(receipts)
    try:
        yield receipts
    finally:
        _CURRENT.reset(token)


def record(usage, *, model, provider):
    receipts = _CURRENT.get()
    if receipts is not None and usage:
        receipts.append({'usage': usage, 'model': model, 'provider': provider})
