"""Development-only orchestration of the real stages, with durable batch evidence."""
import logging
import time

from fastapi import HTTPException

from plugins.operations.policy import local_day, now_iso

EXTERNAL = {"publish", "comment", "reply", "dm", "follow"}
DEPENDENCIES = {"organize": "research", "industry": "analytics", "topics": "organize", "content": "topics", "publish": "content"}


def requires_account(policy, steps, quick=False):
    return any(step['id'] in EXTERNAL and policy['modules'][step['module']] and
               (quick or step['id'] == 'publish' or policy['allowed'][step['id']]) for step in steps)


def unavailable(store, data, step, policy, *, coverage=False):
    task = step["id"]
    # A diagnostic report is always produced, even after a pause or failed prerequisite.
    if task == "report":
        return ""
    from plugins.operations.execution_pause import guard
    guard(store, web=requires_account(policy, data['steps'], data.get('mode') == 'quick'))
    version, current = store.policy()
    if version != data["version"]:
        return "规则版本已变更，本批次停止后续业务步骤"
    if not current["enabled"] or current["paused"]:
        return "运营计划未启用或已全局暂停"
    if local_day(current) != data["day"]:
        return "已跨越运营日期，请发起新的测试；未沿用昨日额度"
    if policy["deadline"] and data["day"] > policy["deadline"][:10]:
        return "运营目标已超过期限"
    if (not coverage or task in EXTERNAL) and not policy["modules"][step["module"]]:
        return "模块未启用；未修改现有计划"
    from plugins.operations.debug_authorization import allowed
    if task in EXTERNAL and not allowed(store, policy, task):
        return "该动作尚未授权"
    return dependency_reason(data, task)


def dependency_reason(data, task):
    dependency = DEPENDENCIES.get(task)
    prior = next((step for step in data['steps'] if step['id'] == dependency), None)
    value = prior.get('result') if prior else None
    result = value if isinstance(value, dict) else {}
    if task == 'publish' and result.get('content_id') and not result.get('ready'):
        missing = result.get('missing') or ['请检查草稿的发布条件']
        return '本轮草稿已生成，尚不可发布：' + '；'.join(missing)
    usable_partial = prior and dependency in {'research', 'organize', 'topics'} and prior['state'] == 'needs_attention' and result.get('usable', 0) > 0
    if prior and prior['state'] != 'completed' and not usable_partial:
        return f"依赖步骤「{prior['title']}」未完成，不使用旧产物替代本轮结果"
    if task == 'publish' and not data.get('content_id'):
        return '没有当前有效的已保存草稿，请先生成并检查内容，或勾选内容生产' if data.get('selected_tasks') is not None and not prior else '本轮没有保存可发布的内容版本'
    return ''


def run_step(store, data, step, policy, *, quick=False, coverage=False):
    from .operations_debug import invoke, update_record
    store.debug_step = step["id"]
    store.renew()
    if step.get('state') == 'paused':
        step.setdefault('attempts', []).append({k: v for k, v in step.items() if k != 'attempts'})
    step.update(state="running", started=now_iso(), detail="开始执行")
    update_record(store, data)
    run_id = store.start_run(data["day"], step["module"], data["id"] + ":" + step["id"] + (f":resume:{data['attempt']}" if data.get('attempt') else ""), data["version"])
    step["run_id"] = run_id
    store.event("pipeline_step_start", {"step": step, "version": data["version"], "content_id": data.get("content_id")})
    from plugins.operations.execution_pause import ExecutionPaused
    try:
        if step['id'] != 'report' and not getattr(store, 'start_preflight_done', False):
            from plugins.operations.execution_preflight import verify_for_start
            if requires_account(policy, data['steps'], quick):
                data['account_preflight'] = verify_for_start(store, data['version'])
            store.start_preflight_done = True
        reason = unavailable(store, data, step, policy, coverage=coverage)
        if reason:
            outcome = {"state": "skipped", "detail": reason, "duration_ms": 0}
        else:
            outcome = invoke(store, step["id"], policy, data["day"], data["version"], content_id=data.get("content_id"), quick=quick)
    except ExecutionPaused as exc:
        outcome = {'state': 'paused', 'detail': str(exc), 'result': exc.result, 'duration_ms': 0}
    step.update(**outcome, ended=now_iso())
    if step['state'] in {'completed', 'needs_attention'}:
        from plugins.operations.resume_artifacts import produced
        produced(store, step['id'], step.get('result'))
    if step["id"] == "content" and isinstance(step.get("result"), dict):
        data["content_id"] = step["result"].get("content_id")
    store.finish_run(run_id, step["state"], step["detail"])
    store.event("pipeline_step_end", {"step": step})
    update_record(store, data)


