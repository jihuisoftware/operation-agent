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
    if data["state"] != "running":
        return
    try:
        alive = psutil.Process(data["pid"]).create_time() == data["process_started"]
    except psutil.NoSuchProcess:
        alive = False
    with store.connection() as db:
        lease = db.execute("SELECT expires FROM leases WHERE token=?", (data["id"],)).fetchone()
        if alive and lease and lease[0] > time.time():
            return
        data.update(state="interrupted", ended=now_iso(), detail="执行进程退出或租约失效；外部结果需核对，不自动重发")
        db.execute("UPDATE runs SET state='interrupted', detail=?, ended=? WHERE (slot=? OR substr(slot,1,?)=?) AND state='running'",
                   (data["detail"], data["ended"], data["id"], len(data["id"]) + 1, data["id"] + ":"))
    for step in data.get("steps", []):
        if step["state"] in {"running", "pending"}:
            step.update(state="interrupted", detail=data["detail"], ended=data["ended"])
    update_record(store, data)


def previous(store, identity, task, version, mode='normal', external_actions='standing_policy'):
    existing = record(store, identity)
    if existing and (existing["task"] != task or existing["version"] != version
                     or existing.get('mode', 'normal') != mode
                     or existing.get('action_mode', 'standing_policy') != external_actions):
        raise HTTPException(409, "同一请求标识不能用于不同任务、规则或执行方式")
    return existing


def update_record(store, data):
    if store.scope:
        data.update(business_id=store.scope['business_id'], topic_id=store.scope['id'])
    with store.connection() as db:
        db.execute("UPDATE objects SET data=? WHERE id=? AND kind='debug_run'", (encoded(data), data["id"]))


def execute(body, path=None):
    require_enabled()
    task, request_id, mode = body.get("task"), body.get("request_id"), body.get("mode", "normal")
    if task not in {*TASKS, "pipeline"} or mode not in {"normal", "quick"} or not isinstance(request_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", request_id):
        raise HTTPException(400, "任务或请求标识无效")
    from .operations_authorization import request_mode
    external_actions = request_mode(body, task, mode)
    identity = "debug:" + request_id
    store = DebugStore(identity, path)
    existing = previous(store, identity, task, body.get("version"), mode, external_actions)
    if existing:
        return existing
    if not store.lease(identity):
        raise HTTPException(409, "已有任务执行中，请等待结束或先处理当前任务")
    try:
        from .operations_pipeline import run_pipeline
        handler = run_pipeline if task == "pipeline" else run_task
        return previous(store, identity, task, body.get("version"), mode, external_actions) or handler(
            store, identity, task, body.get("version"), mode=mode, external_actions=external_actions)
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
    if task in EXTERNAL and mode != 'quick' and not policy["allowed"][task]:
        raise HTTPException(400, "该动作尚未授权")
    data = new_record(identity, task, TASKS[task][0], version, day)
    data.update(mode=mode, action_mode=external_actions)
    store.put("debug_run", data, identity)
    store.manual_run_id = identity
    from .operations_authorization import create
    create(store, data)
    run_id = store.start_run(day, module, identity, version)
    store.event("debug_start", {"task": task, "rule": policy, "run_id": run_id})
    outcome = invoke(store, task, policy, day, version, quick=mode == "quick")
    store.finish_run(run_id, outcome["state"], outcome["detail"])
    data.update(**outcome, ended=now_iso())
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
    try:
        from plugins.operations.debug_authorization import authorized
        if quick and task in EXTERNAL and not authorized(store, policy, task):
            raise StageSkipped('本次快速实测授权已失效，请重新发起')
        if task in {"publish", "comment", "reply", "dm", "follow"} and not store.snapshot()["online"]:
            raise StageSkipped("桌面执行器离线，请启动开发版 Desktop")
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
        if task == "report":
            result = daily_report(store, day)
        elif task == "publish" and content_id:
            result = workflow.publish(store, policy, day, version, content_id=content_id)
        else:
            result = handlers[task](store, policy, day, version)
        state, detail = describe(TASKS[task][1], result)
        store.event("debug_result", {"result": result})
    except StageSkipped as exc:
        state, detail = "skipped", str(exc)
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
            "SELECT data FROM objects WHERE kind='debug_run' ORDER BY created DESC LIMIT 30")]
        from plugins.operations.readiness import web_block_reason
        web_block = web_block_reason(db)
    for data in runs:
        recover_interrupted(store, data)
    from .operations_debug_status import task_status
    fields = ("id", "task", "title", "version", "day", "started", "ended", "state", "detail", "duration_ms")
    return {"version": version, "policy": policy,
            "tasks": [{"id": key, "title": value[0], "module": value[1]} for key, value in TASKS.items()],
            "runs": [{key: value for key, value in run.items() if key in fields} for run in runs],
            "task_status": task_status(store, runs), 'web_block_reason': web_block, "pipeline_available": True}


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
    return {"run": data, "events": [{**row, "data": json.loads(row["data"])} for row in events],
            "actions": [{**row, "data": json.loads(row["data"]), "result": json.loads(row["result"])} for row in actions]}
