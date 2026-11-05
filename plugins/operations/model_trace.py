"""Debug-only business request snapshots; never change prompts or provider routing."""
import json
import re

from .policy import now_iso
from .store import encoded


def redact(value):
    if isinstance(value, dict):
        return {key: '[已隐藏]' if re.search(r'(^|_)(api_key|access_token|refresh_token|password|authorization|cookie|secret)($|_)', str(key), re.IGNORECASE)
                else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def update(store, identity, fields):
    with store.connection() as db:
        row = db.execute("SELECT data FROM objects WHERE id=? AND kind='model_trace'", (identity,)).fetchone()
        if row:
            db.execute('UPDATE objects SET data=? WHERE id=?', (encoded({**json.loads(row[0]), **redact(fields)}), identity))


def capture_response(store, budget_id, response):
    if not getattr(store, 'debug_id', None):
        return
    choices = getattr(response, 'choices', None)
    message = getattr(choices[0], 'message', None) if isinstance(choices, (list, tuple)) and choices else None
    update(store, 'model-trace:' + budget_id, {'raw_response': getattr(message, 'content', None), 'response_at': now_iso()})


def traced(store, instruction, data, budget_id, call, *, options):
    if not getattr(store, 'debug_id', None):
        return call()
    identity = store.put('model_trace', {'instruction': instruction, 'input': redact(data), 'budget_id': budget_id,
                         'started': now_iso(), 'state': 'running', 'options': options, 'step_id': getattr(store, 'debug_step', None)}, 'model-trace:' + budget_id)
    store.event('model_trace_started', {'trace_id': identity})
    try:
        result = call()
    except Exception as exc:
        update(store, identity, {'state': 'failed', 'ended': now_iso(), 'error': str(exc), 'error_type': type(exc).__name__})
        raise
    update(store, identity, {'state': 'completed', 'ended': now_iso(), 'result': result})
    store.event('model_trace_completed', {'trace_id': identity})
    return result
