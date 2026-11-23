"""Bounded review decisions for new AI manuscripts, with durable idempotent scheduling."""
import json
from .store import encoded
from .policy import now_iso
from .content_release import fingerprint, manuscript
from .review_policy import get, read
from .review_scores import decide, VERSION


def decision_current(db, content, decision):
    settings = read(db)
    return (decision.get('approved') is True and decision.get('policy_revision') == settings['revision']
            and decision.get('operating_version') == db.execute('SELECT version FROM settings WHERE id=1').fetchone()[0]
            and settings['mode'] != 'manual' and decision.get('rubric') == VERSION
            and decision.get('content_revision') == fingerprint(content)
            and decision.get('control_revision', 0) == content.get('review_control_revision', 0)
            and content.get('automatic_review') == decision and not content.get('manual'))


def authorize_decision(db, content, decision):
    if not decision_current(db, content, decision):
        raise ValueError('自动审核依据或策略已失效，请重新检查')


def after_production(store, result):
    if getattr(store, 'debug_id', None) or not result.get('content_id'):
        return result
    draft = manuscript(store, result['content_id'])
    settings = get(store)
    if settings['mode'] == 'manual' or draft.get('review_policy_revision') != settings['revision'] or draft.get('manual'):
        return result
    decision = evaluate(store, draft, settings)
    from .automatic_schedule import schedule_one
    schedule_one(store, draft['id'])
    return {**result, 'automatic_review': decision}


def evaluate(store, draft, settings, *, recheck=False, failure=None):
    from .content import check_content
    from .content_release import validate
    from .visual_review import for_content
    from .model_errors import ModelOutputError, ModelServiceUnavailable
    version, policy = store.policy()
    signature = fingerprint(draft)
    old = draft.get('automatic_review') or {}
    if not recheck and old.get('content_revision') == signature and old.get('policy_revision') == settings['revision']:
        return old
    text, visual = draft.get('quality') or {}, {}
    account_id, account_scope = '', ''
    try:
        if failure:
            raise ValueError(failure)
        if draft.get('visual_required') and draft.get('visual_error'):
            raise ValueError('杂志组图尚未完成，请人工核对当前封面')
        if draft.get('manual'):
            raise ValueError('手写稿件仍需人工审核')
        if draft.get('version') != version and not recheck:
            raise ValueError('运营规则已变化，请按当前规则重新生成或人工审核')
        validate(store, draft)
        if recheck:
            text = check_content(store, policy, draft['day'], version, draft, store.objects('source'))
        if text.get('pass') is True:
            visual = for_content(store, draft)
        approved, reason, scores = decide(settings, text, visual)
        if approved:
            from .content_release import account
            account_id, account_scope = account(store, policy)
    except (ValueError, ModelOutputError, ModelServiceUnavailable, TimeoutError, ConnectionError) as exc:
        approved, reason, scores = False, '检查不可用，等待人工审核：' + str(exc), {'text': None, 'visual': None}
    value = {'approved': approved, 'reason': reason, 'scores': scores, 'mode': settings['mode'],
             'account_id': account_id, 'account_scope': account_scope, 'operating_version': version,
             'threshold': settings['threshold'], 'policy_revision': settings['revision'], 'rubric': VERSION,
             'content_revision': signature, 'control_revision': draft.get('review_control_revision', 0), 'checked_at': now_iso()}
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        current = json.loads(db.execute("SELECT data FROM objects WHERE kind='content' AND id=?", (draft['id'],)).fetchone()[0])
        if current.get('review_control_revision', 0) != draft.get('review_control_revision', 0) or fingerprint(current) != signature or read(db)['revision'] != settings['revision'] or db.execute('SELECT version FROM settings WHERE id=1').fetchone()[0] != version:
            raise ValueError('检查期间稿件或规则变化，结果未应用')
        from .content_release import load
        release = load(db, draft['id'])
        if release and release['state'] != 'cancelled':
            return current.get('automatic_review', value)
        current.update(automatic_review=value, quality=text, review_policy_revision=settings['revision'])
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(current), draft['id']))
    store.event('automatic_content_review', {'content_id': draft['id'], **value})
    return value


def recheck(store, identity, body):
    import re
    request = body.get('request_id', '')
    if not isinstance(request, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', request):
        raise ValueError('复检请求标识无效')
    key = 'review-request:' + request
    with store.connection() as db:
        saved = db.execute('SELECT data FROM objects WHERE id=?', (key,)).fetchone()
        if saved:
            saved = json.loads(saved[0])
            if saved['content_id'] != identity or saved['input_revision'] != body.get('content_revision'):
                raise ValueError('同一复检请求不能更换稿件')
            return saved
    token = 'review:' + request
    if not store.lease(token):
        raise ValueError('已有任务执行中，请稍后复检')
    try:
        draft = manuscript(store, identity)
        if fingerprint(draft) != body.get('content_revision'):
            raise ValueError('稿件已修改，请刷新')
        with store.connection() as db:
            from .content_release import load
            release = load(db, identity)
            if release and release['state'] != 'cancelled':
                raise ValueError('稿件已有审核排期，请先取消或转人工')
            if db.execute("SELECT 1 FROM actions WHERE kind='publish' AND json_extract(data,'$.content.id')=?", (identity,)).fetchone():
                raise ValueError('稿件已有发布动作，请核对原记录')
        result = evaluate(store, draft, get(store), recheck=True)
        from .automatic_schedule import schedule_one
        release = schedule_one(store, identity)
        value = {'content_id': identity, 'input_revision': body['content_revision'], 'decision': result, 'release': release}
        store.put('review_request', value, key)
        with store.connection() as db:
            return json.loads(db.execute('SELECT data FROM objects WHERE id=?', (key,)).fetchone()[0])
    finally:
        store.release(token)


def finish_production(store, policy, day, version, draft, sources):
    from .content_recovery import review
    from .model_errors import ModelServiceUnavailable
    try:
        result = review(store, policy, day, version, draft, sources)
    except (ValueError, ModelServiceUnavailable, TimeoutError, ConnectionError) as exc:
        settings = get(store)
        if settings['mode'] == 'manual' or getattr(store, 'debug_id', None):
            raise
        current = manuscript(store, draft['id'])
        decision = evaluate(store, current, settings, failure=str(exc))
        return {'content_id': draft['id'], 'ready': False, 'missing': ['自动检查不可用'], 'reason': str(exc), 'automatic_review': decision}
    return after_production(store, result)


def require_manual(store, identity, body):
    from .content_release import load, cancel
    current = manuscript(store, identity)
    if fingerprint(current) != body.get('content_revision'):
        raise ValueError('稿件已变化，请刷新')
    with store.connection() as db:
        if db.execute("SELECT 1 FROM actions WHERE kind='publish' AND json_extract(data,'$.content.id')=? AND state IN ('queued','executing','submitted','unknown','published','confirmed')", (identity,)).fetchone():
            raise ValueError('已有发布动作，请在执行记录中核对或取消，不能撤销提交事实')
        release = load(db, identity)
    if release and release['state'] == 'scheduled':
        cancel(store, identity, body.get('expected_revision'))
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        saved = json.loads(db.execute('SELECT data FROM objects WHERE id=?', (identity,)).fetchone()[0])
        if fingerprint(saved) != body['content_revision']:
            raise ValueError('稿件已变化，请刷新')
        from .review_policy import hold_manuscript
        hold_manuscript(db, identity, '已转人工审核，不再自动排期')
    store.event('content_review_manual', {'content_id': identity})
    return {'state': 'manual'}
