"""Bind plugin design decisions and revision-specific candidates to operations budgets."""
import hashlib
import logging
from types import SimpleNamespace

from . import designer_jobs as jobs, designer_render as engine
from .policy import local_day
from .store import encoded


def check_current(store, job):
    from .batch_cancellation import check
    from .workspace_execution import check_running
    check(store)
    if job['automatic']:
        check_running(store)
    with store.connection() as db:
        return jobs.current(db, job)


def model_step(store, job, phase, brief, image=None):
    from .model import reserve_call
    from .model_budget_ledger import settle
    policy = store.policy()[1]
    day = local_day(policy)
    budget = reserve_call(store, policy, day, manual=not job['automatic'])
    response = None
    try:
        with engine.exchange({'phase': phase, 'brief': brief}, image) as (_, result):
            response = SimpleNamespace(usage=result.get('usage'))
            return result
    finally:
        settle(store, budget, response, None, 0)


def design_cover(store, job):
    from .template_fallback import no_image_model
    from .visual_sets import asset_bytes
    from .writing_document import project
    draft = check_current(store, job)
    policy = store.policy()[1]
    body = project(draft['document'])['body'] if job['kind'] == 'writing' else draft['body']
    referenced = set(draft.get('asset_ids', []))
    if draft.get('cover_asset_id'):
        referenced.add(draft['cover_asset_id'])
    from .model_inputs import assets
    existing = assets([a for a in store.objects('asset') if a['id'] in referenced and a.get('authorized') and not a.get('revoked')]) if referenced else []
    brief = {'existing_images': existing[:18], **job['spec'], 'body': job.get('excerpt') or body[:6000], 'audience': policy.get('audience'), 'channel': '小红书',
             'has_background': bool(job.get('background')), 'image_model': not no_image_model() and not (job['automatic'] and policy.get('image_mode') == 'basic')}
    job['rounds'] = []
    for _ in range(3):
        check_current(store, job)
        choice = model_step(store, job, 'design', brief)
        job.update(design=choice['design'], panel=choice['panel'])
        check_current(store, job)
        prompt = choice.get('background_prompt')
        if job['mode'] == 'ai' and brief['image_model'] and prompt:
            jobs.reserve_dispatch(store, job)
            job['background'] = engine.generate_background(store, prompt)
            job['dispatch_pending'] = False
            with store.connection() as db:
                jobs.save(db, job)
        asset = engine.render(store, job)
        if any(r['asset_id'] == asset for r in job['rounds']):
            raise ValueError('候选封面没有变化，请人工核对上一轮意见')
        check_current(store, job)
        try:
            review = model_step(store, job, 'review', {'title': brief['title'], 'body': brief['body'][:1500]},
                                asset_bytes(store, asset))['review']
        except Exception as exc:
            logging.getLogger(__name__).exception('Cover candidate review failed for %s', job['id'])
            review = {'pass': None, 'reason': '视觉检查不可用：' + str(exc), 'issues': []}
        job['rounds'].append({'asset_id': asset, 'background': job.get('background'), 'design': job['design'], 'reason': choice['reason'], 'review': review})
        job['asset_id'] = asset
        with store.connection() as db:
            jobs.save(db, job)
        check_current(store, job)
        if review.get('pass') is True and not review.get('issues'):
            job['state'] = 'completed'
            return
        if review.get('pass') is None:
            raise ValueError(review['reason'])
        if len(job['rounds']) > 1 and review.get('issues') and review['issues'] == job['rounds'][-2]['review'].get('issues'):
            raise ValueError('修订后同一问题仍然存在，请查看两版候选')
        brief.update(previous=job['design'], review=review, has_background=bool(job.get('background')))
    raise ValueError('封面两轮修订后仍未通过，请查看评审详情')


def candidate(store, kind, identity, revision, title, *, automatic, purpose='', subtitle='', manuscript_body='', previous=None):
    version = store.policy()[0]
    key = hashlib.sha256(encoded([kind, identity, version, revision, title, purpose, manuscript_body]).encode()).hexdigest()
    engine.check_plugin()
    prior = prior_background(store, kind, identity, revision, previous, automatic)
    previous = prior['id'] if prior else None
    reuse = bool(prior and prior.get('background'))
    result = jobs.start(store, {'kind': kind, 'origin_id': identity, 'request_id': key, 'version': version,
                                'revision': revision, 'title': title, 'subtitle': subtitle, 'excerpt': manuscript_body[:6000], 'mode': 'reuse' if reuse else 'ai', 'previous': previous},
                        automatic=automatic, synchronous=True)
    if result['state'] != 'completed':
        raise ValueError(result.get('error') or '封面设计尚未完成')
    from .designer_apply import verified
    with store.connection() as db:
        verified(store, db, result)
    return result

def prior_background(store, kind, identity, revision, previous, automatic):
    with store.connection() as db:
        if previous:
            return jobs.read(db, previous)
        if not automatic or kind != 'content':
            return None
        legacy = 'designer-auto:' + identity
        if not db.execute("SELECT 1 FROM objects WHERE id=? AND kind=?", (legacy, jobs.KIND)).fetchone():
            return None
    job = jobs.status(store, legacy)
    if job['state'] in ('running', 'queued', 'unknown') or (job.get('charged') and not job.get('background')):
        raise ValueError('已有封面任务执行中或付费结果待核对，请先核对原任务')
    return job if job['revision'] == revision and job.get('background') else None
