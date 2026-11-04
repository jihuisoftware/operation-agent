"""Explicit topic generation uses the ordinary execution lease and model budget."""
import logging
import re

from .policy import local_day, now_iso
from .store import encoded


def existing(store, identity, body):
    from .collection_ledger import load
    record = load(store, identity)
    if record and record['request'] != body:
        raise ValueError('同一请求标识不能用于不同规则或生成方式')
    return record


def run(store, body):
    if set(body) != {'version', 'request_id', 'force'} or type(body['force']) is not bool or type(body['version']) is not int or not isinstance(body['request_id'], str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', body['request_id']):
        raise ValueError('选题请求字段无效')
    identity = 'topic-generation:' + body['request_id']
    saved = existing(store, identity, body)
    if saved:
        return saved
    version, policy = store.policy()
    if body['version'] != version or not policy['modules']['topics'] or not policy['enabled'] or policy['paused']:
        raise ValueError('请启用选题模块并刷新当前规则')
    if not store.lease(identity):
        raise ValueError('已有任务执行中，本次选题未启动')
    try:
        saved = existing(store, identity, body)
        if saved:
            return saved
        return _execute(store, identity, body, policy, version)
    finally:
        store.release(identity)


def _execute(store, identity, body, policy, version):
    from .outcomes import StageSkipped, describe
    from .topics import generate_topics
    from .execution_pause import ExecutionPaused
    day = local_day(policy)
    run_id = store.start_run(day, 'topics', identity, version)
    record = {'request': body, 'run_id': run_id, 'state': 'running', 'started': now_iso(), 'detail': '正在生成选题'}
    if store.scope:
        record.update(business_id=store.scope['business_id'], topic_id=store.scope['id'])
    store.put('topic_generation', record, identity)
    try:
        result = generate_topics(store, policy, day, version, force=body['force'])
        state, detail = describe('topics', result)
    except StageSkipped as exc:
        state, detail = 'skipped', str(exc)
    except ExecutionPaused as exc:
        state, detail = 'paused', str(exc)
    except Exception as exc:
        logging.getLogger(__name__).exception('Topic generation failed: %s', identity)
        state, detail = 'failed', str(exc)
        store.event('topic_generation_error', {'error': detail})
    store.finish_run(run_id, state, detail)
    record.update(state=state, detail=detail, ended=now_iso())
    with store.connection() as db:
        db.execute("UPDATE objects SET data=? WHERE id=? AND kind='topic_generation'", (encoded(record), identity))
    return record
