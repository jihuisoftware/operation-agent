"""Human attribution preserves original ledgers and rule snapshots, without replay."""
import json

TABLES = {'objects', 'runs', 'actions'}


def catalog(store, source_topic):
    source = store.workspace.store(store.scope['business_id'], source_topic)
    if not source.scope['archived']:
        raise ValueError('只能整理已归档的历史分区')
    result = []
    with source.connection() as db:
        for table in TABLES:
            rows = db.execute(f'SELECT * FROM {table} ORDER BY rowid DESC LIMIT 100')
            for row in rows:
                value = dict(row)
                if table == 'objects' and row['kind'] in {'policy', 'schedule', 'activation'}:
                    continue
                result.append({'table': table, 'id': row['id'], 'record': value})
    return {'items': result}


def assign(store, body):
    source = store.workspace.store(store.scope['business_id'], body['source_topic_id'])
    table = body.get('table')
    if table not in TABLES or not source.scope['archived'] or store.scope['archived']:
        raise ValueError('请选择归档历史和有效的目标主题')
    with source.connection() as db:
        row = db.execute(f'SELECT * FROM {table} WHERE id=?', (body['record_id'],)).fetchone()
        if not row:
            raise ValueError('历史记录不存在')
        if table != 'objects' and row['state'] in {'running', 'queued', 'executing', 'unknown', 'submitted'}:
            raise ValueError('请先在原始历史分区核对未完成动作')
        record = dict(row)
        version = record.get('version')
        rule = db.execute("SELECT data FROM objects WHERE kind='policy' AND json_extract(data,'$.version')=?", (version,)).fetchone() if version is not None else None
    snapshot = {'record': record, 'rule': json.loads(rule[0]) if rule else None,
                'source_topic_id': source.scope['id'], 'table': table, 'record_id': body['record_id']}
    with store.workspace.connection() as db:
        db.execute('INSERT INTO history_assignments VALUES (?,?,?,?,?) ON CONFLICT(source_topic,record_table,record_id) DO UPDATE SET target_topic=excluded.target_topic,data=excluded.data',
                   (source.scope['id'], table, body['record_id'], store.scope['id'], json.dumps(snapshot, ensure_ascii=False)))
    store.event('history_assigned', snapshot)
    return {'ok': True}


def assigned(store):
    with store.workspace.connection() as db:
        return {'items': [json.loads(r[0]) for r in db.execute('SELECT data FROM history_assignments WHERE target_topic=?', (store.scope['id'],))]}
