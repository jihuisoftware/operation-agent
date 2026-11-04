"""Editable topic and Profile model budgets; saved lower limits stay authoritative."""
import json

DEFAULT_CALLS = 200
DEFAULT_TOKENS = 1_000_000
POLICY_DEFAULTS = {'model_budget_mode': 'calls', 'model_tokens': DEFAULT_TOKENS}


def validate(value):
    if not isinstance(value, dict) or set(value) != {'mode', 'calls', 'tokens'}:
        raise ValueError('模型预算字段不完整')
    if value['mode'] not in {'calls', 'tokens'}:
        raise ValueError('模型预算方式必须是调用次数或 Token 用量')
    for key, maximum in (('calls', 1000), ('tokens', 1_000_000_000)):
        if type(value[key]) is not int or not 0 <= value[key] <= maximum:
            raise ValueError(f'{key} 预算必须是 0 到 {maximum} 的整数')
    return dict(value)


def topic_config(policy):
    return {'mode': policy.get('model_budget_mode', 'calls'), 'calls': policy['model_calls'],
            'tokens': policy.get('model_tokens', DEFAULT_TOKENS)}


def profile_config(limits):
    return {'mode': limits.get('model_budget_mode', 'calls'), 'calls': limits['model'],
            'tokens': limits.get('model_tokens', DEFAULT_TOKENS)}


def profile_fields(config):
    return {'model': config['calls'], 'model_budget_mode': config['mode'], 'model_tokens': config['tokens']}


def synchronize(db, policy):
    previous = json.loads(db.execute("SELECT data FROM directory.preferences WHERE id='limits'").fetchone()[0])
    model = profile_config(previous) if previous.get('_model_explicit') else topic_config(policy)
    limits = {**previous, **policy['limits'], **profile_fields(model), '_timezone': policy['timezone']}
    if model != profile_config(previous):
        limits['_model_revision'] = previous.get('_model_revision', 0) + 1
    db.execute("UPDATE directory.preferences SET data=? WHERE id='limits'", (json.dumps(limits),))


def read(store):
    from .model_budget_recovery import recover
    recover(store)
    from .model_budget_ledger import totals
    with store.connection() as db:
        limits = json.loads(db.execute("SELECT data FROM directory.preferences WHERE id='limits'").fetchone()[0])
        from .policy import local_day
        day = local_day({'timezone': limits.get('_timezone', 'Asia/Shanghai')})
        used = totals(store, db, day, profile=True)
        used['calls'] = db.execute("SELECT coalesce(sum(amount),0) FROM directory.charges WHERE day=? AND kind='model' AND account_id=''", (day,)).fetchone()[0]
    return {'version': limits.get('_model_revision', 0), 'config': profile_config(limits), 'day': day, 'usage': used}


def save(store, body):
    config = validate(body['config'])
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        limits = json.loads(db.execute("SELECT data FROM directory.preferences WHERE id='limits'").fetchone()[0])
        version = limits.get('_model_revision', 0)
        if type(body.get('version')) is not int or body['version'] != version:
            raise ValueError('共享模型预算已变更，请刷新后保存')
        limits.update(profile_fields(config), _model_explicit=True, _model_revision=version + 1)
        db.execute("UPDATE directory.preferences SET data=? WHERE id='limits'", (json.dumps(limits),))
    return read(store)
