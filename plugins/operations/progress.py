"""Operations step plans and progress projected into the shared Cron task journal."""
from .modules import TIMES
from .policy import local_day
from .occurrences import latest_due

STEPS = {
    'research': ('信息采集', '检索网页与 RSS，读取正文并保存去重来源'),
    'organize': ('资料整理与归类', '分批归类来源，保存摘要、事实陈述、观点、待核实信息及出处'),
    'analytics': ('数据分析', '计算完整日期范围的来源覆盖、趋势及业务指标，保存统计口径'),
    'industry': ('行业分析', '分别分析公开与内部证据，记录趋势、需求、竞争和经营建议'),
    'topics': ('选题策划', '读取已整理分类资料，生成候选选题与依据'),
    'content': ('内容生产', '依据整理资料与授权素材生成内容版本，原文核对事实，缺图保留草稿'),
    'publish': ('图文发布', '核对账号、素材、规则与额度，提交候选版本并核对发布结果'),
    'comments': ('评论互动', '读取相关笔记及收到的评论，依据上下文生成并核对评论或回复'),
    'dm': ('收到私信处理', '读取收到的消息，仅使用已确认知识回答，不确定事项转待处理'),
    'follow': ('条件回关', '核对关注关系、匹配条件及额度，记录符合条件的回关结果'),
    'report': ('运营日报', '依据实际执行台账生成日报，列出成果、未完成原因和次日建议'),
}


def definition(store):
    version, policy = store.policy()
    return {'managed_steps': True, 'topic': policy['topic'], 'goal': policy['goal'], 'policy_version': version,
            'enabled': policy['enabled'], 'paused': policy['paused'], 'timezone': policy['timezone'],
            'limits': policy['limits'], 'allowed': policy['allowed'],
            'steps': [{'title': STEPS[stage][0], 'intent': STEPS[stage][1],
                       'enabled': policy['modules'][stage], 'times': policy['times'][stage]} for stage in TIMES]}


def sync_plan(store, job_id=None):
    from cron.task_history import define
    from .scheduling import schedule_id
    job_id = job_id or schedule_id(store)
    if job_id:
        define(job_id, definition(store))


def bind(store, now, manual_id):
    from .manual import cron_execution
    from cron.task_history import declare
    execution = cron_execution(store)
    store.execution_id = execution['id'] if execution else None
    if not execution:
        return
    version, policy = store.policy()
    steps = planned_steps(store, policy, now, manual_id)
    if store.scope:
        for step in steps:
            step['id'] = store.scope['id'] + ':' + step['id']
            step['title'] = store.scope['business_name'] + ' / ' + policy['topic'] + ' · ' + step['title']
    owner = {'business_id': store.scope['business_id'], 'topic_id': store.scope['id'], 'account_slot': store.scope['account']} if store.scope else {}
    declare(execution['id'], steps, {'topic': policy['topic'], 'goal': policy['goal'],
            'day': local_day(policy, now), 'policy_version': version, 'manual': bool(manual_id),
            'limits': policy['limits'], 'allowed': policy['allowed'], 'times': policy['times'], **owner})


def planned_steps(store, policy, now, manual_id):
    day = local_day(policy, now)
    if not manual_id:
        return scheduled_steps(store, policy, now)
    with store.connection() as db:
        previous = {(r['stage'], r['slot']): dict(r) for r in db.execute('SELECT * FROM runs WHERE day=?', (day,))}
    steps = []
    for stage in TIMES:
        for slot in ['manual:' + manual_id]:
            state, detail = 'pending', ''
            if not policy['modules'][stage]:
                state = 'disabled'
            elif not policy['enabled'] or policy['paused']:
                state, detail = 'not_run', '运营计划未启用或已全局暂停'
            elif (stage, slot) in previous:
                old = previous[stage, slot]
                state = 'cancelled' if old['state'] == 'cancelled' else 'already_done'
                detail = '此时段已有执行记录，本轮不重复：' + old['detail']
            steps.append({'id': f'{stage}:{slot}', 'title': STEPS[stage][0] + ('' if manual_id else ' · ' + slot),
                          'intent': STEPS[stage][1], 'state': state, 'detail': detail})
    return steps


def scheduled_steps(store, policy, now):
    if not policy['enabled']:
        return []
    steps = []
    for stage, due in latest_due(store, policy, now).items():
        day, slot = due.date().isoformat(), due.strftime('%H:%M')
        with store.connection() as db:
            previous = db.execute('SELECT 1 FROM runs WHERE day=? AND stage=? AND slot=?', (day, stage, slot)).fetchone()
        if previous or policy['paused']:
            continue
        if stage == 'report' and day < local_day(policy, now) and store.objects('report', day):
            continue
        steps.append({'id': f'{stage}:{slot}', 'title': STEPS[stage][0] + ' · ' + slot,
                      'intent': STEPS[stage][1], 'state': 'pending', 'detail': '', 'due': due.isoformat()})
    return steps


def update(store, identity, state, detail, data=None):
    from cron.task_history import progress
    with store.connection() as db:
        row = db.execute('SELECT stage,slot,day FROM runs WHERE id=?', (identity,)).fetchone()
    if not row:
        return
    store.event('progress', {'run_id': identity, 'day': row['day'], 'state': state, 'detail': detail, 'data': data or {}})
    if store.execution_id:
        prefix = store.scope['id'] + ':' if store.scope else ''
        progress(store.execution_id, prefix + f"{row['stage']}:{row['slot']}", state=state, detail=detail, data=data)


def saved(store, kind, identity, data):
    # Keep the result as it was produced, even when its editable business version changes later.
    fields = ('title', 'url', 'state', 'ready', 'summary', 'reason', 'error', 'source_ids', 'asset_ids')
    result = data if kind in {'content', 'brief', 'report', 'check', 'review', 'organized_source', 'organization'} else {k: data[k] for k in fields if k in data}
    store.progress('已保存执行产物', {'kind': kind, 'id': identity, 'result': result})
