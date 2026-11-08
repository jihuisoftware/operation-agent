"""Source-checkout-only single-task execution; excluded from distribution snapshots."""
from datetime import datetime, UTC
from functools import partial
import json
import logging
import os
import re
import sys
import time
import traceback

import psutil
from fastapi import APIRouter, HTTPException
from hermes_cli.config import load_config_readonly
from plugins.operations import workflow
from plugins.operations.outcomes import StageSkipped, describe
from plugins.operations.policy import local_day, now_iso
from plugins.operations.report import daily_report
from plugins.operations.store import Store, encoded

from .operations_pipeline import EXTERNAL

router = APIRouter(prefix="/debug")
from .operations_task_api import router as task_router
router.include_router(task_router)
from .operations_debug_history import router as history_router
router.include_router(history_router)
from .operations_debug_cancel import router as cancel_router
router.include_router(cancel_router)
TASKS = {
    "research": ("信息采集", "research"), "organize": ("资料整理与归类", "organize"), "analytics": ("数据分析", "analytics"), "industry": ("行业分析", "industry"), "topics": ("选题策划", "topics"), "content": ("内容生产", "content"),
    "publish": ("图文发布", "publish"), "comment": ("主动评论", "comments"),
    "reply": ("评论回复", "comments"), "dm": ("收到私信处理", "dm"),
    "follow": ("条件回关", "follow"), "report": ("运营日报", "report"),
}


def require_enabled():
    if load_config_readonly().get("development", {}).get("operations_debug") is not True:
        raise HTTPException(404, "调试功能未开启；仅开发 Profile 可配置 development.operations_debug: true")


class DebugStore(Store):
    def __init__(self, identity, path=None):
        self.debug_id = identity
        super().__init__(path)

    def event(self, kind, data):
        super().event(kind, {**data, "debug_id": self.debug_id, "step_id": getattr(self, "debug_step", None)})


def record(store, identity):
    with store.connection() as db:
        row = db.execute("SELECT data FROM objects WHERE id=? AND kind='debug_run'", (identity,)).fetchone()
    data = json.loads(row[0]) if row else None
    if data:
        recover_interrupted(store, data)
    return data


def recover_interrupted(store, data):
    from plugins.operations.execution_resume import recover
    from plugins.operations.execution_pause import load
    recover(store)
    if data['state'] not in {'running', 'paused', 'interrupted'}:
        return
    try:
        alive = psutil.Process(data['pid']).create_time() == data['process_started']
    except psutil.NoSuchProcess:
        alive = False
    with store.connection() as db:
        lease = db.execute('SELECT expires FROM leases WHERE token=?', (data['id'],)).fetchone()
    if alive and lease and lease[0] > time.time():
        return
    paused = load(store, data['id'])
    if paused and paused['state'] == 'paused' and data['state'] in {'running', 'interrupted', 'paused'}:
        original = encoded(data)
        data.update(state='paused', revision=paused['revision'], detail=paused['error'])
        for step in data.get('steps', []):
            if step['state'] in {'running', 'pending', 'interrupted'}:
                step.update(state='paused', detail=paused['error'])
        from .operations_debug_status import persist_recovery
        persist_recovery(store, data, original)
        return
    if data["state"] != "running":
        return
    with store.connection() as db:
        lease = db.execute("SELECT expires FROM leases WHERE token=?", (data["id"],)).fetchone()
        if alive and lease and lease[0] > time.time():
            return
        external = db.execute("SELECT 1 FROM actions WHERE json_extract(data,'$.manual_run_id')=?", (data['id'],)).fetchone()
        detail = '执行进程退出或租约失效；外部结果需核对，不自动重发' if external else '执行进程退出或租约失效；本批次没有外部提交记录'
        data.update(state="interrupted", ended=now_iso(), detail=detail)
        if not alive:
            db.execute("DELETE FROM leases WHERE id='account' AND token=?", (data['id'],))
        db.execute("UPDATE runs SET state='interrupted', detail=?, ended=? WHERE (slot=? OR substr(slot,1,?)=?) AND state='running'",
                   (data["detail"], data["ended"], data["id"], len(data["id"]) + 1, data["id"] + ":"))
    for step in data.get("steps", []):
        if step["state"] in {"running", "pending"}:
            step.update(state="interrupted", detail=data["detail"], ended=data["ended"])
    update_record(store, data)


def previous(store, identity, task, version, mode='normal', external_actions='standing_policy', selected_tasks=None):
    existing = record(store, identity)
    if existing and (existing["task"] != task or existing["version"] != version
                     or existing.get('mode', 'normal') != mode
                     or existing.get('action_mode', 'standing_policy') != external_actions
                     or existing.get('selected_tasks') != selected_tasks):
        raise HTTPException(409, "同一请求标识不能用于不同任务、规则或执行方式")
    return existing


def update_record(store, data):
    if store.scope:
        data.update(business_id=store.scope['business_id'], topic_id=store.scope['id'])
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        from plugins.operations.batch_cancellation import preserve
        preserve(db, data)
        db.execute("UPDATE objects SET data=? WHERE id=? AND kind='debug_run'", (encoded(data), data["id"]))


