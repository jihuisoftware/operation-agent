"""Use a local template for automatic manuscripts with no configured image model."""
import json

from . import visual_provider
from .content_cover import ensure_cover
from .content_release import fingerprint, load
from .content_revision import guard
from .store import encoded

NOTE = '未配置生图模型，已采用本地模板封面'
# Old preflight failures have a human-readable reason only. Never reinterpret a
# provider error or partially completed job as permission to change modes.
_MAGAZINE_PREFLIGHT = '尚未配置可用的生图模型，请在模型能力设置中配置；文字草稿已保留'
_DESIGNER_PREFLIGHT = '请先配置可用的生图模型'


def no_image_model():
    from hermes_cli.config import load_config_readonly
    config = load_config_readonly().get('image_gen') or {}
    # The bundled managed route can be present even on a fresh Profile without
    # a model. An explicitly selected model/backend that is down stays an error.
    if config.get('model') or config.get('provider') not in (None, '', 'nous'):
        return False
    return not visual_provider.available()


def unstarted(db, draft):
    root = draft.get('revision_root_id') or draft['id']
    rows = db.execute("SELECT data FROM objects WHERE kind='visual_set' AND json_extract(data,'$.allowance_key')=?",
                      ('content:' + root,))
    for row in rows:
        job = json.loads(row[0])
        if (job['state'] != 'needs_attention' or job['detail'] != _MAGAZINE_PREFLIGHT
                or job.get('cancelled') or job.get('attempts') or job.get('pages') or job.get('art') or job.get('plan')):
            return False
    for row in db.execute("SELECT data FROM objects WHERE kind='designer_cover_job' AND id IN (?,?)",
                          ('designer-auto:' + root, 'designer-auto:' + draft['id'])):
        job = json.loads(row[0])
        if job['state'] != 'failed' or job.get('charged') or job.get('error') != _DESIGNER_PREFLIGHT:
            return False
    return True


def apply_if_needed(store, draft, policy, version):
    if not (draft.get('visual_required') or draft.get('designer_required')):
        return draft
    if draft.get('asset_ids') and draft.get('cover_origin') != 'generated_typography':
        return draft
    if draft.get('visual_error') and draft['visual_error'] != _MAGAZINE_PREFLIGHT:
        return draft
    if not no_image_model():
        return draft
    if draft.get('version') != version:
        raise ValueError('运营规则已变化，请重新核对原稿')
    guard(store, policy, version, draft)
    with store.connection() as db:
        if not unstarted(db, draft):
            return draft
    if draft.get('asset_ids'):
        from .visual_sets import asset_bytes
        asset_bytes(store, draft['asset_ids'][0])
    cover = ensure_cover(store, draft)
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        current = json.loads(db.execute("SELECT data FROM objects WHERE kind='content' AND id=?", (draft['id'],)).fetchone()[0])
        if fingerprint(current) != fingerprint(draft) or db.execute('SELECT version FROM settings WHERE id=1').fetchone()[0] != version:
            raise ValueError('稿件或规则已变化，请重新核对封面')
        if current.get('template_fallback') and not (current.get('visual_required') or current.get('designer_required')):
            return {**current, 'id': draft['id']}
        release = load(db, draft['id'])
        if (release and release['state'] != 'cancelled') or db.execute(
                "SELECT 1 FROM actions WHERE kind='publish' AND json_extract(data,'$.content.id')=?", (draft['id'],)).fetchone():
            raise ValueError('稿件已有排期或发布记录，请人工核对封面')
        if not unstarted(db, draft):
            return draft
        current.update({key: cover[key] for key in ('asset_ids', 'cover', 'cover_origin', 'cover_candidates',
                                                    'cover_article_title') if key in cover})
        current.update(visual_required=False, designer_required=False, visual_error='', visual_review=None,
                       template_fallback=NOTE, ready=False, review_pending=True)
        current.pop('automatic_review', None)
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(current), draft['id']))
    store.progress(NOTE, {'content_id': draft['id'], 'asset_id': current['asset_ids'][0]})
    return {**current, 'id': draft['id']}
