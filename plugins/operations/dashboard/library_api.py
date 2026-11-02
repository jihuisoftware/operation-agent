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
        action = db.execute("SELECT state FROM actions WHERE kind='publish' AND json_extract(data,'$.content.id')=? ORDER BY rowid DESC LIMIT 1", (item['id'],)).fetchone()
        item['publication_state'] = action['state'] if action else None
    sources = {s['id']: s for s in objects(db, 'source')}
    sources.update({s['id']: s for s in objects(db, 'source', [identity for item in content for identity in item.get('source_ids', [])])})
    return {'content': content, 'asset': objects(db, 'asset'), 'source': list(sources.values())}


@router.get('/library/{section}')
def library(section: str, before: int = 0, filter: str = '', record: str = ''):
    if section not in PRIMARY or before < 0 or filter not in {'', 'published', 'pending', 'drafts', 'comment', 'reply', 'dm', 'follow'}:
        raise HTTPException(400, '资料筛选条件无效')
    store = Store()
    table, condition = PRIMARY[section]
    if section == 'content' and filter == 'published':
        table, condition = 'actions', "kind='publish'"
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
