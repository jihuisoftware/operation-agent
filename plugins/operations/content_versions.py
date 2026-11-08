"""Human edits derive from a trusted manuscript and retain its evidence lineage."""
import hashlib
import json
import re
import uuid

from .content_release import fingerprint, manuscript, validate, sources_unchanged, load
from .policy import local_day, now_iso
from .store import encoded

EDITABLE = ('title', 'body', 'asset_ids', 'source_ids')


def replay(db, key, digest):
    row = db.execute("SELECT data FROM objects WHERE id=? AND kind='content_version_request'", (key,)).fetchone()
    if not row:
        return None
    value = json.loads(row[0])
    if value['digest'] != digest:
        raise ValueError('同一保存请求不能修改稿件内容')
    return value['result']


def proposed(store, parent, body, policy, version):
    value = {key: body.get(key, parent.get(key, [] if key.endswith('_ids') else '')) for key in EDITABLE}
    from .content import validate_content
    from .organization import material_id
    sources = store.objects('source')
    assets = [row for row in store.objects('asset') if row.get('authorized') and not row.get('revoked')]
    validate_content(value, sources, assets)
    from .content_revision import revised_cover
    from .content_cover import ensure_cover
    value = revised_cover(store, parent, value) if value['asset_ids'] == parent.get('asset_ids') else ensure_cover(store, value)
    if 'cover_origin' not in value and value['asset_ids']:
        cover = next((row for row in assets if row['id'] == value['asset_ids'][0]), {})
        value['cover_origin'] = 'generated_typography' if cover.get('generated_typography') else 'user_selected'
    for key in ('analysis_context', 'selected_topic'):
        if key in parent and key not in value:
            value[key] = parent[key]
    evidence = [row for row in parent.get('organized_evidence', []) if row['id'] in value['source_ids']]
    signatures = list(parent.get('organization_ids', []))
    for source in sources:
        if source['id'] in value['source_ids'] and source['id'] not in parent.get('source_ids', []):
            signature = material_id(policy, source)
            evidence.append({'id': source['id'], 'organization_id': signature})
            signatures.append(signature)
    value.update(organized_evidence=evidence, organization_ids=list(dict.fromkeys(signatures)),
                 parent_content_id=parent['id'], revision_root_id=parent.get('revision_root_id') or parent['id'],
                 manual_revision=True, manual=True, version=version, scope_topic=policy['topic'],
                 day=parent.get('day', local_day(policy)) if value.get('analysis_context') else local_day(policy),
                 created=now_iso(), ready=True, state='pending_review', quality={'pass': None, 'reason': '人工编辑版本，等待审核'})
    # Legacy manual drafts may have no organization signatures to inherit.
    if not signatures:
        value.pop('organization_ids')
    from .industry import check_public_context
    check_public_context(store, value, policy, value['day'])
    return value


def create(store, identity, body):
    request = body.get('request_id')
    if not isinstance(request, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', request):
        raise ValueError('保存请求标识无效')
    allowed = {*EDITABLE, 'request_id', 'version', 'content_revision', 'cancel_original_schedule', 'expected_release_revision'}
    if set(body) - allowed:
        raise ValueError('依据与版本关联由服务端继承，不能由请求修改')
    if type(body.get('cancel_original_schedule', False)) is not bool:
        raise ValueError('取消原排期参数无效')
    key = 'content-version-request:' + request
    digest = hashlib.sha256(encoded({'parent': identity, 'body': body}).encode()).hexdigest()
    with store.connection() as db:
        previous = replay(db, key, digest)
    if previous:
        return previous
    version, policy = store.policy()
    parent = manuscript(store, identity)
    if body.get('version') != version or body.get('content_revision') != fingerprint(parent):
        raise ValueError('原稿或规则已变化，请刷新后编辑')
    value = proposed(store, parent, body, policy, version)
    signatures = validate(store, value)
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        previous = replay(db, key, digest)
        if previous:
            return previous
        current = json.loads(db.execute("SELECT data FROM objects WHERE kind='content' AND id=?", (identity,)).fetchone()[0])
        if db.execute('SELECT version FROM settings WHERE id=1').fetchone()[0] != version or fingerprint(current) != body['content_revision']:
            raise ValueError('编辑期间原稿或规则已变化，请刷新')
        from .analysis_publication import check
        check(db, {'kind': 'publish', 'content': value, 'human_review': True}, policy)
        if not sources_unchanged(db, {'source_signatures': signatures}, policy):
            raise ValueError('编辑期间来源已变化，请刷新后核对')
        release = load(db, identity)
        if body.get('cancel_original_schedule'):
            cancel_schedule(db, identity, release, body.get('expected_release_revision'))
        child = uuid.uuid4().hex
        db.execute("INSERT INTO objects VALUES (?,'content',?,?)", (child, encoded(value), value['created']))
        result = {'id': child, 'parent_content_id': identity, 'original_schedule_retained': bool(release and release['state'] == 'scheduled'),
                  'detail': '已保存新的待审核版本，尚未授权发布'}
        db.execute("INSERT INTO objects VALUES (?,'content_version_request',?,?)", (key, encoded({'digest': digest, 'result': result}), now_iso()))
    return result


def cancel_schedule(db, identity, release, revision):
    if not release or release['state'] != 'scheduled' or release['revision'] != revision:
        raise ValueError('原排期已变化，请刷新后决定是否取消')
    if db.execute("SELECT 1 FROM actions WHERE kind='publish' AND json_extract(data,'$.content.id')=?", (identity,)).fetchone():
        raise ValueError('原版本已建立发布动作，请先核对，不能同时取消排期')
    release.update(state='cancelled', revision=revision + 1)
    db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(release), 'content-release:' + identity))
