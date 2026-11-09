"""Attach automatic visuals only to an unapproved, unchanged draft."""
import json

from .store import encoded


def prepare(store, draft):
    from .visual_jobs import automatic
    from .content_revision import guard
    from .visual_plan import signature
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
        if not updated.get('visual_error') and (job['state'] != 'completed' or [page['asset_id'] for page in job['pages']] != updated['asset_ids']):
            raise ValueError('组图已被更新，保留现有草稿等待核对')
        if signature(current) != signature(draft):
            raise ValueError('生成期间稿件变化，图片已保留但未应用')
        changed = {**current, **{key: updated.get(key) for key in ('asset_ids', 'visual_set_id', 'visual_plan', 'visual_error', 'visual_review')}}
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(changed), draft['id']))
    return {**changed, 'id': draft['id']}
