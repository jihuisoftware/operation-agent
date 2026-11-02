"""Translate an operations run into the runtime's generic usage ownership."""
import logging
from agent import token_ledger
from agent.token_tracking import close_task

log = logging.getLogger(__name__)


def run_context(store, identity):
    with store.connection() as db:
        row = db.execute('SELECT stage FROM runs WHERE id=?', (identity,)).fetchone()
    scope = store.scope or {}
    return {'task_id': identity, 'path': str(token_ledger.get_hermes_home() / 'state.db'),
            'business_id': scope.get('business_id', ''), 'topic_id': scope.get('id', ''),
            'run_id': identity, 'stage': row['stage'] if row else 'operations',
            'task_name': row['stage'] if row else '运营调用'}


def begin(store, identity):
    context = run_context(store, identity)
    try:
        token_ledger.start_task(identity, **{k: v for k, v in context.items() if k != 'task_id'})
    except Exception:
        log.exception('Could not record operations usage task')
    return context


def finish(store, identity, state):
    close_task(run_context(store, identity), state)
