"""Transfer received-message ownership without granting permission to send."""
import json
from .policy import now_iso


def candidates(store, kind, items):
    if not store.workspace:
        return items
    with store.connection() as db:
        account = db.execute('SELECT account FROM directory.businesses WHERE id=?', (store.scope['business_id'],)).fetchone()[0]
        claimed = {r[0] for r in db.execute('SELECT target FROM directory.account_claims WHERE account_id=? AND kind=? AND topic_id!=?', (account, kind, store.scope['id']))}
    return [item for item in items if item['id'] not in claimed]


def transfer(store, body):
    target = store.workspace.store(body['business_id'], body['topic_id'])
    if target.scope['archived'] or target.scope['id'] == store.scope['id']:
        raise ValueError('请选择其他有效主题')
    source_scope = store.workspace.resolve(store.scope['business_id'], store.scope['id'])
    if target.scope['account'] != source_scope['account']:
        raise ValueError('只能转交给明确共用同一账号的主题')
    with store.connection() as db:
        db.execute('ATTACH DATABASE ? AS destination', (str(target.path),))
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT * FROM objects WHERE id=? AND kind='inbox'", (body['id'],)).fetchone()
        if not row:
            raise ValueError('待处理事项不存在')
        data = json.loads(row['data'])
        if data.get('state') != 'needs_review':
            raise ValueError('只能转交待人工处理的事项')
        claim = db.execute('SELECT * FROM directory.account_claims WHERE account_id=? AND kind=? AND target=?', (source_scope['account'], data['kind'], data['id'])).fetchone()
        if claim and claim['action_id']:
            raise ValueError('已有动作认领，请先在原主题处理，不能重新发送')
        if claim and claim['topic_id'] not in {store.scope['id'], target.scope['id']}:
            raise ValueError('事项已归属其他主题，请刷新后查看')
        db.execute('INSERT INTO directory.account_claims VALUES (?,?,?,?,?) ON CONFLICT(account_id,kind,target) DO UPDATE SET topic_id=excluded.topic_id', (source_scope['account'], data['kind'], data['id'], target.scope['id'], ''))
        moved = {**data, 'state': 'needs_review', 'reason': '人工转交；等待下次执行重新核对网页与规则',
                 'transferred_from': store.scope['id'], 'business_id': target.scope['business_id'], 'topic_id': target.scope['id']}
        db.execute("INSERT INTO destination.objects VALUES (?,'inbox',?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data", (row['id'], json.dumps(moved, ensure_ascii=False), now_iso()))
        data.update(state='transferred', transferred_to=target.scope['id'])
        db.execute('UPDATE objects SET data=? WHERE id=?', (json.dumps(data, ensure_ascii=False), row['id']))
    store.event('inbox_transferred', {'id': row['id'], 'target_business_id': target.scope['business_id'], 'target_topic_id': target.scope['id']})
    return {'ok': True}