def execute(body, path=None):
    require_enabled()
    task, request_id, mode = body.get("task"), body.get("request_id"), body.get("mode", "normal")
    if task not in {*TASKS, "pipeline"} or mode not in {"normal", "quick"} or not isinstance(request_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", request_id):
        raise HTTPException(400, "任务或请求标识无效")
    from .operations_authorization import request_mode
    from .operations_selection import parse
    selected_tasks = parse(body, task, mode)
    external_actions = request_mode(body, task, mode, selected_tasks)
    identity = "debug:" + request_id
    store = DebugStore(identity, path)
    existing = previous(store, identity, task, body.get("version"), mode, external_actions, selected_tasks)
    if existing:
        return existing
    from .operations_selection import require_selected
    require_selected(task, selected_tasks)
    if not store.lease(identity):
        from .operations_debug_status import active_execution
        occupied = active_execution(store)
        message = occupied['message'] if occupied else '已有任务执行中'
        raise HTTPException(409, message + '；本次调试未启动，请等待当前任务结束后重试')
    from plugins.operations.batch_cancellation import BatchCancelled, check, mark
    try:
        check(store, batch=identity)
        from .operations_pipeline import run_pipeline
        handler = run_pipeline if task == "pipeline" else run_task
        options = {'selected_tasks': selected_tasks} if task == 'pipeline' else {}
        return previous(store, identity, task, body.get("version"), mode, external_actions, selected_tasks) or handler(
            store, identity, task, body.get("version"), mode=mode, external_actions=external_actions, **options)
    except BatchCancelled:
        data = record(store, identity) or new_record(identity, task, TASKS.get(task, ('整链路测试',))[0], body.get('version'), local_day(store.policy()[1]))
        data.setdefault('mode', mode)
        data.setdefault('action_mode', external_actions)
        if selected_tasks is not None:
            data.setdefault('selected_tasks', selected_tasks)
        mark(data, data.get('cancellation_requested_at') or now_iso())
        store.put('debug_run', data, identity)
        return data
    finally:
        store.release(identity)


def run_task(store, identity, task, version, *, mode="normal", external_actions='standing_policy'):
    current, policy = store.policy()
    module = TASKS[task][1]
    if current != version:
        raise HTTPException(409, "规则已变更，请刷新调试页")
    if not policy["enabled"] or policy["paused"] or not policy["modules"][module]:
        raise HTTPException(400, "请先启用对应模块并解除全局暂停")
    day = local_day(policy)
    if policy["deadline"] and day > policy["deadline"][:10] and task != "report":
        raise HTTPException(400, "运营目标已超过期限")
    if task in EXTERNAL and mode != 'quick' and external_actions != 'publish_once' and not policy["allowed"][task]:
        raise HTTPException(400, "该动作尚未授权")
    data = new_record(identity, task, TASKS[task][0], version, day)
    data.update(mode=mode, action_mode=external_actions, policy=policy)
    store.put("debug_run", data, identity)
    store.manual_run_id = identity
    from .operations_authorization import create
    create(store, data)
    run_id = store.start_run(day, module, identity, version)
    store.event("debug_start", {"task": task, "rule": policy, "run_id": run_id})
    outcome = invoke(store, task, policy, day, version, quick=mode == "quick")
    store.finish_run(run_id, outcome["state"], outcome["detail"])
    data.update(**outcome, ended=now_iso())
    if outcome['state'] == 'paused':
        from plugins.operations.execution_pause import load
        data['revision'] = load(store, identity)['revision']
    update_record(store, data)
    return data


def new_record(identity, task, title, version, day):
    return {"id": identity, "task": task, "title": title, "version": version,
            "day": day, "started": now_iso(), "ended": None, "state": "running", "detail": "开始执行",
            "pid": os.getpid(), "process_started": psutil.Process().create_time(), "model_quota": "unlimited"}


def invoke(store, task, policy, day, version, *, content_id=None, quick=False):
    started = datetime.now(UTC)
    result = None
    owns_run_options = False
    from plugins.operations.execution_pause import ExecutionPaused
    from plugins.operations.batch_cancellation import BatchCancelled, check
    try:
        check(store)
        from plugins.operations.debug_authorization import authorized
        if quick and task in EXTERNAL and not authorized(store, policy, task):
            raise StageSkipped('本次快速实测授权已失效，请重新发起')
        if task in EXTERNAL and not getattr(store, 'start_preflight_done', False):
            from plugins.operations.execution_preflight import verify_for_start
            verify_for_start(store, version)
            store.start_preflight_done = True
        if task in {"publish", "comment", "reply", "dm", "follow"} and not store.online():
            from plugins.operations.execution_pause import pause
            reason = {'error_code': 'BROWSER_UNAVAILABLE', 'error': '桌面执行器离线，请启动 Desktop 后手动继续'}
            pause(store, reason)
            raise ExecutionPaused(reason)
        if quick:
            coverage = bool((store.run_options or {}).get("coverage"))
            # Keep the persisted policy object unchanged: workflow guards compare it exactly;
            # quick bounds and pipeline coverage are carried by run_options and unavailable().
            if not coverage:
                store.run_options = {"read_limit": 1, "query_limit": 1, "quick": True,
                                     'external_actions': 'execute_once' if task in EXTERNAL else 'not_requested'}
                owns_run_options = True
        handlers = {"research": workflow.research, "organize": workflow.organize, "analytics": workflow.analytics, "industry": workflow.industry, "topics": workflow.topics, "content": workflow.produce, "publish": workflow.publish,
                    **{k: partial(workflow.interact, kinds=(k,)) for k in ("comment", "reply", "dm", "follow")}}
        from plugins.operations.resume_actions import continue_actions
        continued = continue_actions(store, task, policy, day, version)
        if continued is not None:
            result = continued
        elif task == "report":
            result = daily_report(store, day)
        elif task == "publish" and content_id:
            result = workflow.publish(store, policy, day, version, content_id=content_id)
        else:
            result = handlers[task](store, policy, day, version)
        check(store)
        state, detail = describe(TASKS[task][1], result)
        store.event("debug_result", {"result": result})
    except BatchCancelled as exc:
        state, detail = 'cancelled', str(exc)
    except ExecutionPaused as exc:
        state, detail, result = 'paused', str(exc), exc.result
    except StageSkipped as exc:
        state, detail = "skipped", str(exc)
        result = getattr(exc, 'result', None)
        if result:
            store.event('action_deferred', result)
    except Exception as exc:
        logging.getLogger(__name__).exception("Development task failed: %s", task)
        state, detail = "failed", str(exc)
        store.event("debug_exception", {"error": detail, "traceback": "".join(traceback.format_exception(*sys.exc_info()))})
    if owns_run_options:
        store.run_options = None
    return {"state": state, "detail": detail, "result": result,
            "duration_ms": int((datetime.now(UTC) - started).total_seconds() * 1000)}


@router.get("")
def catalog():
    require_enabled()
    store = Store()
    version, policy = store.policy()
    with store.connection() as db:
        runs = [json.loads(row[0]) for row in db.execute(
            "SELECT r.data FROM objects r WHERE r.kind='debug_run' AND NOT EXISTS(SELECT 1 FROM objects h "
            "WHERE h.id='debug-history-hidden:'||r.id AND h.kind='debug_history_hidden') ORDER BY r.created DESC LIMIT 30")]
        from plugins.operations.readiness import web_block_reason
        web_block = web_block_reason(db)
    for data in runs:
        recover_interrupted(store, data)
    from .operations_debug_status import active_execution, present_run, task_status
    runs = [present_run(store, run) for run in runs]
    fields = ("id", "task", "title", "version", "day", "started", "ended", "state", "detail", "duration_ms", "revision", "attempt", "action_mode", "selected_tasks")
    return {"version": version, "policy": policy,
            "tasks": [{"id": key, "title": value[0], "module": value[1]} for key, value in TASKS.items()],
            "runs": [{key: value for key, value in run.items() if key in fields} for run in runs],
            "task_status": task_status(store, runs), "execution": active_execution(store), 'web_block_reason': web_block,
            "pipeline_available": True, 'selective_quick_available': True, 'selective_pipeline_available': True,
            'browser_check_available': True, 'task_details_available': True, 'history_clear_available': True, 'cancel_all_available': True}


@router.post("/run")
def run(body: dict):
    return execute(body)


@router.get("/{request_id}")
def detail(request_id: str):
    require_enabled()
    store = Store()
    data = record(store, request_id)
    if not data:
        raise HTTPException(404, "调试记录不存在")
    with store.connection() as db:
        events = [dict(row) for row in db.execute(
            "SELECT id,at,kind,data FROM events WHERE json_extract(data,'$.debug_id')=? ORDER BY id", (request_id,))]
        actions = [dict(row) for row in db.execute(
            "SELECT * FROM actions WHERE json_extract(data,'$.manual_run_id')=? ORDER BY created", (request_id,))]
    from .operations_debug_status import present_run
    return {"run": present_run(store, data), "events": [{**row, "data": json.loads(row["data"])} for row in events],
            "actions": [{**row, "data": json.loads(row["data"]), "result": json.loads(row["result"])} for row in actions]}


@router.post('/{identity}/resume')
def resume_run(identity: str, body: dict):
    from .operations_resume import resume
    from plugins.operations.execution_pause import ExecutionPaused
    try:
        return resume(identity, body)
    except (ValueError, KeyError, ExecutionPaused) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post('/browser-check')
def check_browser(body: dict):
    from .operations_browser_check import check
    from plugins.operations.execution_pause import ExecutionPaused
    try:
        return check(body)
    except ExecutionPaused as exc:
        return {'state': 'paused', 'detail': str(exc), 'submitted': False}
    except (ValueError, KeyError) as exc:
        raise HTTPException(409, str(exc)) from exc
