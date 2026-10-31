"""A cron-owned tick; no plugin polling thread or separate scheduling authority."""
from datetime import datetime, timedelta, UTC
from pathlib import Path
import logging
import uuid
from zoneinfo import ZoneInfo

from .policy import local_day
from .report import daily_report
from .store import Store
from . import workflow


def ensure_schedule(store):
    from cron.jobs import create_job, get_job
    from hermes_constants import get_hermes_home
    records = store.objects("schedule")
    if records and get_job(records[0]["job_id"]):
        return records[0]["job_id"]
    script = get_hermes_home() / "scripts" / "operations_tick.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    import hermes_constants
    root = str(Path(hermes_constants.__file__).resolve().parent)
    script.write_text(f"import sys\nsys.path.insert(0, {root!r})\nimport hermes_bootstrap\nfrom plugins.operations.runtime import tick\nprint(tick())\n", encoding="utf-8")
    job = create_job(None, "every 1m", name="每日运营调度", script=str(script), no_agent=True, deliver="local")
    store.put("schedule", {"job_id": job["id"]})
    return job["id"]


def tick(store=None, now=None):
    store = store or Store()
    now = now or datetime.now(UTC)
    token = uuid.uuid4().hex
    if not store.lease(token):
        return "已有运营任务执行中"
    try:
        return _tick(store, now)
    finally:
        store.release(token)


def _tick(store, now):
    version, policy = store.policy()
    if not policy["enabled"]:
        return "运营已暂停"
    day = local_day(policy, now)
    local = now.astimezone(ZoneInfo(policy["timezone"]))
    _recover_reports(store, day)
    if not policy["paused"] and store.snapshot()["online"]:
        from .recovery import reconcile_pending
        reconcile_pending(store, policy, day)
    for stage, times in policy["times"].items():
        if policy["paused"] and stage != "report":
            continue
        for slot in sorted(set(times)):
            due = datetime.fromisoformat(f"{day}T{slot}").replace(tzinfo=local.tzinfo)
            age = (local - due).total_seconds()
            if age < 0:
                continue
            if stage != "report" and age > 1800:
                identity = store.start_run(day, stage, slot, version)
                if identity:
                    store.finish_run(identity, "missed", "超过执行窗口，未集中补发")
                continue
            if stage in {"publish", "interact"} and not store.snapshot()["online"]:
                continue
            identity = store.start_run(day, stage, slot, version)
            if identity:
                _execute(store, policy, day, version, stage, identity)
    return "本轮运营检查完成"


def _execute(store, policy, day, version, stage, identity):
    try:
        current_version, current = store.policy()
        if current_version != version or (current["paused"] and stage != "report") or not current["enabled"]:
            store.finish_run(identity, "cancelled", "规则发生变更")
            return
        if policy["deadline"] and day > policy["deadline"][:10] and stage != "report":
            store.finish_run(identity, "skipped", "目标已超过期限")
            return
        handlers = {"research": workflow.research, "publish": workflow.publish, "interact": workflow.interact}
        if stage == "report":
            daily_report(store, day)
            result = "日报已生成"
        else:
            result = handlers[stage](store, policy, day, version)
        store.finish_run(identity, "completed", str(result or "完成"))
    except Exception as exc:
        # A stage failure is durable and does not prevent the independent daily report.
        logging.getLogger(__name__).exception("Operations stage failed: %s", stage)
        store.finish_run(identity, "failed", str(exc)[:1500])
        store.event("stage_error", {"day": day, "stage": stage, "error": str(exc)[:1500]})


def _recover_reports(store, today):
    with store.connection() as db:
        first = db.execute("SELECT min(at) FROM events WHERE kind='policy'").fetchone()[0]
    if not first:
        return
    _, policy = store.policy()
    start = datetime.fromisoformat(first).astimezone(ZoneInfo(policy["timezone"])).date()
    end = datetime.fromisoformat(today).date()
    reports = {r["day"] for r in store.objects("report")}
    for offset in range(min((end - start).days, 3660)):
        day = (start + timedelta(days=offset)).isoformat()
        if day not in reports:
            daily_report(store, day, delayed=True)
