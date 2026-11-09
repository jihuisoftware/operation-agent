"""Private, scoped background jobs and explicit application of a completed visual set."""
from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import re

from . import visual_sets, visual_plan, visual_job_state
from .store import encoded

_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='operations-visual')


def origin_content(store, origin):
    from .content_release import manuscript
    from .industry import check_public_context
    from .policy import local_day
    _, policy = store.policy()
    if origin['kind'] == 'content':
        content = manuscript(store, origin['id'])
        check_public_context(store, content, policy, content.get('day', local_day(policy)))
        return content
    if origin['kind'] != 'writing':
        raise ValueError('组图归属类型无效')
    from .writing_drafts import read
    from .writing_submission import candidate
    with store.connection() as db:
        draft = read(db, origin['id'])
    if draft.get('archived'):
        raise ValueError('草稿已归档')
    content, projection = candidate(draft)
    if projection['pending_images']:
        raise ValueError('请先处理上传失败或尚未导入的图片')
    if draft['origin'].get('content_id'):
        parent = manuscript(store, draft['origin']['content_id'])
        check_public_context(store, parent, policy, parent.get('day', local_day(policy)))
    content['editor_document'] = draft['document']
    return content


def execute(store, identity, token):
    store.visual_worker = (identity, token)
    try:
        with store.connection() as db:
            if not visual_job_state.owned(db, store, identity):
                return visual_sets.read(store, identity)
        content = origin_content(store, visual_sets.read(store, identity)['origin'])
        return visual_sets.run(store, identity, content)
    except Exception as exc:
        logging.getLogger(__name__).exception('Visual production interrupted')
        record = visual_sets.read(store, identity)
        record.update(state='needs_attention', detail=str(exc))
        visual_sets.save(store, record)
        return record
    finally:
        with store.connection() as db:
            db.execute('DELETE FROM leases WHERE id=? AND token=?', (identity, token))
        store.visual_worker = None


def start(store, body):
    request = body.get('request_id', '')
    if not isinstance(request, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', request):
        raise ValueError('组图请求标识无效')
    replay = visual_job_state.receipt(store, body)
    if replay:
        return public(visual_job_state.status(store, replay))
    if type(body.get('retry', False)) is not bool:
        raise ValueError('重试参数必须为布尔值')
    origin = {'kind': body.get('kind'), 'id': body.get('id')}
    content = origin_content(store, origin)
    if origin['kind'] == 'writing':
        from .writing_drafts import read, check_revision
        with store.connection() as db:
            check_revision(read(db, origin['id']), body)
    else:
        from .content_release import fingerprint
        if body.get('content_revision') != fingerprint(content):
            raise ValueError('稿件版本已变化，请刷新')
    record = visual_sets.create(store, content, origin)
    visual_job_state.receipt(store, body, record['id'])
    if record['state'] == 'completed' and not body.get('retry'):
        return public(record)
    if record['state'] not in {'queued', 'running'} and not body.get('retry'):
        return public(record)
    token = visual_job_state.claim(store, record['id'])
    if not token:
        return public(record)
    record = visual_sets.read(store, record['id'])
    if body.get('regenerate_art') is not None:
        index = body['regenerate_art']
        if type(index) is not int or not record['plan'] or not 0 <= index < len(record['plan']['pages']) or not record['plan']['pages'][index]['art']:
            with store.connection() as db:
                db.execute('DELETE FROM leases WHERE id=? AND token=?', (record['id'], token))
            raise ValueError('此页没有可重做的 AI 主视觉')
        key = str(index)
        record['previous'] = {key: record.get(key) for key in ('pages', 'art', 'art_revision', 'review')}
        record['art'] = dict(record['art'])
        record['art_revision'] = dict(record.get('art_revision', {}))
        record['art'].pop(key, None)
        record.setdefault('art_revision', {})[key] = record.get('art_revision', {}).get(key, 0) + 1
        record.update(pages=[], review=None)
    record.update(cancelled=False, state='queued', detail='等待组图设计；已完成页面会复用')
    visual_sets.save(store, record, resume=True)
    store.visual_manual = True
    scoped = copy_context()
    # Every background callback keeps the request's Profile/secret/workspace context.
    _POOL.submit(scoped.run, execute, store, record['id'], token)
    return public(record)


def public(record):
    return {key: record.get(key) for key in ('id', 'origin', 'state', 'detail', 'pages', 'attempts', 'updated', 'visual_review', 'review', 'previous', 'selection')}


def latest(store, kind, identity):
    origin_content(store, {'kind': kind, 'id': identity})
    rows = [row for row in store.objects('visual_set') if row['origin'] == {'kind': kind, 'id': identity}]
    return {'item': public(visual_job_state.status(store, max(rows, key=lambda row: row.get('updated', row['created']))['id'])) if rows else None}


def cancel(store, identity):
    record = visual_sets.read(store, identity)
    record.update(cancelled=True, state='cancelled', detail='已请求取消；已派发生图可能仍产生费用，已完成图片保留')
    visual_sets.save(store, record)
    return public(record)


def apply(store, identity, body):
    record = visual_sets.read(store, identity)
    content = origin_content(store, record['origin'])
    if record['state'] != 'completed' or record['input_signature'] != visual_plan.signature(content):
        raise ValueError('组图尚未完成或稿件已变化，请重新生成')
    ids = [page['asset_id'] for page in record['pages']]
    for asset_id in ids:
        visual_sets.asset_bytes(store, asset_id)
    if record['origin']['kind'] == 'writing':
        from .writing_drafts import read, check_revision
        with store.connection() as db:
            draft = read(db, record['origin']['id'])
            check_revision(draft, body)
        return {'asset_ids': ids, 'expected_revision': draft['revision']}
    from .content_versions import create
    return create(store, record['origin']['id'], {**body, 'asset_ids': ids})


def automatic(store, content):
    record = visual_sets.create(store, content, {'kind': 'content', 'id': content['id']})
    if record['state'] == 'running' or (record['state'] == 'queued' and record.get('worker_session')):
        record = visual_job_state.status(store, record['id'])
    if record['state'] == 'queued':
        token = visual_job_state.claim(store, record['id'])
        if token:
            record = execute(store, record['id'], token)
    if record['state'] != 'completed':
        return {**content, 'visual_set_id': record['id'], 'visual_error': record['detail'], 'ready': False}
    ids = [page['asset_id'] for page in record['pages']]
    for identity in ids:
        visual_sets.asset_bytes(store, identity)
    return {**content, 'asset_ids': ids, 'visual_set_id': record['id'], 'visual_plan': record['plan'], 'visual_error': '', 'visual_review': record.get('review')}


def restore(store, identity):
    record = visual_job_state.status(store, identity)
    with store.connection() as db:
        lease = db.execute('SELECT expires FROM leases WHERE id=?', (identity,)).fetchone()
    import time
    active = lease and lease['expires'] > time.time() and record.get('worker_session') == visual_job_state.SESSION
    if active or record['state'] in {'running', 'queued'} or not record.get('previous'):
        raise ValueError('请等待生成结束，或没有可恢复的上一套组图')
    if visual_plan.signature(origin_content(store, record['origin'])) != record['input_signature']:
        raise ValueError('稿件已变化，不能应用旧组图')
    for page in record['previous']['pages']:
        visual_sets.asset_bytes(store, page['asset_id'])
    record.update(record.pop('previous'))
    record.update(state='completed', cancelled=False, detail='已恢复上一套组图；调用次数与费用记录保留')
    visual_sets.save(store, record, resume=True)
    return public(record)
