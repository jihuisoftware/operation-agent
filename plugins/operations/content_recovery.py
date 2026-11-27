"""Persist generated text before review, and resume only unchanged production inputs."""
import hashlib
import json

from .store import encoded


def fingerprint(data, version, analysis):
    lineage = {key: value for key, value in (analysis or {}).items()
               if key not in {'analytics_id', 'industry_id', 'generated_at'}}
    return hashlib.sha256(encoded({'version': version, 'input': data, 'analysis': lineage}).encode()).hexdigest()


def pending(store, day, signature):
    with store.connection() as db:
        protected = {row[0] for row in db.execute("SELECT json_extract(data,'$.content_id') FROM objects WHERE kind='content_release' AND json_extract(data,'$.state')!='cancelled'")}
        protected.update(row[0] for row in db.execute("SELECT json_extract(data,'$.content.id') FROM actions WHERE kind='publish'"))
    candidates = [row for row in store.objects('content', day) if row.get('production_input') == signature and row['id'] not in protected]
    if getattr(store,'daily_writing',False):
        candidates = [row for row in candidates if not row.get('debug_id') and row.get('draft_mode')!='new_variant']
    return max(candidates, key=lambda row: (row.get('created', ''), row.get('revision_index', 0)), default=None)


def review(store, policy, day, version, draft, sources):
    from .template_fallback import no_image_model, unstarted
    from .content import check_content
    from .content_revision import guard, root, revise, REVIEW_VERSION, MAX_REVISIONS
    from .model_budget import remaining_calls
    while True:
        with store.connection() as db:
            template_only = draft.get('visual_required') and no_image_model() and unstarted(db, draft)
        if (draft.get('designer_required') or template_only or
                (not draft.get('visual_required') and not draft.get('asset_ids'))):
            from .designer_apply import automatic
            try:
                draft = automatic(store, draft, policy, version, template_only=template_only)
            except ValueError as exc:
                mark_missing(store, draft, str(exc))
                return {'content_id': draft['id'], 'ready': False, 'missing': ['待补封面'], 'reason': str(exc)}
        if draft.get('visual_required'):
            from .visual_pipeline import prepare
            draft = prepare(store, draft)
            if draft.get('visual_error'):
                return {'content_id': draft['id'], 'ready': False, 'missing': ['组图尚未完成'], 'reason': draft['visual_error'], 'revision_count': 0}
        guard(store, policy, version, draft)
        if draft.get('review_pending') or draft.get('review_version') != REVIEW_VERSION:
            quality = check_content(store, policy, day, version, draft, sources)
            guard(store, policy, version, draft)
            draft = save_review(store, version, draft, quality)
        count = root(store, draft).get('auto_revision_attempts', 0)
        if any(issue.get('code') == 'visual' for issue in draft['quality'].get('issues', [])):
            return outcome(draft, count, '请在杂志组图中检查或重做主视觉，文字稿已保留')
        if draft['quality'].get('pass') is True or count >= MAX_REVISIONS:
            return outcome(draft, count, '已达到两轮自动修订上限，需人工检查' if not draft['quality'].get('pass') else '')
        if remaining_calls(store, policy, day) < 2:
            return outcome(draft, count, '剩余模型额度不足以完成修订和复检，草稿已保存')
        child, error = revise(store, policy, day, version, draft, sources)
        if child is None:
            return outcome(draft, root(store, draft).get('auto_revision_attempts', 0), error)
        draft = child


def save_review(store, version, draft, quality):
    from .content_revision import REVIEW_VERSION
    ready = quality.get('pass') is True and bool(draft.get('asset_ids')) and (not draft.get('visual_required') or (draft.get('visual_review') or {}).get('pass') is True)
    updated = {**draft, 'quality': quality, 'ready': ready, 'review_pending': False, 'review_version': REVIEW_VERSION,
               'state': 'pending_review' if ready else 'needs_material' if not draft.get('asset_ids') else 'needs_review'}
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        current = db.execute('SELECT version FROM settings WHERE id=1').fetchone()[0]
        if current != version:
            raise ValueError('检查期间规则已变更，草稿已保留，请按新规则重新执行')
        stored = json.loads(db.execute("SELECT data FROM objects WHERE kind='content' AND id=?", (draft['id'],)).fetchone()[0])
        updated = {**stored, **updated}
        db.execute("UPDATE objects SET data=? WHERE kind='content' AND id=?", (encoded(updated), draft['id']))
        from .daily_tasks import record_draft
        record_draft(store, db, updated)
    store.event('content_review_completed', {'content_id': draft['id'], 'ready': ready, 'state': 'completed' if ready else 'needs_attention',
                                           'reason': quality.get('reason'), 'issues': quality.get('issues', [])})
    return updated


def outcome(draft, count, extra=''):
    missing = ([] if draft.get('asset_ids') else ['缺少获授权图片']) + ([] if draft['quality'].get('pass') is True else ['自动质量检查未通过'])
    if draft.get('visual_required') and (draft.get('visual_review') or {}).get('pass') is not True:
        missing.append('组图视觉检查待人工核对')
        extra = '；'.join(filter(None, [extra, (draft.get('visual_review') or {}).get('reason')]))
    reason = '；'.join(part for part in (draft.get('template_fallback'), draft['quality'].get('reason'), extra) if part)
    return {'content_id': draft['id'], 'ready': draft['ready'], 'missing': missing, 'reason': reason, 'revision_count': count}

def mark_missing(store, draft, reason):
    from .content_release import fingerprint, load
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT data FROM objects WHERE id=? AND kind='content'", (draft['id'],)).fetchone()
        if row and fingerprint(json.loads(row[0])) == fingerprint(draft) and (load(db, draft['id']) or {}).get('state') in (None, 'cancelled') and not db.execute(
                "SELECT 1 FROM actions WHERE kind='publish' AND json_extract(data,'$.content.id')=?", (draft['id'],)).fetchone():
            db.execute("UPDATE objects SET data=json_set(data,'$.cover_error',?,'$.state','needs_material') WHERE id=?",
                       (reason, draft['id']))
