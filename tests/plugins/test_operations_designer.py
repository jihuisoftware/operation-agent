"""Cover receipts are scoped to a revision; paid dispatch has a durable admission."""
import base64
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from PIL import Image
import pytest

from plugins.operations import content_release, designer_apply, designer_jobs, designer_render, visual_provider, writing_drafts
from plugins.operations.store import Store
from tests.plugins import test_operations_content_review as support


_manuscript = support.manuscript


def image():
    buf = BytesIO()
    Image.new('RGB', (640, 800), 'blue').save(buf, 'PNG')
    return buf.getvalue()


def test_handmade_candidate_keeps_bytes_and_requires_current_revision(_manuscript, monkeypatch):
    store, _, _, draft = _manuscript
    monkeypatch.setattr(designer_render, 'check_plugin', lambda: None)
    req = dict(kind='content', origin_id=draft['id'], revision=content_release.fingerprint(draft), version=1,
               mode='upload', request_id='upload', upload={'name': 'cover.png', 'authorized': True,
               'data': base64.b64encode(image()).decode()})
    from threading import Event
    done = Event()
    original = designer_jobs.execute

    def observe(*args):
        try:
            return original(*args)
        finally:
            done.set()
    monkeypatch.setattr(designer_jobs, 'execute', observe)
    first = designer_jobs.start(store, req)
    assert done.wait(10)
    job = designer_jobs.start(store, req)
    assert first['id'] == job['id'] and not job['charged'] and job['state'] == 'completed'
    assert content_release.manuscript(store, draft['id'])['asset_ids'] == draft['asset_ids']
    from plugins.operations.visual_sets import asset_bytes
    assert asset_bytes(store, job['asset_id']) == image()
    designer_apply.apply(store, job['id'], req)
    changed = content_release.manuscript(store, draft['id'])
    assert changed['asset_ids'][0] == job['asset_id'] and changed['state'] == 'pending_review'
    assert designer_apply.apply(store, job['id'], req)['id'] == draft['id']
    with pytest.raises(ValueError, match='授权'):
        designer_jobs.start(store, {**req, 'upload': {**req['upload'], 'authorized': False}})


def test_auto_quota_is_atomic_and_uncertain_call_never_replayed(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    version, policy = store.policy()
    policy.update(enabled=True, topic='杂志', goal='封面', image_mode='designer')
    policy['modules']['content'] = True
    store.configure(policy, version)
    monkeypatch.setattr(designer_render, 'check_plugin', lambda: None)
    monkeypatch.setattr(visual_provider, 'available', lambda: True)
    from plugins.operations import designer_workflow
    monkeypatch.setattr(designer_workflow, 'model_step', lambda owner, job, phase, brief, image=None: (
        {'design': {'title': brief['title'], 'template': 'editorial'}, 'reason': '设计', 'panel': 'bottom', 'background_prompt': '新底图'}
        if phase == 'design' else {'review': {'pass': True, 'reason': '通过', 'issues': []}}))
    calls = []

    def uncertain(*args):
        calls.append(1)
        raise TimeoutError('服务超时')
    monkeypatch.setattr(designer_render, 'generate_background', uncertain)
    reqs = []
    for name in ['one', 'two']:
        draft = {'title': name, 'body': name, 'asset_ids': []}
        identity = store.put('content', draft)
        reqs.append(dict(kind='content', origin_id=identity, revision=content_release.fingerprint(draft), version=1,
                         request_id=name, mode='ai', title=name))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda body: designer_jobs.start(store, body, automatic=True), reqs))
    assert len(calls) == 1
    assert {job['state'] for job in results} == {'failed', 'unknown'}
    for req, job in zip(reqs, results):
        assert designer_jobs.start(store, req, automatic=True)['id'] == job['id']
    assert len(calls) == 1


