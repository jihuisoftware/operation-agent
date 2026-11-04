"""Explicit continuation of the same development batch, with cumulative one-run grants."""
import os

import psutil
from fastapi import HTTPException

from plugins.operations import execution_resume
from plugins.operations.execution_pause import load
from plugins.operations.policy import now_iso


def resume(identity, body):
    from .operations_debug import DebugStore, require_enabled, record, update_record, invoke, TASKS
    from .operations_pipeline import execute_steps, summarize
    require_enabled()
    store = DebugStore(identity)
    data = record(store, identity)
    if not data:
        raise HTTPException(404, '调试批次不存在')
    if data.get('action_mode') == 'execute_once' and body.get('external_actions') != 'execute_once':
        raise HTTPException(400, '继续快速实测需明确确认真实执行方式')
    replay = execution_resume.replay(store, identity, body)
    if replay:
        return replay
    if not store.lease(identity):
        raise HTTPException(409, '已有任务执行中，本次继续未启动')
    store.manual_run_id = identity
    try:
        resumed, repeated = execution_resume.prepare(store, identity, body)
        if repeated:
            return resumed.get('result', resumed)
        data.update(state='running', revision=resumed['revision'], attempt=resumed['attempt'], ended=None,
                    pid=os.getpid(), process_started=psutil.Process().create_time())
        update_record(store, data)
        policy = store.policy()[1]
        quick = data.get('mode') == 'quick'
        from .operations_pipeline import EXTERNAL, requires_account
        store.run_options = {'account_required': data['task'] in EXTERNAL or requires_account(policy, data.get('steps', []), quick)}
        if quick:
            store.run_options = {**store.run_options, 'read_limit': 1, 'query_limit': 1, 'quick': True, 'coverage': data['task'] == 'pipeline',
                                 'external_actions': data.get('action_mode')}
        store.report_phase = 'completed'
        if data['task'] == 'pipeline':
            execute_steps(store, data, policy, quick=quick, coverage=quick)
            summarize(store, data)
        else:
            task = data['task']
            run = store.start_run(data['day'], TASKS[task][1], f"{identity}:{task}:resume:{data['attempt']}", data['version'])
            outcome = invoke(store, task, policy, data['day'], data['version'], quick=quick)
            store.finish_run(run, outcome['state'], outcome['detail'])
            data.update(outcome)
        if data['state'] == 'paused':
            data['revision'] = load(store, identity)['revision']
        data['ended'] = now_iso()
        update_record(store, data)
        return execution_resume.complete(store, identity, body, data)
    finally:
        store.release(identity)
