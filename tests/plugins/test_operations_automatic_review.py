"""Automatic approval is revision-scoped and never processes historical/manual/debug drafts implicitly."""
from copy import deepcopy
from datetime import datetime, UTC, timedelta
import json

import pytest
from plugins.operations import review_policy, review_scores, automatic_review, automatic_schedule, content_release
from plugins.operations.store import encoded
from plugins.operations.content import check_content as check_actual_content
from tests.plugins.test_operations_content_review import manuscript as _manuscript, desktop


@pytest.fixture(name='manuscript')
def prepared_manuscript(tmp_path, monkeypatch):
    return _manuscript.__wrapped__(tmp_path, monkeypatch)


def replace_draft(store, draft):
    with store.connection() as db:
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(draft), draft['id']))


def configure(store, mode='score', threshold=85):
    return review_policy.update(store, {'mode': mode, 'threshold': threshold, 'expected_revision': review_policy.get(store)['revision']})


def good(kind, number=85):
    weights = review_scores.TEXT if kind == 'text' else review_scores.VISUAL
    return {'pass': True, 'issues': [], 'scores': dict.fromkeys(weights, number)}


@pytest.mark.parametrize('text,visual,expected', [(85,85,True),(84,100,False),(100,84,False),(None,100,False)])
def test_scores_are_bounded_and_neither_side_can_mask_the_other(text, visual, expected):
    approved, _, _ = review_scores.decide({'mode':'score','threshold':85}, good('text',text), good('visual',visual))
    assert approved is expected
    assert review_scores.decide({'mode':'automatic'}, {'pass':False}, good('visual'))[0] is False
    assert review_scores.score(good('text', float('nan')), 'text') is None


def test_policy_cas_preserves_operating_rules_and_old_drafts(manuscript):
    store, _, _, draft = manuscript
    before = store.policy()
    assert review_policy.get(store)['mode'] == 'manual'
    settings = configure(store)
    assert store.policy() == before
    with pytest.raises(ValueError, match='策略已变化'):
        review_policy.update(store, {'mode':'manual','threshold':85,'expected_revision':0})
    automatic_review.after_production(store, {'content_id':draft['id']})
    with store.connection() as db:
        assert content_release.load(db,draft['id']) is None
    assert settings['revision'] == 1


def test_explicit_recheck_schedules_once_and_cancellation_cannot_rearm(manuscript, monkeypatch):
    store, _, _, draft = manuscript
    configure(store)
    monkeypatch.setattr('plugins.operations.content.check_content', lambda *a: good('text'))
    monkeypatch.setattr('plugins.operations.visual_review.for_content', lambda *a: good('visual'))
    body={'request_id':'one','content_revision':content_release.fingerprint(draft)}
    result=automatic_review.recheck(store,draft['id'],body)
    assert result['decision']['approved']
    assert result['release']['reviewer']=='automatic'
    assert datetime.fromisoformat(result['release']['publish_at']) > datetime.now(UTC)
    assert automatic_review.recheck(store,draft['id'],body)==result
    content_release.cancel(store,draft['id'],result['release']['revision'])
    automatic_schedule.schedule_pending(store,datetime.now(UTC))
    with store.connection() as db:
        assert content_release.load(db,draft['id'])['state']=='cancelled'


def test_policy_change_revokes_automatic_not_human_and_keeps_legacy_authorization(manuscript, monkeypatch):
    store, policy, _, draft=manuscript
    settings=configure(store, 'automatic')
    monkeypatch.setattr('plugins.operations.visual_review.for_content',lambda *a:good('visual'))
    draft.update(review_policy_revision=settings['revision'])
    replace_draft(store,draft)
    automatic_review.after_production(store,{'content_id':draft['id']})
    with store.connection() as db:
        release=content_release.load(db,draft['id'])
    assert release['reviewer']=='automatic'
    store.execution_now=datetime.fromisoformat(release['publish_at'])+timedelta(seconds=1)
    action={'kind':'publish','content':content_release.manuscript(store,draft['id']),'account_id':'me','release_revision':release['revision']}
    with store.connection() as db:
        assert content_release.authorization(store,db,action,1,policy)
    configure(store,'manual')
    with store.connection() as db:
        assert content_release.load(db,draft['id'])['state']=='cancelled'
        assert not content_release.authorization(store,db,action,1,policy)
    due=datetime.now(UTC)+timedelta(minutes=10)
    human=content_release.review(store,draft['id'],{'expected_revision':release['revision']+1,'version':1,
      'content_revision':content_release.fingerprint(draft),'publish_at':due.isoformat()})
    configure(store,'score',90)
    action.pop('release_revision');action['human_review']=human['revision'];store.execution_now=due+timedelta(seconds=1)
    with store.connection() as db:
        assert content_release.authorization(store,db,action,1,policy)


