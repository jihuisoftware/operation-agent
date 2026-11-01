"""Profile-local imports with transactional idempotency and immutable batches."""
import base64
import json

from . import business_files as files
from . import business_validation as validation
from .policy import now_iso
from .store import encoded

SCHEMA = '''
CREATE TABLE IF NOT EXISTS business_datasets(id TEXT PRIMARY KEY, version INTEGER NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS business_uploads(id TEXT PRIMARY KEY, name TEXT NOT NULL, file BLOB NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS business_batches(id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL, digest TEXT NOT NULL, data TEXT NOT NULL,
 UNIQUE(dataset_id,digest));
CREATE TABLE IF NOT EXISTS business_rows(batch_id TEXT NOT NULL, row_number INTEGER NOT NULL, dataset_id TEXT NOT NULL,
 day TEXT NOT NULL, business_key TEXT, data TEXT NOT NULL, PRIMARY KEY(batch_id,row_number));
CREATE INDEX IF NOT EXISTS business_rows_dates ON business_rows(dataset_id,day);
CREATE INDEX IF NOT EXISTS business_rows_keys ON business_rows(dataset_id,business_key);
'''


def initialize(db):
    db.executescript(SCHEMA)


def datasets(store):
    with store.connection() as db:
        return [{**json.loads(r['data']), 'id': r['id'], 'version': r['version']} for r in db.execute('SELECT * FROM business_datasets')]


def upload(store, body):
    name = str(body.get('name', ''))[:200]
    if len(body.get('data', '')) > files.MAX_BYTES * 4 // 3 + 4:
        raise ValueError('文件超过 20 MB')
    data = base64.b64decode(body['data'], validate=True)
    if not data or len(data) > files.MAX_BYTES:
        raise ValueError('文件必须非空且不超过 20 MB')
    choices = list(files.sheets(data)) if name.lower().endswith('.xlsx') else ['CSV']
    identity = validation.fingerprint([name, base64.b64encode(data).decode()])
    with store.connection() as db:
        db.execute('INSERT OR IGNORE INTO business_uploads VALUES (?,?,?,?)', (identity, name, data, now_iso()))
    return inspect(store, identity, choices[0]) | {'sheets': choices}


def file_data(store, identity):
    with store.connection() as db:
        row = db.execute('SELECT name,file FROM business_uploads WHERE id=?', (identity,)).fetchone()
    if not row:
        raise ValueError('导入文件不存在，请重新上传')
    return row['name'], row['file']


def inspect(store, identity, sheet):
    name, data = file_data(store, identity)
    iterator = files.rows(data, name, sheet)
    headers = next(iterator, (0, []))[1]
    if not headers or len(headers) != len(set(headers)) or any(not h for h in headers):
        raise ValueError('首行应为非空且不重复的列名')
    sample = []
    for _, row in iterator:
        sample.append(dict(zip(headers, row)))
        if len(sample) == 5:
            break
    return {'upload_id': identity, 'sheet': sheet, 'headers': headers, 'sample': sample,
            'suggestions': {k: validation.suggest(headers, k) for k in validation.TEMPLATES}}


def prepare(store, body):
    view = inspect(store, body['upload_id'], body['sheet'])
    config = validation.options(body, view['headers'])
    sharing = validation.permissions(body, config)
    name, data = file_data(store, body['upload_id'])
    return view, config, sharing, name, data


def parsed(data, name, sheet, config):
    iterator = files.rows(data, name, sheet)
    headers = next(iterator)[1]
    for number, values in iterator:
        try:
            if len(values) > len(headers):
                raise ValueError('此行列数超出表头')
            yield number, validation.clean_row(dict(zip(headers, values)), config), None
        except ValueError as exc:
            yield number, None, str(exc)


def model_sample(rows, sharing):
    if sharing['model_mode'] != 'details':
        return []
    return [{k: validation.redact(row[k]) if k in {'product', 'channel', 'platform', 'note'} and isinstance(row.get(k), str) else row.get(k)
             for k in sharing['detail_fields']} for row in rows]


def preview(store, body):
    _, config, sharing, name, data = prepare(store, body)
    good, bad, sample, errors = 0, 0, [], []
    for number, row, error in parsed(data, name, body['sheet'], config):
        if error:
            bad += 1
            if len(errors) < 100:
                errors.append({'row': number, 'error': error})
        else:
            good += 1
            if len(sample) < 20:
                sample.append(row)
    policy_version, policy = store.policy()
    digest = validation.fingerprint({'policy_version': policy_version, 'topic': policy['topic'], 'file': validation.fingerprint(base64.b64encode(data).decode()), 'sheet': body['sheet'],
                                     'config': config, 'sharing': sharing})
    return {'policy_version': policy_version, 'scope_topic': policy['topic'], 'valid': good, 'invalid': bad, 'errors': errors, 'sample': sample,
            'model_sample': model_sample(sample, sharing), 'preview_token': digest, 'config': config, 'sharing': sharing}