def test_writing_candidate_denies_revoked_or_foreign_image(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    draft = writing_drafts.create(store, {'request_id': 'my-draft'})
    asset = store.add_asset('x.png', image(), True)
    body = dict(kind='writing', origin_id=draft['id'], revision=1, version=0, mode='upload', request_id='write')
    job, _ = designer_jobs.admit(store, body, False)
    with store.connection() as db:
        job.update(state='completed', asset_id=asset, background=asset)
        designer_jobs.save(db, job)
    with pytest.raises(ValueError, match='不属于'):
        designer_apply.apply(store, job['id'], {**body, 'origin_id': 'foreign'})
    assert designer_apply.apply(store, job['id'], body)['asset_id'] == asset
    with store.connection() as db:
        db.execute("UPDATE objects SET data=json_set(data,'$.revoked',1) WHERE id=?", (asset,))
    with pytest.raises(ValueError, match='已撤回'):
        writing_drafts.save(store, draft['id'], {**writing_drafts.detail(store, draft['id']), 'request_id': 'save',
                            'expected_revision': 1, 'designer_job_id': job['id'], 'cover_asset_id': asset})


def test_automatic_title_revision_reuses_background_and_cannot_approve_stale_cover(_manuscript, monkeypatch):
    from plugins.operations import content_revision
    from plugins.operations.store import encoded
    store, policy, _, draft = _manuscript
    version = store.configure({**policy, 'image_mode': 'designer'}, 1)
    policy = store.policy()[1]
    draft.update(version=version, asset_ids=[], designer_required=True)
    with store.connection() as db:
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(draft), draft['id']))
    from plugins.operations import designer_workflow
    monkeypatch.setattr(designer_workflow, 'model_step', lambda owner, job, phase, brief, image=None: (
        {'design': {'title': brief['title'], 'template': 'editorial'}, 'reason': '设计', 'panel': 'bottom', 'background_prompt': '新底图'}
        if phase == 'design' else {'review': {'pass': True, 'reason': '通过', 'issues': []}}))
    calls = []
    monkeypatch.setattr(designer_render, 'check_plugin', lambda: None)
    monkeypatch.setattr(visual_provider, 'available', lambda: True)

    def background(owner, spec):
        calls.append(spec)
        return owner.add_asset('background.png', image(), True)
    monkeypatch.setattr(designer_render, 'generate_background', background)
    monkeypatch.setattr(designer_render, 'render', lambda owner, job: job['background'])
    result = designer_apply.automatic(store, draft, policy, version)
    assert result['cover_origin'] == 'designer' and result['asset_ids']
    assert designer_apply.automatic(store, result, policy, version) == result
    child = {**result, 'revision_root_id': draft['id'], 'title': '修改标题', 'id': 'revision-two'}
    store.put('content', child, child['id'])
    updated = designer_apply.automatic(store, child, policy, version)
    assert updated['designer_applied_title'] == '修改标题'
    assert len(calls) == 1
    content_revision.guard(store, policy, version, updated)


def test_old_candidate_is_visible_but_cannot_overwrite_newer_work_or_cross_profile(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path / 'first'))
    store = Store()
    draft = writing_drafts.create(store, {'request_id': 'original'})
    req = dict(kind='writing', origin_id=draft['id'], revision=1, version=0, mode='upload', request_id='preview')
    job, _ = designer_jobs.admit(store, req, False)
    asset = store.add_asset('photo.png', image(), True)
    with store.connection() as db:
        job.update(asset_id=asset, background=asset, state='completed')
        designer_jobs.save(db, job)
    data = writing_drafts.detail(store, draft['id'])
    writing_drafts.save(store, draft['id'], {**data, 'title': '新文案', 'request_id': 'edit', 'expected_revision': 1})
    assert designer_jobs.latest(store, 'writing', draft['id'])['asset_id'] == asset
    with pytest.raises(ValueError, match='已变化'):
        designer_apply.apply(store, job['id'], req)
    monkeypatch.setenv('HERMES_HOME', str(tmp_path / 'second'))
    with pytest.raises(ValueError, match='未找到'):
        designer_jobs.status(Store(), job['id'])


def test_reopened_store_reconciles_dead_owner_without_resubmitting(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    draft = writing_drafts.create(store, {'request_id': 'original'})
    req = dict(kind='writing', origin_id=draft['id'], revision=1, version=0, mode='ai', title='短标题', request_id='lost')
    job, _ = designer_jobs.admit(store, req, False)
    with store.connection() as db:
        job.update(state='running', charged=True, process_started=0)
        designer_jobs.save(db, job)
    again = Store()
    result = designer_jobs.start(again, req)
    assert result['state'] == 'unknown' and result['charged']
    with again.connection() as db:
        assert designer_jobs.read(db, job['id'])['state'] == 'unknown'
