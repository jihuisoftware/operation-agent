"""Image usage belongs to its operations run; missing token/price receipts stay unknown."""
from agent.token_ledger import bind, connection, safe_start, safe_finish
from plugins.image_gen.usage_receipts import capture

from .usage_context import begin, finish
from .model_budget_ledger import marker
from .policy import local_day


def call(store, record, attempt, operation):
    owner = store.current_run_id or record['id'] + ':' + attempt['id']
    context = begin(store, owner)
    after = marker(context)
    result, state, receipts = None, 'failed', []
    try:
        with bind(context), capture() as receipts:
            result = operation()
        state = 'completed'
        return result
    finally:
        with connection(context['path']) as db:
            rows = db.execute('SELECT total_tokens,state FROM token_usage_calls WHERE task_id=? AND rowid>?', (owner, after)).fetchall()
        if not rows:
            actual = receipts or [{'model': record['selection']['model'], 'provider': record['selection']['provider'], 'usage': (result or {}).get('usage')}]
            for receipt in actual:
                item = safe_start(context=context, model=receipt['model'], provider=receipt['provider'], purpose='image_generation')
                safe_finish(item, response=receipt)
            with connection(context['path']) as db:
                rows = db.execute('SELECT total_tokens,state FROM token_usage_calls WHERE task_id=? AND rowid>?', (owner, after)).fetchall()
        known = bool(rows) and all(row['state'] == 'confirmed' and row['total_tokens'] is not None for row in rows)
        tokens = {'total_tokens': sum(row['total_tokens'] for row in rows)} if known else None
        cost = (result or {}).get('cost')
        store.event('image_usage', {'day': local_day(store.policy()[1]), 'visual_set_id': record['id'], 'attempt_id': attempt['id'],
                    'state': state, 'cost': cost, 'tokens': tokens, 'cost_note': '未提供费用回执' if cost is None else '提供方回执'})
        if not store.current_run_id:
            finish(store, owner, state)
