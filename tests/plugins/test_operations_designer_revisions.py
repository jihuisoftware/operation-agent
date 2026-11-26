"""Each reviewed candidate belongs to one revision. Failed rounds never authorize release."""
import pytest

from plugins.operations import content_release, designer_apply, designer_jobs, designer_workflow
from plugins.operations.store import Store, encoded
from tests.plugins.operations_support import install_test_designer


@pytest.fixture
def setup_design(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    install_test_designer(monkeypatch)
    store = Store()
    draft = {'title': '案例', 'body': '案例正文', 'source_ids': [], 'asset_ids': [],
             'authorship': {'kind': 'human_original', 'declared': True, 'draft_id': 'writer'}}
    identity = store.put('content', draft)
    body = {'kind': 'content', 'origin_id': identity, 'revision': content_release.fingerprint(draft),
            'version': 0, 'request_id': 'make', 'mode': 'ai', 'title': draft['title']}
    return store, draft, body


def test_failed_rounds_stop_after_two_revisions_and_can_be_selected_manually(setup_design, monkeypatch):
    store, draft, body = setup_design
    reviews = []
    def model_step(owner, job, phase, brief, image=None):
        if phase == 'review':
            reason = '版式问题 ' + str(len(reviews))
            reviews.append(reason)
            return {'review': {'pass': False, 'reason': reason, 'issues': [reason]}}
        if reviews:
            assert brief['review']['reason'] == reviews[-1]
        return {'design': {'template': 'editorial', 'title': draft['title'] + str(len(reviews))},
                'panel': 'bottom', 'reason': '调整版式', 'background_prompt': ''}
    monkeypatch.setattr(designer_workflow, 'model_step', model_step)
    job = designer_jobs.start(store, body, synchronous=True)
    assert job['state'] == 'failed' and len(job['rounds']) == len(reviews) == 3
    assert designer_jobs.start(store, body, synchronous=True)['id'] == job['id'] and len(reviews) == 3
    assert not store.objects('content')[0]['asset_ids'] and not store.objects('content_release')
    choice = job['rounds'][0]['asset_id']
    with pytest.raises(ValueError, match='轮次'):
        designer_apply.apply(store, job['id'], {**body, 'candidate_asset': 'foreign'})
    result = designer_apply.apply(store, job['id'], {**body, 'candidate_asset': choice})
    assert result['id'] == body['origin_id']
    assert store.objects('content')[0]['asset_ids'] == [choice] and not store.objects('content_release')


def test_edit_during_review_retains_candidate_and_rejects_old_application(setup_design, monkeypatch):
    store, draft, body = setup_design
    original = designer_workflow.model_step
    def edit_during_review(owner, job, phase, brief, image=None):
        result = original(owner, job, phase, brief, image)
        if phase == 'review':
            with store.connection() as db:
                db.execute('UPDATE objects SET data=? WHERE id=?', (encoded({**draft, 'body': '新正文'}), body['origin_id']))
        return result
    monkeypatch.setattr(designer_workflow, 'model_step', edit_during_review)
    job = designer_jobs.start(store, body, synchronous=True)
    assert job['state'] == 'failed' and len(job['rounds']) == 1
    with pytest.raises(ValueError, match='变化'):
        designer_apply.apply(store, job['id'], {**body, 'candidate_asset': job['rounds'][0]['asset_id']})
    assert store.objects('content')[0]['body'] == '新正文' and not store.objects('content')[0]['asset_ids']


def test_upgrade_preserves_unknown_paid_job_without_dispatching_again(setup_design):
    store, _, body = setup_design
    legacy, _ = designer_jobs.admit(store, {**body, 'request_id': body['origin_id']}, automatic=True)
    with store.connection() as db:
        legacy.update(charged=True, state='unknown')
        designer_jobs.save(db, legacy)
    with pytest.raises(ValueError, match='付费结果待核对'):
        designer_workflow.candidate(store, 'content', body['origin_id'], body['revision'], body['title'], automatic=True)
    assert [job['id'] for job in store.objects(designer_jobs.KIND)] == [legacy['id']]
