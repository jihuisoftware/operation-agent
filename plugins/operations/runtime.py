"""A cron-owned tick; no plugin polling thread or separate scheduling authority."""
from datetime import datetime, UTC
from pathlib import Path
import logging
import uuid

from .policy import local_day, now_iso
from .modules import EXTERNAL
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
    from .scheduling import schedule_id, save_schedule
    with (store.workspace.connection() if store.workspace else store.connection()) as db:
        db.execute("BEGIN IMMEDIATE")
        identity = schedule_id(store, db)
        job = get_job(identity) if identity else None
        if not job:
            job = next((j for j in list_jobs(include_disabled=True) if j.get("script") == str(script) and j.get("no_agent")), None)
        if not job:
            script.parent.mkdir(parents=True, exist_ok=True)
            root = str(Path(hermes_constants.__file__).resolve().parent)
            script.write_text(f"import sys\nsys.path.insert(0, {root!r})\nimport hermes_bootstrap\nfrom plugins.operations.runtime import tick\nprint(tick())\n", encoding="utf-8")
            job = create_job(None, "every 1m", name="每日运营调度", script=str(script), no_agent=True, deliver="local")
        if not job.get("enabled", True):
            job = resume_job(job["id"])
        save_schedule(store, db, job["id"])
    from .progress import sync_plan
    sync_plan(store, job['id'])
    return job["id"]


def schedule_state(store):
    from cron.jobs import get_job
    from .scheduling import schedule_id
    identity = schedule_id(store)
    job = get_job(identity) if identity else None
    if not job:
        return "missing"
    return "ready" if job.get("enabled", True) else "paused"


def tick(store=None, now=None, *, request_id=None, scheduled=False):
    if store is None:
        from .workspace_runtime import dispatch
        return dispatch(now)
    from .manual import cron_request_id, run
    store = store or Store()
    now = now or datetime.now(UTC)
    store.execution_now = now
    request_id = request_id or (None if scheduled else cron_request_id(store))
    from .workspace_execution import check_running
    check_running(store)
    token = uuid.uuid4().hex
    if not store.lease(token):
        return "已有运营任务执行中"
    try:
        from .progress import bind
        bind(store, now, request_id)
        from .quick_start import drain
        quick = drain(store, now)
        if quick is not None:
            return quick
        if request_id:
            return run(store, now, request_id, one_stage=scheduled)
        return _tick(store, now, one_stage=scheduled)
    finally:
        store.execution_id = None
        store.release(token)


def _tick(store, now, *, one_stage=False):
    from .evidence_storage import maybe_cleanup
    maybe_cleanup(store, now)
    version, policy = store.policy()
    if not policy["enabled"]:
        return "运营已暂停"
    if policy["paused"]:
        return "运营已全局暂停"
    from .readiness import refresh
    readiness = refresh(store, now)
    day = local_day(policy, now)
    if not policy["paused"] and store.online():
        from .recovery import reconcile_pending
        reconcile_pending(store, policy, day)
    from .publication_plan import publish_due
    if publish_due(store, now) and one_stage:
        return '本轮已处理审核排期'
    from .workspace_upcoming import queue_due
    for stage, due in queue_due(store, policy, now).items():
        if not readiness[stage]["ready"]:
            continue
        if stage in EXTERNAL and not store.online():
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
            if one_stage:
                break
    from .publication_waiting import pending_detail
    waiting = pending_detail(store, now) if policy['modules']['publish'] else None
    return waiting or "本轮运营检查完成"


def _execute(store, policy, day, version, stage, identity, *, delayed=False):
    from .outcomes import StageSkipped, describe
    from .analysis_runs import AnalysisCancelled
    from .execution_pause import ExecutionPaused
    try:
        from .plan_controls import check_cancelled
        check_cancelled(store)
        if stage in EXTERNAL:
            from .execution_pause import guard
            guard(store, web=True)
        current_version, current = store.policy()
        if current_version != version or current["paused"] or not current["enabled"]:
            store.finish_run(identity, "cancelled", "规则发生变更")
            return
        if policy["deadline"] and day > policy["deadline"][:10] and stage != "report":
            store.finish_run(identity, "skipped", "目标已超过期限")
            return
        from functools import partial
        handlers = {"research": workflow.research, "organize": workflow.organize, "analytics": workflow.analytics, "industry": workflow.industry, "topics": workflow.topics, "content": workflow.produce, "publish": workflow.publish,
                    "comments": partial(workflow.interact, kinds=("comment", "reply")),
                    "dm": partial(workflow.interact, kinds=("dm",)), "follow": partial(workflow.interact, kinds=("follow",))}
        from .resume_actions import continue_actions
        continued = continue_actions(store, stage, policy, day, version)
        if continued is not None:
            result = continued
        elif stage == "report":
            daily_report(store, day, delayed=delayed)
            result = "日报已生成"
        else:
            result = handlers[stage](store, policy, day, version)
        state, detail = describe(stage, result)
        from .resume_artifacts import produced
        produced(store, stage, result)
        store.finish_run(identity, state, detail)
    except ExecutionPaused as exc:
        store.finish_run(identity, 'paused', str(exc))
        store.report_phase = 'paused'
        daily_report(store, day)
    except AnalysisCancelled as exc:
        store.finish_run(identity, "cancelled", str(exc))
    except StageSkipped as exc:
        store.finish_run(identity, "skipped", str(exc))
        if getattr(exc, 'result', None):
            store.event('action_deferred', exc.result)
    except Exception as exc:
        # A stage failure is durable and does not prevent the independent daily report.
        logging.getLogger(__name__).exception("Operations stage failed: %s", stage)
        store.finish_run(identity, "failed", str(exc)[:1500])
        store.event("stage_error", {"day": day, "stage": stage, "run_id": identity, "error": str(exc)[:1500]})
