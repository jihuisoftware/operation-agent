"""Mutable, scoped writing copies; autosave never creates a publishable manuscript."""
import hashlib
import json
import re
import uuid

from .store import encoded
from .policy import now_iso
from .writing_document import validate, SCHEMA_VERSION


class DraftConflict(ValueError):
    pass


def key(identity):
    if not isinstance(identity, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', identity):
        raise ValueError('草稿标识无效')
    return 'writing-draft:' + identity


def read(db, identity):
    row = db.execute("SELECT data FROM objects WHERE id=? AND kind='writing_draft'", (key(identity),)).fetchone()
    if not row:
        raise KeyError('写作草稿不存在')
    return json.loads(row[0])


def request(body, operation, identity):
    value = body.get('request_id')
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', value):
        raise ValueError('请求标识无效')
    digest = hashlib.sha256(encoded({'operation': operation, 'id': identity, 'body': body}).encode()).hexdigest()
    return 'writing-request:' + value, digest


def replay(db, request_key, digest):
    row = db.execute("SELECT data FROM objects WHERE id=? AND kind='writing_request'", (request_key,)).fetchone()
    if not row:
        return None
    data = json.loads(row[0])
    if data['digest'] != digest:
        raise DraftConflict('同一请求标识不能用于不同修改')
    return data['result']


def remember(db, request_key, digest, result):
    db.execute("INSERT INTO objects VALUES (?,'writing_request',?,?)", (request_key, encoded({'digest': digest, 'result': result}), now_iso()))
    return result


def fields(body):
    allowed = {'title', 'document', 'document_version', 'source_ids', 'original', 'cover_asset_id'}
    value = {name: body[name] for name in allowed if name in body}
    if not isinstance(value.get('title'), str) or len(value['title']) > 200:
        raise ValueError('草稿标题最多 200 字')
    if value.get('document_version') != SCHEMA_VERSION:
        raise ValueError('文档版本不受支持，请更新客户端')
    value['document'] = validate(value.get('document'))
    source_ids = value.get('source_ids', [])
    if not isinstance(source_ids, list) or len(source_ids) > 200 or any(not isinstance(v, str) or not 0 < len(v) <= 160 for v in source_ids):
        raise ValueError('引用来源格式无效')
    if type(value.get('original', False)) is not bool or not isinstance(value.get('cover_asset_id', ''), str):
        raise ValueError('草稿声明或封面格式无效')
    if len(value.get('cover_asset_id', '')) > 160:
        raise ValueError('封面标识无效')
    value.update(source_ids=list(dict.fromkeys(source_ids)), original=value.get('original', False), cover_asset_id=value.get('cover_asset_id', ''))
    return value


def input_digest(data):
    return hashlib.sha256(encoded({name: data[name] for name in ('title', 'document', 'document_version', 'source_ids', 'original', 'cover_asset_id')}).encode()).hexdigest()


def check_revision(data, body):
    if data.get('archived'):
        raise DraftConflict('草稿已归档，可另存副本继续编写')
    if type(body.get('expected_revision')) is not int or body['expected_revision'] != data['revision']:
        raise DraftConflict('草稿已在其他窗口更新；请另存副本或重新载入服务器版本')


def store_draft(db, data):
    db.execute("INSERT INTO objects VALUES (?,'writing_draft',?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
               (key(data['id']), encoded(data), data['created']))


def acknowledgment(data):
    return {name: data.get(name) for name in ('id', 'revision', 'updated', 'input_digest', 'last_submission', 'cover_asset_id')}


def create(store, body):
    identity = body.get('id') or uuid.uuid5(uuid.NAMESPACE_URL, str(body.get('request_id'))).hex
    record_key = key(identity)
    receipt, digest = request(body, 'create', identity)
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        previous = replay(db, receipt, digest)
        if previous:
            return previous
        if db.execute('SELECT 1 FROM objects WHERE id=?', (record_key,)).fetchone():
            raise DraftConflict('草稿标识已存在，请重新打开或另存副本')
        from .writing_origin import initial
        data = initial(db, body)
        stamp = now_iso()
        data.update(id=identity, revision=1, created=stamp, updated=stamp, archived=False)
        data['input_digest'] = input_digest(data)
        store_draft(db, data)
        return remember(db, receipt, digest, acknowledgment(data))


def save(store, identity, body):
    receipt, digest = request(body, 'save', identity)
    value = fields(body)
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        previous = replay(db, receipt, digest)
        if previous:
            return previous
        data = read(db, identity)
        check_revision(data, body)
        if data['origin']['kind'] == 'derived' and value['original']:
            raise ValueError('派生稿件必须保留原稿依据，不能改为无来源原创')
        if input_digest(value) != data['input_digest']:
            data.update(value, revision=data['revision'] + 1, updated=now_iso(), input_digest=input_digest(value))
            store_draft(db, data)
        return remember(db, receipt, digest, acknowledgment(data))


def archive(store, identity, body):
    receipt, digest = request(body, 'archive', identity)
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        previous = replay(db, receipt, digest)
        if previous:
            return previous
        data = read(db, identity)
        check_revision(data, body)
        data.update(archived=True, revision=data['revision'] + 1, updated=now_iso())
        store_draft(db, data)
        return remember(db, receipt, digest, acknowledgment(data))


def listing(store, before=''):
    with store.connection() as db:
        rows = db.execute("SELECT json_extract(data,'$.id') AS id,json_extract(data,'$.title') AS title,"
            "json_extract(data,'$.updated') AS updated,json_extract(data,'$.revision') AS revision,"
            "json_extract(data,'$.last_submission.content_id') AS content_id "
            "FROM objects WHERE kind='writing_draft' AND json_extract(data,'$.archived')=0 "
            "AND (?='' OR json_extract(data,'$.updated')||id<?) ORDER BY json_extract(data,'$.updated') DESC,id DESC LIMIT 31", (before, before)).fetchall()
    page = [dict(row) for row in rows[:30]]
    return {'items': page, 'next': page[-1]['updated'] + key(page[-1]['id']) if len(rows) > 30 else None}


def detail(store, identity):
    with store.connection() as db:
        data = read(db, identity)
    from .writing_submission import preview
    return {**data, 'policy_version': store.policy()[0], 'preview': preview(store, data)}
