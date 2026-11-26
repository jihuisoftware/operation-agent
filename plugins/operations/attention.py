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


def listing(store, kind, before=0, day='', record=''):
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
    if kind == 'unverified':
        from .message_storage import initialize
        initialize(store)
        if record:
            where += ' AND id=?'
            params = (*params, record)
    with store.connection() as db:
        db.execute('BEGIN')
        total = db.execute(f'SELECT count(*) FROM {table} WHERE {where}', params).fetchone()[0]
        rows = db.execute(f'SELECT rowid AS cursor,{PROJECTIONS[kind]} FROM {table} WHERE {where} '
                          'AND (?=0 OR rowid<?) ORDER BY rowid DESC LIMIT 26', (*params, before, before)).fetchall()
        items = [dict(row) for row in rows[:25]]
        if kind == 'unverified':
            attach_origins(store, db, items)

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

def attach_origins(store, db, items):
    if not items:
        return
    from .message_storage import table, owner
    keys = json.dumps([item['id'] for item in items])
    ids = ' IN (SELECT value FROM json_each(?))'
    targets = {r['id']: r for r in db.execute(
        "SELECT id,json_extract(data,'$.content.id') AS manuscript,coalesce(json_extract(data,'$.content.title'),"
        "json_extract(data,'$.item.text'),json_extract(data,'$.target'),target) AS name FROM actions WHERE id" + ids, (keys,))}
    submissions = dict(db.execute(
        "SELECT json_extract(data,'$.action_id'),max(created) FROM objects WHERE kind='browser_step' "
        "AND json_extract(data,'$.phase')='completed' AND json_extract(data,'$.name') IN ('submit','submit_interaction') "
        "AND json_extract(data,'$.action_id')" + ids + " GROUP BY 1", (keys,)))
    linked = {(r['action_id'],r['kind']):r['id'] for r in db.execute(
        f"SELECT action_id,kind,id FROM {table(store)} WHERE topic=? AND account!='' AND target!='' AND action_id" + ids,
        (owner(store),keys))}
    missing = [i['id'] for i in items if i['kind'] in ('reply','dm','follow') and (i['id'],i['kind']) not in linked]
    if missing:
        history = db.execute(
            f"SELECT m.id,m.kind,json_extract(h.value,'$.action_id') AS action_id FROM {table(store)} m, json_each(m.history) h "
            "WHERE m.topic=? AND m.account!='' AND m.target!='' AND json_extract(h.value,'$.topic')=? "
            "AND json_extract(h.value,'$.event')='legacy' AND json_extract(h.value,'$.action_id')" + ids,
            (owner(store), owner(store), json.dumps(missing)))
        linked.update({(r['action_id'],r['kind']):r['id'] for r in history})
    for item in items:
        identity, kind = item['id'], item['kind']
        result = json.loads(item['result'])
        item.update(target_name=targets[identity]['name'], submitted_at=submissions.get(identity),
                    evidence=result.get('evidence') or result.get('error') or '')
        if kind == 'publish' and targets[identity]['manuscript']:
            item['origin'] = {'tab':'published','record':identity}
        elif kind == 'comment':
            item['origin'] = {'tab':'comment','record':identity}
        elif (identity,kind) in linked:
            item['origin'] = {'tab':'messages','source':kind,'record':linked[identity,kind]}
        if store.scope and 'origin' in item:
            item['origin'].update(business_id=store.scope['business_id'], topic_id=owner(store))
