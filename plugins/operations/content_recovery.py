"""Persist generated text before review, and resume only unchanged production inputs."""
import hashlib

from .store import encoded


def fingerprint(data, version, analysis):
    lineage = {key: value for key, value in (analysis or {}).items()
               if key not in {'analytics_id', 'industry_id', 'generated_at'}}
    return hashlib.sha256(encoded({'version': version, 'input': data, 'analysis': lineage}).encode()).hexdigest()


def pending(store, day, signature):
    return next((row for row in store.objects('content', day)
                 if row.get('review_pending') and row.get('production_input') == signature), None)


def review(store, policy, day, version, draft, sources):
    from .content import check_content
    quality = check_content(store, policy, day, version, draft, sources)
    ready = quality.get('pass') is True and bool(draft.get('asset_ids'))
    missing = ([] if draft.get('asset_ids') else ['缺少获授权图片']) + ([] if quality.get('pass') is True else ['自动质量检查未通过'])
    updated = {**draft, 'quality': quality, 'ready': ready, 'review_pending': False,
               'state': 'ready' if ready else 'needs_material' if not draft.get('asset_ids') else 'needs_review'}
    if getattr(store, 'debug_id', None):
        updated['debug_id'] = store.debug_id
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        current = db.execute('SELECT version FROM settings WHERE id=1').fetchone()[0]
        if current != version:
            raise ValueError('检查期间规则已变更，草稿已保留，请按新规则重新执行')
        db.execute("UPDATE objects SET data=? WHERE kind='content' AND id=?", (encoded(updated), draft['id']))
    store.event('content_review_completed', {'content_id': draft['id'], 'ready': ready})
    return {'content_id': draft['id'], 'ready': ready, 'missing': missing, 'reason': quality.get('reason')}
