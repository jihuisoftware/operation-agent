"""Immutable final manuscript, ordered assets, sources and policy at reservation time."""
import base64
import hashlib
import json
from pathlib import Path
import uuid
from .policy import now_iso
from .store import encoded


def capture(db, action, version, policy):
    if action['kind'] != 'publish':
        return action
    assets, sources = [], []
    for kind, ids, target in [('asset', action['content'].get('asset_ids', []), assets),
                              ('source', action['content'].get('source_ids', []), sources)]:
        for identity in ids:
            row = db.execute('SELECT data FROM objects WHERE id=? AND kind=?', (identity, kind)).fetchone()
            data = json.loads(row[0]) if row else {'missing': True}
            keys = ('name', 'file', 'sha256', 'authorized', 'revoked') if kind == 'asset' else ('title', 'url', 'author', 'published_at', 'collected_at')
            target.append({'id': identity, **{k: data[k] for k in keys if k in data}, 'missing': not bool(row)})
    identity = 'publication-snapshot:' + uuid.uuid4().hex
    data = {'id': identity, 'created': now_iso(), 'account_id': action['account_id'], 'policy_version': version,
            'policy': policy, 'content': action['content'], 'assets': assets, 'sources': sources,
            'content_hash': hashlib.sha256(encoded(action['content']).encode()).hexdigest()}
    db.execute("INSERT INTO objects VALUES (?, 'publication_snapshot', ?, ?)", (identity, encoded(data), data['created']))
    return {**action, 'snapshot_id': identity}


def read(store, action_id):
    with store.connection() as db:
        row = db.execute('SELECT data FROM actions WHERE id=?', (action_id,)).fetchone()
        if not row:
            raise ValueError('动作不存在')
        action = json.loads(row[0])
        identity = action.get('snapshot_id')
        saved = db.execute("SELECT data FROM objects WHERE id=? AND kind='publication_snapshot'", (identity,)).fetchone()
    if saved:
        return json.loads(saved[0])
    raise ValueError('发布快照不存在')


def asset_bytes(row):
    from plugins.plugin_storage import plugin_data_dir
    filename = row.get('file', '')
    if not filename or Path(filename).name != filename:
        raise ValueError('素材文件不存在')
    raw = (plugin_data_dir('operations') / 'assets' / filename).read_bytes()
    if hashlib.sha256(raw).hexdigest() != row['id']:
        raise ValueError('素材文件校验失败')
    return raw


def image(store, action_id, asset_id):
    snapshot = read(store, action_id)
    asset = next((a for a in snapshot['assets'] if a['id'] == asset_id), None)
    if not asset:
        raise ValueError('图片不属于此最终稿')
    return {'name': asset['name'], 'data': base64.b64encode(asset_bytes(asset)).decode()}
