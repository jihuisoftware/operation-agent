"""A focused editor for the owning topic's daily source-read allowance."""
import json

from .collection_ledger import budget
from .policy import local_day


def read(store):
    version, policy = store.policy()
    day = local_day(policy)
    used = budget(store, day)
    shared_limit, shared_used, shared_day = None, None, None
    if store.workspace:
        with store.connection() as db:
            limits = json.loads(db.execute("SELECT data FROM directory.preferences WHERE id='limits'").fetchone()[0])
            shared_limit = limits['source']
            shared_day = local_day({'timezone': limits.get('_timezone', 'Asia/Shanghai')})
            shared_used = db.execute("SELECT coalesce(sum(amount),0) FROM directory.charges WHERE day=? AND kind='source' AND account_id=''", (shared_day,)).fetchone()[0]
    remaining = max(0, policy['limits']['source'] - used)
    if shared_limit is not None:
        remaining = min(remaining, max(0, shared_limit - shared_used))
    return {'version': version, 'limit': policy['limits']['source'], 'day': day, 'used': used,
            'shared_limit': shared_limit, 'shared_used': shared_used, 'shared_day': shared_day, 'remaining': remaining}


def save(store, body):
    value = body.get('limit')
    version = body.get('version')
    if type(value) is not int or not 100 <= value <= 10_000:
        raise ValueError('每日采集上限必须为100到10000之间的整数')
    if type(version) is not int or version < 0:
        raise ValueError('设置版本无效，请重新读取')
    _, policy = store.policy()
    store.configure({**policy, 'limits': {**policy['limits'], 'source': value}}, version)
    return read(store)
