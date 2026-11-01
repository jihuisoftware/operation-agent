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

router = APIRouter(prefix="/debug")
TASKS = {
    "research": ("信息采集与选题", "research"), "content": ("内容生产", "content"),
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
        super().event(kind, {**data, "debug_id": self.debug_id})


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
        db.execute("UPDATE runs SET state='interrupted', detail=?, ended=? WHERE slot=? AND state='running'",
                   (data["detail"], data["ended"], data["id"]))
    update_record(store, data)


def previous(store, identity, task, version):
    existing = record(store, identity)
    if existing and (existing["task"] != task or existing["version"] != version):
        raise HTTPException(409, "同一请求标识不能用于不同任务或规则")
    return existing


def update_record(store, data):
    with store.connection() as db:
        db.execute("UPDATE objects SET data=? WHERE id=? AND kind='debug_run'", (encoded(data), data["id"]))


def execute(body, path=None):
    require_enabled()
    task, request_id = body.get("task"), body.get("request_id")
    if task not in TASKS or not isinstance(request_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", request_id):
        raise HTTPException(400, "任务或请求标识无效")
    identity = "debug:" + request_id
    store = DebugStore(identity, path)
    existing = previous(store, identity, task, body.get("version"))
    if existing:
        return existing
    if not store.lease(identity):
        raise HTTPException(409, "已有任务执行中，请等待结束或先处理当前任务")
    try:
        return previous(store, identity, task, body.get("version")) or run_task(store, identity, task, body.get("version"))
    finally:
        store.release(identity)


def run_task(store, identity, task, version):
    current, policy = store.policy()
    module = TASKS[task][1]
    if current != version:
        raise HTTPException(409, "规则已变更，请刷新调试页")
    if not policy["enabled"] or policy["paused"] or not policy["modules"][module]:
        raise HTTPException(400, "请先启用对应模块并解除全局暂停")
    day = local_day(policy)
    if policy["deadline"] and day > policy["deadline"][:10] and task != "report":
        raise HTTPException(400, "运营目标已超过期限")
    if task in {"publish", "comment", "reply", "dm", "follow"} and not policy["allowed"][task]:
        raise HTTPException(400, "该动作尚未授权")
    data = {"id": identity, "task": task, "title": TASKS[task][0], "version": version,
            "day": day, "started": now_iso(), "ended": None, "state": "running", "detail": "开始执行",
            "pid": os.getpid(), "process_started": psutil.Process().create_time()}
    store.put("debug_run", data, identity)
    store.manual_run_id = identity
    run_id = store.start_run(day, module, identity, version)
    store.event("debug_start", {"task": task, "rule": policy, "run_id": run_id})
    started = datetime.now(UTC)
    try:
        if task in {"publish", "comment", "reply", "dm", "follow"} and not store.snapshot()["online"]:
            raise StageSkipped("桌面执行器离线，请启动开发版 Desktop")
        handlers = {"research": workflow.research, "content": workflow.produce, "publish": workflow.publish,
                    **{k: partial(workflow.interact, kinds=(k,)) for k in ("comment", "reply", "dm", "follow")}}
        if task == "report":
            result = daily_report(store, day)
        else:
            result = handlers[task](store, policy, day, version)
        state, detail = describe(module, result)
        store.event("debug_result", {"result": result})
    except StageSkipped as exc:
        state, detail = "skipped", str(exc)
    except Exception as exc:
        logging.getLogger(__name__).exception("Development task failed: %s", task)
        state, detail = "failed", str(exc)
        store.event("debug_exception", {"error": detail, "traceback": "".join(traceback.format_exception(*sys.exc_info()))})
    store.finish_run(run_id, state, detail)
    data.update(state=state, detail=detail, ended=now_iso(), duration_ms=int((datetime.now(UTC) - started).total_seconds() * 1000))
    update_record(store, data)
    return data


@router.get("")
def catalog():
    require_enabled()
    store = Store()
    version, policy = store.policy()
    runs = store.objects("debug_run")[:30]
    for data in runs:
        recover_interrupted(store, data)
    return {"version": version, "policy": policy,
            "tasks": [{"id": key, "title": value[0], "module": value[1]} for key, value in TASKS.items()],
            "runs": runs}


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
    return {"run": data, "events": [{**row, "data": json.loads(row["data"])} for row in events], "actions": actions}
