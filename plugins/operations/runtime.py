"""A cron-owned tick; no plugin polling thread or separate scheduling authority."""
from datetime import datetime, UTC
from pathlib import Path
import logging
import uuid

from .policy import local_day, now_iso
from .modules import EXTERNAL
from .occurrences import latest_due
from .store import encoded
from .report import daily_report
from .store import Store
from . import workflow


def ensure_schedule(store):
    from cron.jobs import create_job, get_job, list_jobs, resume_job
    from hermes_constants import get_hermes_home
    import hermes_constants
    script = get_hermes_home() / "scripts" / "operations_tick.py"
    # The database lock serializes Desktop/CLI saves; matching the durable script recovers
    # a crash between cron creation and writing the local receipt.
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT data FROM objects WHERE kind='schedule' ORDER BY created DESC LIMIT 1").fetchone()
        import json
        job = get_job(json.loads(row[0])["job_id"]) if row else None
        if not job:
            job = next((j for j in list_jobs(include_disabled=True) if j.get("script") == str(script) and j.get("no_agent")), None)
        if not job:
            script.parent.mkdir(parents=True, exist_ok=True)
            root = str(Path(hermes_constants.__file__).resolve().parent)
            script.write_text(f"import sys\nsys.path.insert(0, {root!r})\nimport hermes_bootstrap\nfrom plugins.operations.runtime import tick\nprint(tick())\n", encoding="utf-8")
            job = create_job(None, "every 1m", name="每日运营调度", script=str(script), no_agent=True, deliver="local")
        if not job.get("enabled", True):
            job = resume_job(job["id"])
        db.execute("INSERT OR REPLACE INTO objects VALUES ('schedule', 'schedule', ?, ?)",
                   (encoded({"job_id": job["id"]}), now_iso()))
    from .progress import sync_plan
    sync_plan(store, job['id'])
    return job["id"]


def schedule_state(store):
    from cron.jobs import get_job
    schedules = store.objects("schedule")
    job = get_job(schedules[0]["job_id"]) if schedules else None
    if not job:
        return "missing"
    return "ready" if job.get("enabled", True) else "paused"


def tick(store=None, now=None, *, request_id=None):
    from .manual import cron_request_id, run
    store = store or Store()
    now = now or datetime.now(UTC)
    request_id = request_id or cron_request_id(store)
    token = uuid.uuid4().hex
    if not store.lease(token):
        return "已有运营任务执行中"
    try:
        from .progress import bind
        bind(store, now, request_id)
        if request_id:
            return run(store, now, request_id)
        return _tick(store, now)
    finally:
        store.execution_id = None
        store.release(token)


def _tick(store, now):
    from .evidence_storage import maybe_cleanup
    maybe_cleanup(store, now)
    version, policy = store.policy()
    if not policy["enabled"]:
        return "运营已暂停"
    day = local_day(policy, now)
    if not policy["paused"] and store.snapshot()["online"]:
        from .recovery import reconcile_pending
        reconcile_pending(store, policy, day)
    for stage, due in latest_due(store, policy, now).items():
        if policy["paused"] and stage != "report":
            continue
        if stage in EXTERNAL and not store.snapshot()["online"]:
            continue
        scheduled_day, slot = due.date().isoformat(), due.strftime('%H:%M')
        if stage == 'report' and scheduled_day < day and store.objects('report', scheduled_day):
            continue
        identity = store.start_run(scheduled_day, stage, slot, version)
        if identity:
            # Quotas and new work belong to the actual execution day; a delayed
            # report alone summarizes its original day. The claim retains the due day.
            work_day = scheduled_day if stage == 'report' else day
            _execute(store, policy, work_day, version, stage, identity, delayed=scheduled_day < day)
    return "本轮运营检查完成"


def _execute(store, policy, day, version, stage, identity, *, delayed=False):
    from .outcomes import StageSkipped, describe
    try:
        current_version, current = store.policy()
        if current_version != version or (current["paused"] and stage != "report") or not current["enabled"]:
            store.finish_run(identity, "cancelled", "规则发生变更")
            return
        if policy["deadline"] and day > policy["deadline"][:10] and stage != "report":
            store.finish_run(identity, "skipped", "目标已超过期限")
            return
        from functools import partial
        handlers = {"research": workflow.research, "organize": workflow.organize, "topics": workflow.topics, "content": workflow.produce, "publish": workflow.publish,
                    "comments": partial(workflow.interact, kinds=("comment", "reply")),
                    "dm": partial(workflow.interact, kinds=("dm",)), "follow": partial(workflow.interact, kinds=("follow",))}
        if stage == "report":
            daily_report(store, day, delayed=delayed)
            result = "日报已生成"
        else:
            result = handlers[stage](store, policy, day, version)
        state, detail = describe(stage, result)
        store.finish_run(identity, state, detail)
    except StageSkipped as exc:
        store.finish_run(identity, "skipped", str(exc))
    except Exception as exc:
        # A stage failure is durable and does not prevent the independent daily report.
        logging.getLogger(__name__).exception("Operations stage failed: %s", stage)
        store.finish_run(identity, "failed", str(exc)[:1500])
        store.event("stage_error", {"day": day, "stage": stage, "error": str(exc)[:1500]})
