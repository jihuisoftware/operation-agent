"""Authorize candidates against the manuscript revision that requested them."""
from . import designer_jobs as jobs
from .content_release import fingerprint, load
from .store import encoded


def verified(store, db, job):
    draft = jobs.current(db, job)
    if job['state'] != 'completed':
        raise ValueError(job.get('error') or '候选封面尚未完成')
    for asset in {job['asset_id'], job.get('background')} - {None}:
        if not db.execute("SELECT 1 FROM objects WHERE id=? AND kind='asset' AND json_extract(data,'$.authorized')=1 "
                          "AND coalesce(json_extract(data,'$.revoked'),0)=0", (asset,)).fetchone():
            raise ValueError('素材已撤回，请重新选择')
        if store.workspace and not db.execute(
                "SELECT 1 FROM directory.resources WHERE business_id=? AND kind='asset' AND id=? "
                "AND json_extract(data,'$.authorized')=1 AND coalesce(json_extract(data,'$.revoked'),0)=0",
                (store.scope['business_id'], asset)).fetchone():
            raise ValueError('业务素材授权已变化，请重新选择')
    return draft


def manual_candidate(db, job, asset):
    """Bind an explicitly selected reviewed round to a manual-only application receipt."""
    import hashlib
    chosen = next((r for r in job.get('rounds', []) if r['asset_id'] == asset), None)
    if job['state'] not in ('completed', 'failed', 'unknown') or not chosen:
        raise ValueError('所选封面不属于已结束的评审轮次')
    key = 'designer-choice:' + hashlib.sha256(encoded([job['id'], asset]).encode()).hexdigest()
    selected = {**job, 'id': key, 'asset_id': asset, 'background': chosen.get('background'), 'automatic': False, 'charged': False, 'state': 'completed',
                'digest': key.split(':')[1], 'parent_job': job['id']}
    selected.pop('applied', None)
    from .policy import now_iso
    db.execute('INSERT OR IGNORE INTO objects VALUES (?,?,?,?)', (key, jobs.KIND, encoded(selected), now_iso()))
    return jobs.read(db, key)


def apply(store, job_id, body):
    from .content_versions import create
    from .writing_document import project
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        job = jobs.read(db, job_id)
        if (body.get('kind'), body.get('origin_id')) != (job['kind'], job['origin_id']):
            raise ValueError('封面不属于当前稿件')
        if body.get('candidate_asset'):
            job = manual_candidate(db, job, body['candidate_asset'])
            job_id = job['id']
        if 'applied' in job:
            return job['applied']
        draft = verified(store, db, job)
        if body.get('fill_only') and (draft.get('asset_ids') or db.execute(
                "SELECT 1 FROM actions WHERE kind='publish' AND json_extract(data,'$.content.id')=?", (job['origin_id'],)).fetchone()):
            raise ValueError('稿件已有封面或发布动作')
        if job['kind'] == 'writing':
            # Writer saves through its existing revision-checked autosave journal.
            return {'asset_id': job['asset_id'], 'revision': job['revision'], **({'job_id': job_id} if job.get('parent_job') else {})}
        images = list(draft.get('asset_ids', [])[1:])
        if draft.get('editor_document'):
            images.extend(project(draft['editor_document'])['asset_ids'])
        ids = list(dict.fromkeys([job['asset_id'], *images]))
    return create(store, job['origin_id'], {'request_id': 'apply-' + job['digest'], 'asset_ids': ids,
                  'content_revision': job['revision'], 'version': job['version'],
                  'expected_release_revision': job['release_revision'], 'designer_job_id': job_id})


def automatic(store, draft, policy, version, *, template_only=False):
    from .content_revision import guard
    if draft.get('version') != version:
        raise ValueError('运营规则已变化，请重新生成稿件')
    guard(store, policy, version, draft)
    if draft.get('asset_ids') and (draft.get('cover_origin') == 'user_selected' or draft.get('designer_applied_title') == draft['title']):
        return draft
    from .designer_workflow import candidate
    job = candidate(store, 'content', draft['id'], fingerprint(draft), draft['title'], automatic=True, previous=draft.get('designer_background_job'))
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        current = verified(store, db, job)
        release = load(db, draft['id'])
        if (release and release['state'] != 'cancelled') or db.execute(
                "SELECT 1 FROM actions WHERE kind='publish' AND json_extract(data,'$.content.id')=?", (draft['id'],)).fetchone():
            raise ValueError('稿件已有排期或发布记录，候选封面已保留')
        current.update(asset_ids=[job['asset_id'], *current.get('asset_ids', [])[1:]], cover_origin='designer', designer_required=True,
                       designer_background_job=job['id'], designer_applied_title=draft['title'], cover_error='', visual_required=False if template_only else current.get('visual_required', False))
        if current['asset_ids'] == [job['asset_id']] and job.get('rounds'):
            from .visual_review import remember_cover
            remember_cover(db, current, version, job['rounds'][-1])
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(current), draft['id']))
    return {**current, 'id': draft['id']}

def fill_missing(store, identity, body):
    from .content_release import manuscript
    from .designer_workflow import candidate
    draft = manuscript(store, identity)
    expected = body.get('content_revision')
    if expected != fingerprint(draft) or body.get('version') != store.policy()[0]:
        raise ValueError('稿件或规则已变化，请刷新')
    if draft.get('asset_ids'):
        raise ValueError('稿件已有封面')
    with store.connection() as db:
        release = load(db, identity)
        if (release and release['state'] != 'cancelled') or db.execute(
                "SELECT 1 FROM actions WHERE kind='publish' AND json_extract(data,'$.content.id')=?", (identity,)).fetchone():
            raise ValueError('稿件已有排期或发布记录')
    job = candidate(store, 'content', identity, expected, draft['title'], automatic=False, purpose='fill-missing')
    if job.get('release_revision', 0) != body.get('expected_release_revision', 0):
        raise ValueError('原排期已变化，请刷新稿件')
    return apply(store, job['id'], {'kind': 'content', 'origin_id': identity, 'fill_only': True})
