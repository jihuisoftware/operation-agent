"""Attach automatic visuals only to an unapproved, unchanged draft."""
import json

from .store import encoded


def prepare(store, draft):
    from .visual_jobs import automatic
    from .content_revision import guard
    from .content_release import fingerprint, load
    version, policy = store.policy()
    if draft.get('version') != version:
        raise ValueError('运营规则已变化，保留旧稿，不继续自动生图')
    guard(store, policy, version, draft)
    updated = automatic(store, draft)
    guard(store, policy, version, draft)
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        current = json.loads(db.execute("SELECT data FROM objects WHERE id=? AND kind='content'", (draft['id'],)).fetchone()[0])
        job = json.loads(db.execute("SELECT data FROM objects WHERE id=? AND kind='visual_set'", (updated['visual_set_id'],)).fetchone()[0])
        if updated.get('visual_error') and job['state'] == 'completed':
            raise ValueError('组图已完成，请刷新稿件后继续')
        if not updated.get('visual_error') and (job['state'] != 'completed' or [page['asset_id'] for page in job['pages']] != updated['asset_ids']):
            raise ValueError('组图已被更新，保留现有草稿等待核对')
        release = load(db, draft['id'])
        if (release and release['state'] != 'cancelled') or db.execute(
                "SELECT 1 FROM actions WHERE kind='publish' AND json_extract(data,'$.content.id')=?", (draft['id'],)).fetchone():
            raise ValueError('稿件已有排期或发布动作，保留现有封面')
        if fingerprint(current) != fingerprint(draft) or db.execute('SELECT version FROM settings WHERE id=1').fetchone()[0] != version:
            raise ValueError('生成期间稿件变化，图片已保留但未应用')
        changed = {**current, **{key: updated.get(key) for key in ('asset_ids', 'visual_set_id', 'visual_plan', 'visual_error', 'visual_review')}}
        if updated.get('visual_error'):
            changed['ready'] = False
            changed.pop('automatic_review', None)
            changed.update({key: updated[key] for key in ('cover', 'cover_origin', 'cover_candidates', 'cover_article_title') if key in updated})
        elif current.get('cover_origin') == 'generated_typography' and current.get('asset_ids') != updated['asset_ids']:
            for key in ('cover_origin', 'cover_candidates', 'cover_article_title'):
                changed.pop(key, None)
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(changed), draft['id']))
    return {**changed, 'id': draft['id']}
