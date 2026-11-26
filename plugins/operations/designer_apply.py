"""Authorize candidates against the manuscript revision that requested them."""
from . import designer_jobs as jobs
from .content_release import fingerprint, load
from .store import encoded


def verified(store, db, job):
    draft = jobs.current(db, job)
    if job['state'] != 'completed':
        raise ValueError(job.get('error') or '候选封面尚未完成')
    for asset in {job['asset_id'], job['background']}:
        if not db.execute("SELECT 1 FROM objects WHERE id=? AND kind='asset' AND json_extract(data,'$.authorized')=1 "
                          "AND coalesce(json_extract(data,'$.revoked'),0)=0", (asset,)).fetchone():
            raise ValueError('素材已撤回，请重新选择')
        if store.workspace and not db.execute(
                "SELECT 1 FROM directory.resources WHERE business_id=? AND kind='asset' AND id=? "
                "AND json_extract(data,'$.authorized')=1 AND coalesce(json_extract(data,'$.revoked'),0)=0",
                (store.scope['business_id'], asset)).fetchone():
            raise ValueError('业务素材授权已变化，请重新选择')
    return draft


def apply(store, job_id, body):
    from .content_versions import create
    from .writing_document import project
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        job = jobs.read(db, job_id)
        if (body.get('kind'), body.get('origin_id')) != (job['kind'], job['origin_id']):
            raise ValueError('封面不属于当前稿件')
        if 'applied' in job:
            return job['applied']
        draft = verified(store, db, job)
        if job['kind'] == 'writing':
            # Writer saves through its existing revision-checked autosave journal.
            return {'asset_id': job['asset_id'], 'revision': job['revision']}
        images = (project(draft['editor_document'])['asset_ids'] if draft.get('editor_document')
                  else draft.get('asset_ids', [])[1:])
        ids = list(dict.fromkeys([job['asset_id'], *images]))
    return create(store, job['origin_id'], {'request_id': 'apply-' + job['digest'], 'asset_ids': ids,
                  'content_revision': job['revision'], 'version': job['version'],
                  'expected_release_revision': job['release_revision'], 'designer_job_id': job_id})


def automatic(store, draft, policy, version):
    from .content_revision import guard
    if draft.get('version') != version:
        raise ValueError('运营规则已变化，请重新生成稿件')
    guard(store, policy, version, draft)
    if draft.get('designer_applied_title') == draft['title'] and draft.get('asset_ids'):
        return draft
    previous = draft.get('designer_background_job')
    body = {'kind': 'content', 'origin_id': draft['id'], 'request_id': draft['id'], 'version': version,
            'revision': fingerprint(draft), 'mode': 'reuse' if previous else 'ai', 'title': draft['title'],
            'style': policy['designer_style'], 'previous': previous}
    job = jobs.start(store, body, automatic=True)
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        current = verified(store, db, job)
        release = load(db, draft['id'])
        if (release and release['state'] != 'cancelled') or db.execute(
                "SELECT 1 FROM actions WHERE kind='publish' AND json_extract(data,'$.content.id')=?", (draft['id'],)).fetchone():
            raise ValueError('稿件已有排期或发布记录，候选封面已保留')
        current.update(asset_ids=[job['asset_id']], cover_origin='designer', designer_required=True,
                       designer_background_job=previous or job['id'], designer_applied_title=draft['title'])
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(current), draft['id']))
    return {**current, 'id': draft['id']}
