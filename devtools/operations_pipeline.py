"""Development-only orchestration of the real stages, with durable batch evidence."""
import logging
import time

from fastapi import HTTPException

from plugins.operations.policy import local_day, now_iso

EXTERNAL = {"publish", "comment", "reply", "dm", "follow"}
DEPENDENCIES = {"organize": "research", "topics": "organize", "content": "topics", "publish": "content"}


def unavailable(store, data, step, policy):
    task = step["id"]
    # A diagnostic report is always produced, even after a pause or failed prerequisite.
    if task == "report":
        return ""
    version, current = store.policy()
    if version != data["version"]:
        return "规则版本已变更，本批次停止后续业务步骤"
    if not current["enabled"] or current["paused"]:
        return "运营计划未启用或已全局暂停"
    if local_day(current) != data["day"]:
        return "已跨越运营日期，请发起新的测试；未沿用昨日额度"
    if policy["deadline"] and data["day"] > policy["deadline"][:10]:
        return "运营目标已超过期限"
    if not policy["modules"][step["module"]]:
        return "模块未启用；未修改现有计划"
    if task in EXTERNAL and not policy["allowed"][task]:
        return "该动作尚未授权"
    dependency = DEPENDENCIES.get(task)
    prior = next((s for s in data["steps"] if s["id"] == dependency), None)
    usable_partial = prior and dependency == 'organize' and prior['state'] == 'needs_attention' and prior.get('result', {}).get('usable', 0) > 0
    if prior and prior["state"] != "completed" and not usable_partial:
        return f"依赖步骤「{prior['title']}」未完成，不使用旧产物替代本轮结果"
    if task == "publish" and not data.get("content_id"):
        return "本轮没有保存可发布的内容版本"
    return ""


def run_step(store, data, step, policy):
    from .operations_debug import invoke, update_record
    store.debug_step = step["id"]
    store.renew()
    step.update(state="running", started=now_iso(), detail="开始执行")
    update_record(store, data)
    run_id = store.start_run(data["day"], step["module"], data["id"] + ":" + step["id"], data["version"])
    step["run_id"] = run_id
    store.event("pipeline_step_start", {"step": step, "version": data["version"], "content_id": data.get("content_id")})
    reason = unavailable(store, data, step, policy)
    if reason:
        outcome = {"state": "skipped", "detail": reason, "duration_ms": 0}
    else:
        outcome = invoke(store, step["id"], policy, data["day"], data["version"], content_id=data.get("content_id"))
    step.update(**outcome, ended=now_iso())
    if step["id"] == "content" and isinstance(step.get("result"), dict):
        data["content_id"] = step["result"].get("content_id")
    store.finish_run(run_id, step["state"], step["detail"])
    store.event("pipeline_step_end", {"step": step})
    update_record(store, data)


def run_pipeline(store, identity, task, version):
    from .operations_debug import TASKS, new_record, update_record
    current, policy = store.policy()
    if current != version:
        raise HTTPException(409, "规则已变更，请刷新调试页")
    day = local_day(policy)
    data = new_record(identity, task, "整链路测试", version, day)
    data.update(mode="live", policy=policy, steps=[
        {"id": key, "title": title, "module": module, "state": "pending", "detail": "等待执行"}
        for key, (title, module) in TASKS.items()])
    store.put("debug_run", data, identity)
    store.manual_run_id = identity
    store.event("pipeline_start", {"day": day, "version": version, "policy": policy, "mode": "live"})
    started = time.monotonic()
    try:
        for step in data["steps"]:
            run_step(store, data, step, policy)
    except Exception as exc:
        # Infrastructure/lease loss must stop the batch; never silently replay a submission.
        import traceback
        logging.getLogger(__name__).exception("Development pipeline interrupted: %s", identity)
        data.update(state="interrupted", detail=str(exc))
        store.event("pipeline_exception", {"error": str(exc), "traceback": traceback.format_exc()})
        for step in data["steps"]:
            if step["state"] in {"pending", "running"}:
                step.update(state="interrupted", detail="批次中断：" + str(exc), ended=now_iso())
                if step.get("run_id"):
                    store.finish_run(step["run_id"], "interrupted", step["detail"])
    else:
        summarize(store, data)
    data.update(ended=now_iso(), duration_ms=int((time.monotonic() - started) * 1000))
    store.debug_step = None
    store.event("pipeline_end", {"state": data["state"], "detail": data["detail"]})
    update_record(store, data)
    return data


def summarize(store, data):
    counts = {state: sum(s["state"] == state for s in data["steps"])
              for state in ("completed", "failed", "skipped", "needs_attention")}
    with store.connection() as db:
        errors = db.execute(
            "SELECT count(*) FROM events WHERE json_extract(data,'$.debug_id')=? AND "
            "(json_extract(data,'$.error') IS NOT NULL OR json_extract(data,'$.data.result.state')='unavailable')",
            (data["id"],)).fetchone()[0]
        actions = [dict(r) for r in db.execute(
            "SELECT id,kind,state,result FROM actions WHERE json_extract(data,'$.manual_run_id')=?", (data["id"],))]
    data["counts"] = counts
    data["external_actions"] = {"total": len(actions), "confirmed": sum(a["state"] in {"confirmed", "published"} for a in actions)}
    data["state"] = "failed" if counts["failed"] else "needs_attention" if counts["skipped"] or counts["needs_attention"] or errors else "completed"
    data["detail"] = (f"完成 {counts['completed']}/{len(data['steps'])} 步；失败 {counts['failed']}，"
                      f"跳过 {counts['skipped']}，待完善 {counts['needs_attention']}；异常事件 {errors}。"
                      f"外部动作已核对 {data['external_actions']['confirmed']}/{len(actions)} 条。"
                      "本次使用真实业务服务；跳过或未核对不代表全链路通过。")