def test_debug_and_manual_drafts_never_implicitly_schedule(manuscript, monkeypatch):
    store, _, _, draft=manuscript
    cfg=configure(store,'automatic')
    monkeypatch.setattr('plugins.operations.visual_review.for_content',lambda *a:pytest.fail('must not call visual model'))
    draft.update(review_policy_revision=cfg['revision'],manual=True);replace_draft(store,draft)
    automatic_review.after_production(store,{'content_id':draft['id']})
    draft['manual']=False;replace_draft(store,draft);store.debug_id='debug:only-content'
    automatic_review.after_production(store,{'content_id':draft['id']})
    with store.connection() as db:
        assert content_release.load(db,draft['id']) is None


def test_score_failure_retains_text_and_returns_to_manual(manuscript, monkeypatch):
    store, _, _, draft=manuscript
    cfg=configure(store)
    monkeypatch.setattr('plugins.operations.visual_review.for_content',lambda *a:good('visual',100))
    decision=automatic_review.evaluate(store,draft,cfg)
    assert not decision['approved'] and '评分缺失' in decision['reason']
    assert content_release.manuscript(store,draft['id'])['body']==draft['body']


def test_due_automatic_release_uses_real_pipeline_without_human_flag(manuscript, monkeypatch):
    store, _policy, _, draft=manuscript
    configure(store,'automatic')
    monkeypatch.setattr('plugins.operations.visual_review.for_content',lambda *a:good('visual'))
    result=automatic_review.recheck(store,draft['id'],{'request_id':'due','content_revision':content_release.fingerprint(draft)})
    seen=desktop(store,monkeypatch)
    from plugins.operations.publication_plan import publish_due
    due=datetime.fromisoformat(result['release']['publish_at'])+timedelta(seconds=1)
    store.execution_now=due
    monkeypatch.setattr('plugins.operations.execution_preflight.verify_for_start',lambda *a:None)
    assert publish_due(store,due)
    assert len(seen)==1 and 'release_revision' in seen[0]['payload'] and 'human_review' not in seen[0]['payload']
    assert not publish_due(store,due)
    with pytest.raises(ValueError, match='发布动作'):
        automatic_review.require_manual(store,draft['id'],{'content_revision':content_release.fingerprint(draft)})


def test_manual_intervention_wins_over_late_model_result(manuscript, monkeypatch):
    store, _, _, draft = manuscript
    cfg = configure(store, 'automatic')
    def image_review(*args):
        automatic_review.require_manual(store,draft['id'],{'content_revision':content_release.fingerprint(draft)})
        return good('visual')
    monkeypatch.setattr('plugins.operations.visual_review.for_content',image_review)
    with pytest.raises(ValueError, match='检查期间'):
        automatic_review.evaluate(store,draft,cfg)
    with store.connection() as db:
        assert content_release.load(db,draft['id']) is None


def test_next_slot_respects_timezone_existing_booking_and_capacity(manuscript):
    store, policy, _, draft = manuscript
    policy = deepcopy(policy)
    policy['timezone']='Asia/Shanghai'
    policy['times']['publish']=['09:00','18:00']
    now=datetime(2026,1,1,0,30,tzinfo=UTC)
    assert automatic_schedule.next_slot(store,policy,now)=='2026-01-01T01:00:00+00:00'
    with store.connection() as db:
        booked={'content_id':draft['id'],'state':'scheduled','publish_at':'2026-01-01T01:00:00+00:00'}
        db.execute("INSERT INTO objects VALUES (?,'content_release',?,?)",('content-release:'+draft['id'],encoded(booked),now.isoformat()))
    assert automatic_schedule.next_slot(store,policy,now)=='2026-01-02T01:00:00+00:00'
    policy['times']['publish']=[]
    assert automatic_schedule.next_slot(store,policy,now) is None


def test_production_failure_retains_a_manual_review_decision(manuscript, monkeypatch):
    store, policy, day, draft=manuscript
    cfg=configure(store,'automatic')
    draft.update(review_policy_revision=cfg['revision'],quality={'pass':False})
    replace_draft(store,draft)
    from plugins.operations.model_errors import ModelServiceUnavailable
    def fail(*args): raise ModelServiceUnavailable('模型超时')
    monkeypatch.setattr('plugins.operations.content_recovery.review',fail)
    result=automatic_review.finish_production(store,policy,day,1,draft,[])
    assert result['ready'] is False and '模型超时' in result['reason']
    assert not result['automatic_review']['approved']
    assert content_release.manuscript(store,draft['id'])['body']==draft['body']


def test_threshold_change_invalidates_waiting_decision_without_calling_model(manuscript, monkeypatch):
    store, _, _, draft = manuscript
    cfg = configure(store, 'automatic')
    monkeypatch.setattr('plugins.operations.visual_review.for_content', lambda *a:good('visual'))
    decision = automatic_review.evaluate(store, draft, cfg)
    assert decision['approved']
    configure(store, 'score', 90)
    current = content_release.manuscript(store, draft['id'])
    assert current['automatic_review']['approved'] is False
    with store.connection() as db:
        assert not automatic_review.decision_current(db, current, decision)


