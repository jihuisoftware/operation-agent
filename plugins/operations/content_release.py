"""Human review binds one immutable manuscript and one scheduled publication."""
from datetime import datetime, UTC
import hashlib
import json

from .store import encoded
from .policy import now_iso


def fingerprint(content):
    keys = ('title', 'body', 'asset_ids', 'source_ids', 'organization_ids', 'analysis_context')
    value = {key: content.get(key) for key in keys}
    value.update({key: content[key] for key in ('editor_document', 'editor_document_version', 'authorship', 'edit_revision') if key in content})
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def load(db, identity):
    row = db.execute("SELECT data FROM objects WHERE kind='content_release' AND id=?", ('content-release:' + identity,)).fetchone()
    return json.loads(row[0]) if row else None


def manuscript(store, identity):
    with store.connection() as db:
        row = db.execute("SELECT data FROM objects WHERE kind='content' AND id=?", (identity,)).fetchone()
    if not row:
        raise ValueError('内容不存在')
    return {**json.loads(row[0]), 'id': identity}


def validate(store, content, *, require_assets=True):
    from .content import validate_content
    from .publication_snapshot import asset_bytes
    sources = store.objects('source')
    assets = [a for a in store.objects('asset') if a.get('authorized') and not a.get('revoked')]
    validate_content(content, sources, assets, require_assets=require_assets)
    for asset in assets:
        if asset['id'] in content['asset_ids']:
            asset_bytes(asset)
    from .organization import material_id
    signatures = content.get('organization_ids')
    if signatures and any(material_id(store.policy()[1], row) not in signatures for row in sources if row['id'] in content['source_ids']):
        raise ValueError('来源依据已变化，请修改内容后重新审核')
    return {row['id']: material_id(store.policy()[1], row) for row in sources if row['id'] in content['source_ids']}


def account(store, policy):
    from .login_status import catalog
    login = next(row for row in catalog(store)['platforms'] if row['id'] == 'xiaohongshu')
    identity = policy['account_id'] or login['account_id']
    if not identity:
        raise ValueError('请先登录并确认发布账号')
    scope = store.workspace.resolve(store.scope['business_id'], store.scope['id'])['account'] if store.workspace else ''
    return identity, scope


def review(store, identity, body, *, automatic=None):
    if 'publish_at' in body:
        raise ValueError('稿件改为按账号自动排期，请刷新后重新审核')
    if type(body.get('expected_revision')) is not int or body['expected_revision'] < 0:
        raise ValueError('审核版本无效，请刷新')
    content = manuscript(store, identity)
    version, policy = store.policy()
    if body.get('version') != version or body.get('content_revision') != fingerprint(content):
        raise ValueError('规则或稿件已变化，请刷新后重新审核')
    source_signatures = validate(store, content)
    who, scope = account(store, policy)
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT version FROM settings WHERE id=1').fetchone()[0] != version:
            raise ValueError('规则已变化，请重新审核')
        current = json.loads(db.execute("SELECT data FROM objects WHERE kind='content' AND id=?", (identity,)).fetchone()[0])
        if fingerprint(current) != body['content_revision']:
            raise ValueError('稿件已变化，请重新审核')
        from .analysis_publication import check
        check(db, {'kind': 'publish', 'content': content, 'human_review': True}, policy)
        previous = load(db, identity)
        if (previous or {}).get('revision', 0) != body.get('expected_revision'):
            raise ValueError('审核排期已变化，请刷新')
        from .content import content_digest
        from .publication_attempts import guard
        action = {'kind': 'publish', 'account_id': who, 'target': content_digest(content)}
        guard(db, action)
        from .publication_shared import history
        history(store, db, action)
        now = getattr(store, 'execution_now', None) or datetime.now(UTC)
        value = {'content_id': identity, 'content_revision': fingerprint(content), 'revision': body['expected_revision'] + 1,
                 'version': version, 'account_id': who, 'account_scope': scope, 'state': 'scheduled',
                 'publish_at': None, 'reviewed_at': now.isoformat(), 'reviewer': 'human'}
        if automatic is not None:
            from .automatic_review import authorize_decision
            authorize_decision(db, current, automatic)
            if (automatic.get('account_id'), automatic.get('account_scope')) != (who, scope):
                raise ValueError('账号已变化，自动审核已失效')
            value.update(reviewer='automatic', automatic_review=automatic)
        from .account_calendar import assign, approval_policy
        value.update(approval_policy=approval_policy(policy), reviewed_version=version)
        if store.workspace:
            from .account_calendar import account_key
            if scope != account_key(store,db):
                raise ValueError('关联账号已变化，请重新审核')
        assign(store, db, policy, now, value)
        value['source_signatures'] = source_signatures
        if not sources_unchanged(db, value, policy):
            raise ValueError('审核期间来源已变化，请刷新后重新核对')
        db.execute("INSERT OR REPLACE INTO objects VALUES (?, 'content_release', ?, ?)", ('content-release:' + identity, encoded(value), now_iso()))
    store.event('content_approved', value)
    return value


def cancel(store, identity, revision):
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        value = load(db, identity)
        if not value or value['revision'] != revision:
            raise ValueError('审核排期已变化，请刷新')
        from .content_edits import latest_action
        if latest_action(db, identity, manuscript(store, identity)):
            raise ValueError('发布动作已建立，请在执行记录中核对或取消，不能假定撤回成功')
        value.update(state='cancelled', revision=revision + 1)
        from .review_policy import hold_manuscript
        hold_manuscript(db, identity, '人工取消排期，等待人工审核')
        db.execute("UPDATE objects SET data=? WHERE id=?", (encoded(value), 'content-release:' + identity))
    return value


def authorization(store, db, action, version, policy):
    if action['kind'] != 'publish':
        return False
    value = load(db, action['content']['id'])
    if not value or value['state'] not in {'scheduled', 'paused', 'needs_attention'} or value['version'] != version or action.get('release_revision', action.get('human_review')) != value['revision']:
        return False
    row = db.execute("SELECT data FROM objects WHERE kind='content' AND id=?", (action['content']['id'],)).fetchone()
    if not row or fingerprint(json.loads(row[0])) != value['content_revision']:
        return False
    if value.get('reviewer') == 'automatic':
        from .automatic_review import decision_current
        if not decision_current(db, json.loads(row[0]), value.get('automatic_review') or {}):
            return False
    if not sources_unchanged(db, value, policy):
        return False
    scope = db.execute('SELECT account FROM directory.businesses WHERE id=?', (store.scope['business_id'],)).fetchone()[0] if store.workspace else ''
    return (value['content_revision'] == fingerprint(action['content']) and value['account_id'] == action['account_id']
            and value['account_scope'] == scope and datetime.fromisoformat(value['publish_at']) <= (getattr(store, 'execution_now', None) or datetime.now(UTC)))


def sources_unchanged(db, release, policy):
    from .organization import material_id
    for identity, signature in release.get('source_signatures', {}).items():
        row = db.execute("SELECT data FROM objects WHERE kind='source' AND id=?", (identity,)).fetchone()
        if not row or material_id(policy, {**json.loads(row[0]), 'id': identity}) != signature:
            return False
    return True
