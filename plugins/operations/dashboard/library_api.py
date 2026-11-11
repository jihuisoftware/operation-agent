"""Bounded page projections with independent cursors and explicit owning Profile."""
import json
from fastapi import APIRouter, HTTPException
from plugins.operations.store import Store

router = APIRouter()
PRIMARY = {'assets': ('objects', "kind='asset'"), 'content': ('objects', "kind='content'"),
           'interactions': ('actions', "kind!='publish'"), 'reports': ('objects', "kind='report'"),
           'history': ('runs', '1=1')}


def objects(db, kind, identities=None):
    if identities is None:
        rows = db.execute('SELECT * FROM objects WHERE kind=? ORDER BY rowid DESC LIMIT 100', (kind,))
    else:
        rows = db.execute('SELECT * FROM objects WHERE kind=? AND id IN (SELECT value FROM json_each(?))', (kind, json.dumps(identities)))
    return [{**json.loads(r['data']), 'id': r['id'], 'created': r['created']} for r in rows]


def content_data(db, rows):
    content = [{**json.loads(r['data']), 'id': r['id'], 'created': r['created']} for r in rows]
    for item in content:
        from plugins.operations.content_edits import latest_action
        action = latest_action(db, item['id'], item)
        item['publication_state'] = action['state'] if action else None
        from plugins.operations.content_release import load, fingerprint
        item['release'] = load(db, item['id'])
        item['content_revision'] = fingerprint(item)
        item['policy_version'] = db.execute('SELECT version FROM settings WHERE id=1').fetchone()[0]
    from plugins.operations.publication_waiting import annotate
    annotate(db, content)
    sources = {s['id']: s for s in objects(db, 'source')}
    sources.update({s['id']: s for s in objects(db, 'source', [identity for item in content for identity in item.get('source_ids', [])])})
    return {'content': content, 'asset': objects(db, 'asset'), 'source': list(sources.values())}


@router.get('/library/{section}')
def library(section: str, before: int = 0, filter: str = '', record: str = '', compact: bool = False, status: str = 'all'):
    if section not in PRIMARY or before < 0 or filter not in {'', 'published', 'pending', 'drafts', 'comment', 'reply', 'dm', 'follow'}:
        raise HTTPException(400, '资料筛选条件无效')
    store = Store()
    if section == 'content':
        from ..content_library import listing
        try:
            return listing(store, before, filter, record, status, compact)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    table, condition = PRIMARY[section]
    with store.connection() as db:
        rows = list(db.execute(f"SELECT rowid AS cursor,* FROM {table} WHERE {condition} AND (?='' OR id=?) AND (?=0 OR rowid<?) ORDER BY rowid DESC LIMIT 100", (record, record, before, before)))
        data = {'actions': [], 'next': str(rows[-1]['cursor']) if len(rows) == 100 else None}
        if table == 'actions':
            data['actions'] = [dict(r) for r in rows if not filter or filter == 'published' or r['kind'] == filter]
        elif section == 'content':
            data.update(content_data(db, rows))
        elif table == 'objects':
            kind = 'asset' if section == 'assets' else 'report'
            data[kind] = [{**json.loads(r['data']), 'id': r['id'], 'created': r['created']} for r in rows]
        else:
            data['runs'] = [dict(r) for r in rows]
            data['task'] = objects(db, 'task')
        if section == 'interactions':
            data.update(inbox=objects(db, 'inbox'), block=objects(db, 'block'))
    return data


@router.get('/reports/{identity}/details')
def report_details(identity: str):
    store = Store()
    with store.connection() as db:
        row = db.execute("SELECT data FROM objects WHERE kind='report' AND id=?", (identity,)).fetchone()
        if not row:
            raise HTTPException(404, '日报不存在')
        record = json.loads(row['data'])
        details = db.execute("SELECT data FROM objects WHERE kind='report_detail' AND id=?", (record.get('details_id', ''),)).fetchone()
    return {'id': identity, 'markdown': json.loads(details['data'])['markdown'] if details else record['markdown']}
