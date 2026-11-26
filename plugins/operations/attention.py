"""Overview counts and their drill-downs use the same topic-local predicates."""
import json
from datetime import date

from .policy import local_day, now_iso

CONTENT = "json_extract(c.data,'$.state') IN ('needs_material','needs_review')"
SOURCES = {
    'unverified': ('actions', "state IN ('submitted','unknown')"),
    'content': ('objects c', "c.kind='content' AND " + CONTENT),
    'failed_today': ('runs', "day=? AND state='failed'"),
}
PROJECTIONS = {
    'unverified': 'id,kind,day,version,target,state,result,created',
    'failed_today': 'id,stage,started,state,detail',
}


def counts(store, db, day):
    from .messages import query
    source, args = query(store, state='attention')
    return {'inbox': db.execute('SELECT count(*)' + source, args).fetchone()[0], **{key: db.execute(f'SELECT count(*) FROM {table} WHERE {where}',
                            (day,) if key == 'failed_today' else ()).fetchone()[0]
            for key, (table, where) in SOURCES.items()}}


def listing(store, kind, before=0, day=''):
    if kind == 'inbox':
        from .messages import listing as message_list
        page = message_list(store, state='attention', before=before)
        return {**page, 'day': day}
    if kind not in PROJECTIONS or before < 0:
        raise ValueError('待处理事项筛选无效')
    table, where = SOURCES[kind]
    if kind == 'failed_today':
        day = date.fromisoformat(day).isoformat() if day else local_day(store.policy()[1])
    params = (day,) if kind == 'failed_today' else ()
    with store.connection() as db:
        db.execute('BEGIN')
        total = db.execute(f'SELECT count(*) FROM {table} WHERE {where}', params).fetchone()[0]
        rows = db.execute(f'SELECT rowid AS cursor,{PROJECTIONS[kind]} FROM {table} WHERE {where} '
                          'AND (?=0 OR rowid<?) ORDER BY rowid DESC LIMIT 26', (*params, before, before)).fetchall()
    items = [dict(row) for row in rows[:25]]
    return {'items': items, 'total': total, 'day': day, 'next': items[-1]['cursor'] if len(rows) > 25 else None}


def handle_inbox(store, identity):
    if not isinstance(identity, str) or not identity:
        raise ValueError('咨询标识无效')
    from .messages import detail, legacy_id
    from .message_actions import change
    try:
        record = detail(store, legacy_id(store, identity) or identity)
    except KeyError:
        record = None
    if record:
        if record['state'] != 'handled':
            change(store, record['id'], {'revision': record['revision'], 'operation': 'handle'})
        return {'state': 'handled'}
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT json_extract(data,'$.state') FROM objects WHERE kind='inbox' AND id=?", (identity,)).fetchone()
        if not row:
            raise KeyError('咨询不存在')
        if row[0] == 'needs_review':
            db.execute("UPDATE objects SET data=json_set(data,'$.state','handled','$.handled_at',?) WHERE id=?",
                       (now_iso(), identity))
        elif row[0] != 'handled':
            raise ValueError('咨询状态已变化，请刷新')
    return {'state': 'handled'}
