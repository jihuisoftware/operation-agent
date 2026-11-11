"""Commit a working draft to its original manuscript; never approve, schedule or publish it."""
import hashlib
import json
import uuid

from . import writing_drafts as drafts
from .writing_document import project
from .content_release import fingerprint, validate, sources_unchanged
from .policy import now_iso, local_day
from .store import encoded


def candidate(data):
    projection = project(data['document'], data['cover_asset_id'])
    content = {'title': data['title'], 'body': projection['body'], 'asset_ids': projection['asset_ids'], 'source_ids': data['source_ids']}
    if data['origin']['kind'] == 'original' and data['original']:
        content['authorship'] = {'kind': 'human_original', 'declared': True, 'draft_id': data['id']}
    return content, projection


def preview(store, data):
    from .content import validate_content
    content, projection = candidate(data)
    issues = []
    if data['archived']:
        issues.append('草稿已归档，请另存副本')
    if projection['pending_images']:
        issues.append('有图片未上传或未导入，请完成上传或移除占位')
    if len(content['asset_ids']) > 18:
        issues.append('当前发布通道最多使用 18 张图片')
    with store.connection() as db:
        sources = [dict(row) for row in db.execute("SELECT id FROM objects WHERE kind='source' AND id IN (SELECT value FROM json_each(?))", (encoded(content['source_ids']),))]
        assets = [dict(row) for row in db.execute("SELECT id FROM objects WHERE kind='asset' AND json_extract(data,'$.authorized')=1 "
                    "AND COALESCE(json_extract(data,'$.revoked'),0)=0 AND id IN (SELECT value FROM json_each(?))", (encoded(content['asset_ids']),))]
    try:
        validate_content(content, sources, assets)
    except ValueError as exc:
        issues.append(str(exc))
    if not data['source_ids'] and not (data['origin']['kind'] == 'original' and data['original']):
        issues.append('请选择引用来源；全新手稿也可明确声明原创')
    return {**projection, 'title': content['title'], 'title_characters': len(content['title']), 'revision': data['revision'],
            'issues': list(dict.fromkeys(issues)), 'limits': {'title': 20, 'body': 900, 'images': 18},
            'automatic_cover': not content['asset_ids'], 'can_submit': not issues}


def build(store, data, version, policy):
    from .content_versions import proposed
    from .content_cover import ensure_cover
    content, _ = candidate(data)
    origin = data['origin']
    if origin.get('content_id'):
        from .content_release import manuscript
        parent = manuscript(store, origin['content_id'])
        if fingerprint(parent) != origin['content_revision']:
            raise ValueError('原稿依据已变化，请重新打开原稿创建工作副本')
        if origin['kind'] == 'derived':
            content['source_ids'] = list(dict.fromkeys(parent.get('source_ids', []) + content['source_ids']))
        content = proposed(store, parent, content, policy, version)
    else:
        content = ensure_cover(store, content)
        content.update(manual=True, day=local_day(policy), version=version, scope_topic=policy['topic'], created=now_iso(),
                       ready=True, state='pending_review', quality={'pass': None, 'reason': '手写稿件，等待人工审核'})
    if data['origin']['kind'] == 'original' and not data['original']:
        content.pop('authorship', None)
    content.update(editor_document=data['document'], editor_document_version=data['document_version'], writing_draft_id=data['id'])
    return content


def submit(store, identity, body):
    request_key, digest = drafts.request(body, 'submit', identity)
    with store.connection() as db:
        previous = drafts.replay(db, request_key, digest)
        if previous:
            return previous
        data = drafts.read(db, identity)
    drafts.check_revision(data, body)
    last = data.get('last_submission')
    if last:
        from .content_release import manuscript
        target = manuscript(store, last['content_id'])
        expected = last.get('content_revision')
        if (expected and fingerprint(target) != expected) or (not expected and target.get('edit_revision')):
            raise drafts.DraftConflict('原内容已在其他窗口修改，请重新打开后编辑')
        data['origin'] = {**data['origin'], 'content_id': target['id'], 'content_revision': expected or fingerprint(target)}
    version, policy = store.policy()
    if body.get('version') != version:
        raise drafts.DraftConflict('运营规则已变化，请刷新发布预览')
    checked = preview(store, data)
    if checked['issues']:
        raise ValueError('；'.join(checked['issues']))
    signature = hashlib.sha256(encoded({'draft': data['input_digest'], 'policy': version}).encode()).hexdigest()
    last = data.get('last_submission')
    if last and last['signature'] == signature:
        with store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            drafts.check_revision(drafts.read(db, identity), body)
            previous = drafts.replay(db, request_key, digest)
            return previous or drafts.remember(db, request_key, digest, last)
    content = build(store, data, version, policy)
    from .writing_integrity import asset_revisions, confirm_assets
    with store.connection() as db:
        asset_signatures = asset_revisions(db, content['asset_ids'])
    source_signatures = validate(store, content)
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        previous = drafts.replay(db, request_key, digest)
        if previous:
            return previous
        current = drafts.read(db, identity)
        drafts.check_revision(current, body)
        if (current.get('last_submission') or {}).get('signature') == signature:
            return drafts.remember(db, request_key, digest, current['last_submission'])
        if db.execute('SELECT version FROM settings WHERE id=1').fetchone()[0] != version:
            raise drafts.DraftConflict('提交期间规则已变化，请刷新')
        confirm_assets(db, content['asset_ids'], asset_signatures)
        from .analysis_publication import check
        check(db, {'kind': 'publish', 'content': content, 'human_review': True}, policy)
        if not sources_unchanged(db, {'source_signatures': source_signatures}, policy):
            raise ValueError('提交期间来源已变化，请重新核对')
        origin = data['origin']
        if origin.get('content_id'):
            parent = db.execute("SELECT data FROM objects WHERE id=? AND kind='content'", (origin['content_id'],)).fetchone()
            if not parent or fingerprint(json.loads(parent[0])) != origin['content_revision']:
                raise drafts.DraftConflict('原稿已变化，请重新核对')
        content_id = origin.get('content_id') if last or not data.get('copied_from') else None
        updated = bool(content_id)
        if content_id:
            from .content_edits import write
            write(db, content_id, json.loads(parent[0]), content)
        else:
            content_id = uuid.uuid4().hex
            db.execute("INSERT INTO objects VALUES (?,'content',?,?)", (content_id, encoded(content), now_iso()))
        result = {'id': identity, 'revision': current['revision'], 'content_id': content_id, 'signature': signature,
                  'content_revision': fingerprint(content), 'revision_root_id': content.get('revision_root_id') or content_id,
                  'updated_in_place': updated, 'detail': '已保存到原内容；请重新审核后安排发布' if updated else '已创建待审核内容；尚未授权发布', 'at': now_iso()}
        current['origin'] = {**origin, 'content_id': content_id, 'content_revision': fingerprint(content)}
        current['last_submission'] = result
        drafts.store_draft(db, current)
        return drafts.remember(db, request_key, digest, result)
