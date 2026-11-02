"""Manual Cron fires reuse the scheduler's durable identity, but ignore module times."""
import os

from .modules import TIMES, EXTERNAL
from .policy import local_day

LABELS = {"research": "信息采集", "organize": "资料整理与归类", "analytics": "数据分析", "industry": "行业分析", "topics": "选题策划", "content": "内容生产", "publish": "图文发布",
          "comments": "评论互动", "dm": "私信回复", "follow": "条件回关", "report": "运营日报"}


def cron_execution(store):
    from cron.executions import live_inflight_execution
    schedules = store.objects("schedule")
    if not schedules:
        return None
    execution = live_inflight_execution(schedules[0]["job_id"])
    # The Python script is a direct child of the owning Cron worker. A CLI tick or
    # another process must not borrow an unrelated/manual execution's authority.
    if execution and execution["status"] == "running" and execution["pid"] == os.getppid():
        return execution
    return None


def cron_request_id(store):
    execution = cron_execution(store)
    return execution['id'] if execution and 'scheduled_instant' in execution and execution['scheduled_instant'] is None else None


def run(store, now, request_id):
    from .runtime import _execute
    version, policy = store.policy()
    if not policy["enabled"] or policy["paused"]:
        return "未执行：运营计划未启用或已全局暂停"
    from .readiness import conditions
    readiness = conditions(store, policy)
    day = local_day(policy, now)
    batch_id = "manual:" + request_id
    batches = [b for b in store.objects("manual_run") if b["id"] == batch_id]
    if batches:
        day = batches[0]["day"]
        if batches[0]["version"] != version:
            return "未继续执行：本批次的规则已变更，请发起新的手动执行"
    else:
        store.put("manual_run", {"day": day, "version": version}, batch_id)
    slot = "manual:" + request_id
    store.manual_run_id = request_id
    try:
        if store.snapshot()["online"]:
            from .recovery import reconcile_pending
            reconcile_pending(store, policy, day)
        for stage in TIMES:
            if not policy["modules"][stage]:
                continue
            identity = store.start_run(day, stage, slot, version)
            if not identity:
                continue
            with store.connection() as db:
                from .readiness import web_held
                held = stage in EXTERNAL and web_held(db)
            if held:
                store.finish_run(identity, "skipped", "网页正在人工接管")
            elif store.run_options and not readiness[stage]["ready"]:
                store.finish_run(identity, "skipped", "；".join(readiness[stage]["reasons"]))
            elif stage in EXTERNAL and not store.snapshot()["online"]:
                store.finish_run(identity, "skipped", "桌面执行器离线，未执行网页动作")
            else:
                _execute(store, policy, day, version, stage, identity)
        return summary(store, day, slot)
    finally:
        store.manual_run_id = None


def summary(store, day, slot):
    with store.connection() as db:
        rows = [dict(r) for r in db.execute("SELECT stage,state,detail FROM runs WHERE day=? AND slot=? ORDER BY started", (day, slot))]
    states = {"completed": "完成", "needs_attention": "待完善", "skipped": "跳过", "failed": "失败", "cancelled": "取消", "interrupted": "中断"}
    counts = {state: sum(r["state"] == state for r in rows) for state in states}
    lines = ["手动运营：" + "，".join(f"{label} {counts[state]}" for state, label in states.items() if counts[state]),
             "忽略排期；同一批次重试不重复执行。"]
    lines.extend(f"- {LABELS[r['stage']]}：{states.get(r['state'], r['state'])}；{r['detail']}" for r in rows)
    lines.extend(_external_summary(store, slot))
    if not rows:
        lines.append("未选择执行模块")
    result = "\n".join(lines)
    from .upcoming import CANCEL_REASON
    if any(counts[s] for s in ("failed", "interrupted")) or any(r['state'] == 'cancelled' and r['detail'] != CANCEL_REASON for r in rows):
        raise RuntimeError(result)
    return result


def _external_summary(store, slot):
    from .blueprints import requirements
    with store.connection() as db:
        actions = [dict(r) for r in db.execute(
            "SELECT kind,state FROM actions WHERE json_extract(data,'$.manual_run_id')=?", (slot.removeprefix("manual:"),))]
    confirmed = sum(a["state"] in {"published", "confirmed"} for a in actions)
    lines = [f"\n本批次外部动作：记录 {len(actions)} 条，已核对成功 {confirmed} 条。阶段完成不代表已经发布或发送。"]
    _, policy = store.policy()
    assets = store.objects("asset")
    for module in ("publish", "comments", "dm"):
        if not policy["modules"][module]:
            missing = requirements(policy, module, assets)
            lines.append(f"- {LABELS[module]}：未加入当前生效计划；" + ("；".join(missing) if missing else "请在场景配置中加入并应用"))
    return lines
