"""One authenticated request produces a complete manuscript for human review."""
import re
import logging

from .outcomes import StageSkipped
from .policy import local_day, now_iso
from .store import encoded


def generate(store, body):
    from .collection_ledger import load
    request = body.get('request_id', '')
    if not isinstance(request, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', request):
        raise ValueError('生成请求标识无效')
    identity = 'content-generation:' + request
    previous = load(store, identity)
    if previous:
        if previous['version'] != body.get('version'):
            raise ValueError('同一请求不能更换规则版本')
        return previous
    version, policy = store.policy()
    if version != body.get('version') or not policy['enabled'] or policy['paused'] or not policy['modules']['content']:
        raise ValueError('请启用内容生产并刷新当前配置')
    if not store.lease(identity):
        raise ValueError('已有任务执行中，请等待结束')
    try:
        previous = load(store, identity)
        if previous:
            return previous
        return _generate(store, identity, version, policy)
    finally:
        store.release(identity)


def _generate(store, identity, version, policy):
    from .topics import production_topic, generate_topics
    from .content import produce_content
    from .outcomes import describe
    day = local_day(policy)
    run = store.start_run(day, 'content', identity, version)
    record = {'state': 'running', 'version': version, 'run_id': run, 'started': now_iso()}
    if store.scope:
        record.update(business_id=store.scope['business_id'], topic_id=store.scope['id'])
    store.put('content_generation', record, identity)
    try:
        try:
            topic = production_topic(store, policy, day)
        except StageSkipped:
            topic = None
        if topic is None:
            generate_topics(store, policy, day, version)
        result = produce_content(store, policy, day, version)
        state, detail = describe('content', result)
        record['result'] = result
    except Exception as exc:
        logging.getLogger(__name__).exception('Content generation failed: %s', identity)
        from .execution_pause import ExecutionPaused
        state = 'paused' if isinstance(exc, ExecutionPaused) else 'failed'
        detail = str(exc)
        store.event('content_generation_error', {'error': detail})
    store.finish_run(run, state, detail)
    record.update(state=state, detail=detail, ended=now_iso())
    with store.connection() as db:
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(record), identity))
    return record
