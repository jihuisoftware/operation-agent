"""Human edits replace the current manuscript while retaining its evidence and audit history."""
import hashlib
import json
import re

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
    if 'authorship' in parent:
        value['authorship'] = parent['authorship']
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
    if parent.get('editor_document') and value['body'] == parent['body']:
        value.update(editor_document=parent['editor_document'], editor_document_version=parent['editor_document_version'])
    for key in ('analysis_context', 'selected_topic'):
        if key in parent and key not in value:
            value[key] = parent[key]
    from .cover_assets import attach
    attach(store, parent, value, body.get('cover_set_id'))
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
                 created=now_iso(), ready=True, state='pending_review', quality={'pass': None, 'reason': '内容已编辑，等待重新审核'})
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
    allowed = {*EDITABLE, 'request_id', 'version', 'content_revision', 'cancel_original_schedule', 'expected_release_revision', 'cover_set_id'}
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
    from .writing_document import project
    if parent.get('editor_document'):
        if body.get('body', parent['body']) != parent['body']:
            raise ValueError('富文本稿件请在独立写稿页编辑')
        if not set(project(parent['editor_document'])['asset_ids']).issubset(body.get('asset_ids', parent['asset_ids'])):
            raise ValueError('正文中的图片请在独立写稿页删除')
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
        if body.get('expected_release_revision') is not None and (not release or release['revision'] != body['expected_release_revision']):
            raise ValueError('原排期已变化，请刷新后编辑')
        from .content_edits import write
        write(db, identity, current, value)
        result = {'id': identity, 'updated_in_place': True, 'original_schedule_retained': False,
                  'detail': '已更新原内容，原审核与排期已失效；请重新审核后安排发布'}
        db.execute("INSERT INTO objects VALUES (?,'content_version_request',?,?)", (key, encoded({'digest': digest, 'result': result}), now_iso()))
    return result