def confirm(store, body):
    result = preview(store, body)
    if result['preview_token'] != body.get('preview_token'):
        raise ValueError('预览已变化，请重新检查发送范围')
    if result['invalid'] and body.get('exclude_invalid') is not True:
        raise ValueError('存在无效行，请修正或选择排除后导入')
    if not result['valid']:
        raise ValueError('没有有效数据可导入')
    return _save(store, body, result)


def _save(store, body, previewed):
    _, config, sharing, name, data = prepare(store, body)
    identity = body.get('dataset_id') or 'dataset:' + validation.fingerprint([previewed['scope_topic'], base64.b64encode(data).decode(), config])[:24]
    digest = validation.fingerprint([base64.b64encode(data).decode(), body['sheet'], config])
    batch = 'batch:' + validation.fingerprint([identity, digest])[:32]
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT version FROM settings WHERE id=1').fetchone()[0] != previewed['policy_version']:
            raise ValueError('运营主题或规则已变化，请重新预览导入')
        existing = db.execute('SELECT data FROM business_batches WHERE id=?', (batch,)).fetchone()
        if existing:
            return json.loads(existing[0])
        prior = db.execute('SELECT * FROM business_datasets WHERE id=?', (identity,)).fetchone()
        current = json.loads(prior['data']) if prior else None
        if prior and prior['version'] != body.get('dataset_version'):
            raise ValueError('数据集已变化，请刷新后导入')
        if current and current['scope_topic'] != previewed['scope_topic']:
            raise ValueError('数据集属于其他主题，请新建当前主题的数据集')
        if current and current['config'] != config:
            raise ValueError('同一数据集的模板与指标口径必须一致，请新建数据集')
        if current and current['sharing'] != sharing:
            raise ValueError('数据集权限已变化，请先保存使用选项')
        inserted, duplicate = _insert_rows(db, data, name, body, config, identity, batch)
        batches = [] if body.get('replace') else (current or {}).get('batches', [])
        dataset = {'name': str(body.get('name') or name)[:100], 'scope_topic': previewed['scope_topic'],
                   'active': True, 'config': config, 'sharing': sharing, 'batches': batches + [batch], 'updated': now_iso()}
        db.execute('INSERT OR REPLACE INTO business_datasets VALUES (?,?,?)', (identity, (prior['version'] if prior else 0) + 1, encoded(dataset)))
        receipt = {'id': batch, 'dataset_id': identity, 'inserted': inserted, 'duplicates': duplicate,
                   'invalid': previewed['invalid'], 'errors': previewed['errors'], 'created': now_iso(), 'config': config}
        db.execute('INSERT INTO business_batches VALUES (?,?,?,?)', (batch, identity, digest, encoded(receipt)))
    store.event('business_import', {**receipt, 'day': now_iso()[:10]})
    return receipt


def _insert_rows(db, data, name, body, config, identity, batch):
    inserted = duplicate = 0
    for number, row, error in parsed(data, name, body['sheet'], config):
        if error:
            continue
        key = row.get('key') if config['dedupe'] else None
        prior = _duplicate(db, identity, batch, key, body.get('replace')) if key else False
        if prior:
            duplicate += 1
            continue
        db.execute('INSERT INTO business_rows VALUES (?,?,?,?,?,?)', (batch, number, identity, row['day'], key, encoded(row)))
        inserted += 1
    return inserted, duplicate


def update_dataset(store, identity, body):
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM business_datasets WHERE id=?', (identity,)).fetchone()
        if not row or row['version'] != body['version']:
            raise ValueError('数据集已变化，请刷新')
        value = json.loads(row['data'])
        sharing = validation.permissions(body, value['config'])
        token = validation.fingerprint([identity, row['version'], sharing, body.get('active') is True])
        if body.get('preview_token') != token:
            raise ValueError('请先预览并确认使用选项')
        value.update(sharing=sharing, active=body.get('active') is True, updated=now_iso())
        db.execute('UPDATE business_datasets SET version=version+1,data=? WHERE id=?', (encoded(value), identity))
    store.event('business_permissions', {'dataset_id': identity, 'version': row['version'] + 1, 'day': now_iso()[:10]})
    return {'ok': True}


def permission_preview(store, identity, body):
    item = next((d for d in datasets(store) if d['id'] == identity), None)
    if not item or item['version'] != body['version']:
        raise ValueError('数据集已变化，请刷新')
    sharing = validation.permissions(body, item['config'])
    with store.connection() as db:
        rows = [json.loads(r[0]) for r in db.execute('SELECT data FROM business_rows WHERE dataset_id=? LIMIT 20', (identity,))]
    return {'model_sample': model_sample(rows, sharing), 'sharing': sharing,
            'preview_token': validation.fingerprint([identity, item['version'], sharing, body.get('active') is True])}


def _duplicate(db, dataset, batch, key, replace):
    row = db.execute('SELECT data FROM business_datasets WHERE id=?', (dataset,)).fetchone()
    active = [] if replace or not row else json.loads(row[0])['batches']
    return any(r[0] in [*active, batch] for r in db.execute('SELECT batch_id FROM business_rows WHERE dataset_id=? AND business_key=?', (dataset, key)))