def run_pipeline(store, identity, task, version, *, mode="normal", external_actions='standing_policy', selected_tasks=None):
    from .operations_debug import TASKS, new_record, update_record
    current, policy = store.policy()
    if current != version:
        raise HTTPException(409, "规则已变更，请刷新调试页")
    day = local_day(policy)
    data = new_record(identity, task, "整链路测试", version, day)
    data.update(mode=mode, action_mode=external_actions, policy=policy, steps=[
        {"id": key, "title": title, "module": module, "state": "pending", "detail": "等待执行"}
        for key, (title, module) in TASKS.items() if selected_tasks is None or key in selected_tasks])
    if selected_tasks is not None:
        label = '快速实测' if mode == 'quick' else '详细执行'
        data.update(selected_tasks=selected_tasks, title=f'{label}（{len(selected_tasks)} 项）')
    store.put("debug_run", data, identity)
    store.manual_run_id = identity
    from .operations_selection import bind_existing_content
    bind_existing_content(store, data, policy)
    from .operations_authorization import create
    create(store, data)
    coverage = mode == "quick"
    previous_options = store.run_options
    store.run_options = {**(previous_options or {}), 'account_required': requires_account(policy, data['steps'], coverage)}
    if coverage:
        data["coverage"] = {"internal_modules": [step['id'] for step in data['steps']
                              if step['module'] not in {"comments", "dm", "follow", "publish", "report"}],
                             "external_actions": external_actions, 'max_per_kind': 1}
        update_record(store, data)
    store.event("pipeline_start", {"day": day, "version": version, "policy": policy, "mode": mode,
                                    "coverage": coverage})
    if coverage:
        store.run_options = {**store.run_options, "read_limit": 1, "query_limit": 1, "quick": True, "coverage": True,
                             'external_actions': external_actions}
    started = time.monotonic()
    from plugins.operations.batch_cancellation import BatchCancelled, mark
    try:
        try:
            execute_steps(store, data, policy, quick=mode == "quick", coverage=coverage)
        except BatchCancelled:
            mark(data, now_iso())
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
    finally:
        store.run_options = previous_options


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
    data["state"] = "paused" if any(s["state"] == "paused" for s in data["steps"]) else "failed" if counts["failed"] else "needs_attention" if counts["skipped"] or counts["needs_attention"] or errors else "completed"
    data["detail"] = (f"完成 {counts['completed']}/{len(data['steps'])} 步；失败 {counts['failed']}，"
                      f"跳过 {counts['skipped']}，待完善 {counts['needs_attention']}；异常事件 {errors}。"
                      f"外部动作已核对 {data['external_actions']['confirmed']}/{len(actions)} 条。"
                      "本次使用真实业务服务；跳过或未核对不代表全链路通过。")


def execute_steps(store, data, policy, *, quick=False, coverage=False):
    from .operations_debug import update_record
    from plugins.operations.execution_pause import load
    from plugins.operations.batch_cancellation import check
    for step in data['steps']:
        check(store)
        if data.get('attempt') and step['state'] not in {'paused', 'pending'} and step['id'] != 'report':
            continue
        run_step(store, data, step, policy, quick=quick, coverage=coverage)
        check(store)
        if step['state'] != 'paused':
            continue
        paused = load(store, data['id'])
        data.update(state='paused', revision=paused['revision'], detail=paused['error'])
        for later in data['steps']:
            if later['state'] == 'pending' and later['id'] != 'report':
                later.update(state='paused', detail='批次暂停：' + paused['error'])
        store.resume_attempt = data.get('attempt', 0)
        store.report_phase = 'paused'
        report = next((item for item in data['steps'] if item['id'] == 'report'), None)
        if report:
            run_step(store, data, report, policy, quick=quick, coverage=coverage)
        update_record(store, data)
        break
    from .operations_selection import diagnostic
    check(store)
    diagnostic(store, data)