def test_auto_authorization_rejects_edits_and_changed_operating_rules(manuscript, monkeypatch):
    store, policy, _, draft = manuscript
    cfg = configure(store, 'automatic')
    monkeypatch.setattr('plugins.operations.visual_review.for_content', lambda *a:good('visual'))
    decision = automatic_review.evaluate(store,draft,cfg)
    with store.connection() as db:
        current = content_release.manuscript(store,draft['id'])
        assert automatic_review.decision_current(db,current,decision)
        assert not automatic_review.decision_current(db,{**current,'body':'changed'},decision)
    store.configure({**policy,'style':'新要求'},1)
    assert automatic_schedule.schedule_one(store,draft['id']) is None


def test_real_new_ai_production_records_policy_and_auto_schedules(manuscript, monkeypatch):
    store, policy, day, _draft=manuscript
    cfg=configure(store,'automatic')
    # Isolated fixture clears its first manual draft so the production path creates a new manuscript.
    with store.connection() as db:
        db.execute("DELETE FROM objects WHERE kind='content'")
    monkeypatch.setattr('plugins.operations.visual_review.for_content',lambda *a:good('visual'))
    from plugins.operations.content import produce_content
    result=produce_content(store,policy,day,1)
    current=content_release.manuscript(store,result['content_id'])
    assert current['review_policy_revision']==cfg['revision']
    assert result['automatic_review']['approved']
    with store.connection() as db:
        assert content_release.load(db,result['content_id'])['reviewer']=='automatic'


def test_new_quality_failure_cannot_reuse_an_old_pass_for_auto_release(manuscript, monkeypatch):
    store, policy, day, draft=manuscript
    cfg=configure(store,'automatic')
    draft.update(review_policy_revision=cfg['revision'])
    replace_draft(store,draft)
    def fail(*a): raise ValueError('达到每日或本轮模型调用额度')
    monkeypatch.setattr('plugins.operations.content_recovery.review',fail)
    monkeypatch.setattr('plugins.operations.visual_review.for_content',lambda *a:pytest.fail('no model call after budget failure'))
    result=automatic_review.finish_production(store,policy,day,1,draft,[])
    assert not result['automatic_review']['approved']
    with store.connection() as db:
        assert content_release.load(db,draft['id']) is None


def test_readonly_verification_survives_expired_release_authorization(tmp_path):
    from tests.plugins.test_operations_publication_evidence import prepared
    from plugins.operations.browser_evidence import record_step
    from plugins.operations.review_queue import request_check
    store, identity, command = prepared(tmp_path / 'verify.db')
    with store.connection() as db:
        payload = json.loads(db.execute('SELECT data FROM actions WHERE id=?',(identity,)).fetchone()[0])
        payload['content']['id']='old-content'
        payload['release_revision']=1
        db.execute('UPDATE actions SET data=? WHERE id=?',(encoded(payload),identity))
    store.acknowledge(command['id'],'desktop',{'state':'submitted','evidence':'已提交'})
    request_check(store,identity)
    verifying=store.claim('desktop')
    assert verifying['kind']=='verify'
    record_step(store,verifying['id'],'desktop',{'sequence':1,'phase':'started','name':'account'})
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM actions WHERE kind='publish'").fetchone()[0]==1


def test_nonexistent_dst_slot_is_skipped(manuscript):
    store, policy, _, _draft=manuscript
    policy=deepcopy(policy)
    policy.update(timezone='America/New_York')
    policy['times']['publish']=['02:30']
    slot=automatic_schedule.next_slot(store,policy,datetime(2026,3,8,6,0,tzinfo=UTC))
    assert slot=='2026-03-09T06:30:00+00:00'


def test_visual_scores_reuse_same_input_but_not_changed_text(manuscript, monkeypatch):
    from plugins.operations import visual_review
    store, _, _, draft=manuscript
    configure(store,'score')
    calls=[]
    monkeypatch.setattr(visual_review,'inspect',lambda *a: calls.append(1) or good('visual'))
    visual_review.for_content(store,draft)
    configure(store,'score',90)
    visual_review.for_content(store,draft)
    assert calls==[1]
    visual_review.for_content(store,{**draft,'body':'变更后的内容'})
    assert calls==[1,1]


def test_existing_magazine_visual_review_is_reused_without_extra_model_call(manuscript, monkeypatch):
    from plugins.operations import visual_review, visual_plan
    store, _, _, draft=manuscript
    configure(store,'score')
    draft={**draft,'visual_set_id':'visual-test'}
    store.put('visual_set',{'state':'completed','policy_version':1,'input_signature':visual_plan.signature(draft),
      'pages':[{'asset_id':i} for i in draft['asset_ids']], 'review':good('visual')},'visual-test')
    monkeypatch.setattr(visual_review,'inspect',lambda *a:pytest.fail('duplicate visual check'))
    assert visual_review.for_content(store,draft)==good('visual')


def test_threshold_only_change_reuses_text_check_without_model_call(manuscript, monkeypatch):
    store, policy, day, draft = manuscript
    configure(store, 'score')
    calls=[]
    monkeypatch.setattr('plugins.operations.content.generate',lambda *a, **kw:calls.append(1) or good('text'))
    first=check_actual_content(store,policy,day,1,draft,store.objects('source'))
    configure(store,'score',90)
    second=check_actual_content(store,policy,day,1,draft,store.objects('source'))
    assert first==second and calls==[1]
