"""Same-day exact-input topic reuse, independent of execution-batch idempotency."""
import hashlib

from .store import encoded


def fingerprint(day, version, instruction, data, analysis):
    lineage = {key: value for key, value in (analysis or {}).items() if key not in {'analytics_id', 'industry_id', 'generated_at'}}
    return hashlib.sha256(encoded({'day': day, 'version': version, 'instruction': instruction, 'input': data, 'analysis': lineage}).encode()).hexdigest()


def find(store, day, signature):
    return next((row for row in store.objects('brief', day) if row.get('result', {}).get('input_signature') == signature), None)


def reuse(store, row, day, signature):
    from .outcomes import StageSkipped
    if not row['result'].get('topics'):
        raise StageSkipped('资料已整理，但没有符合主题的选题；可补充来源或手动指定题目')
    from .research import save_brief
    sources = [source for source in store.objects('source') if source['id'] in row['source_ids']]
    result = {**row['result'], 'reused_from': row['id'], 'input_signature': signature}
    identity = save_brief(store, day, result, sources, scope_topic=row['scope_topic'], version=row['version'])
    store.event('topics_reused', {'day': day, 'brief_id': identity, 'reused_from': row['id'], 'source_ids': row['source_ids']})
    return f"复用已完成选题 {len(result.get('topics', []))} 个；输入未变，本次未调用模型"


def guard(store, version):
    from .plan_controls import check_cancelled
    from .workspace_execution import check_running
    check_cancelled(store)
    check_running(store)
    store.renew()
    current, policy = store.policy()
    if current != version or not policy['enabled'] or policy['paused']:
        raise ValueError('选题期间规则变更或计划已暂停，未保存新结果')
