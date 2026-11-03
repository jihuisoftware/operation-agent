"""Immutable, timestamped daily snapshots built exclusively from durable records."""
import json
from datetime import datetime
from .feedback import review
from .policy import now_iso
from .publication_status import complete, display


def daily_report(store, day, delayed=False):
    identity = f"report:{day}" + (f":manual:{store.manual_run_id}" if store.manual_run_id else "")
    existing = [r for r in store.objects("report", day) if r["id"] == identity]
    if existing:
        return existing[0]
    from .workspace_execution import check_running
    check_running(store)
    run_scope = store.manual_run_id
    is_debug_scope = isinstance(run_scope, str) and run_scope.startswith("debug:")
    from .run_scope import ReportScope
    scope = ReportScope(store, day)
    runs, actions, events = scope.runs, scope.actions, scope.events
    version, policy = store.policy()
    versions = sorted({r["version"] for r in runs} | {a["version"] for a in actions})
    history = {p["version"]: p["policy"] for p in store.objects("policy")}
    goals = [history[v]["goal"] for v in versions if v in history] or [policy["goal"]]
    from .report_sources import source_lines
    source_sections, source_count = source_lines(scope, actions)
    coverage = getattr(store, "run_options", None) or {}
    quick_coverage = bool(coverage.get("coverage") or coverage.get("quick"))
    external_stages = {"publish", "comments", "dm", "follow"}
    execution_runs = [run for run in runs if not quick_coverage or run["stage"] not in external_stages]
    preflight_runs = [run for run in runs if quick_coverage and run["stage"] in external_stages]
    lines = [f"# {day} 运营日报", "", f"目标：{'；'.join(dict.fromkeys(goals))}", f"生成时间：{now_iso()}",
             f"规则版本：{versions or [version]}", f"延迟补生成：{'是' if delayed else '否'}", "", "## 任务与执行", ""]
    if store.scope:
        lines.insert(2, f"业务：{store.scope['business_name']}；主题：{policy['topic']}；归属：{store.scope['business_id']} / {store.scope['id']}")
    if quick_coverage:
        lines.extend(["## 快速模式限制", "", "本次为快速模式：仅抽样 1 条来源、外部动作不执行。", ""])
    lines.extend(f"- {r['stage']} · {r['state']} · {r['detail'] or '无补充说明'}" for r in execution_runs)
    if preflight_runs:
        lines.extend(["", "## 预检查结果", ""])
        lines.extend(f"- {r['stage']} · {r['state']} · {r['detail'] or '无补充说明'}" for r in preflight_runs)
    if not execution_runs and not preflight_runs:
        lines.append("- 当日无执行记录；未据此推断任务已完成。")
    lines.extend(f"- 临时任务：{t['text']} · {t.get('state', 'pending')}" for t in scope.objects("task"))
    lines.extend(source_sections)
    for brief in scope.objects("brief"):
        lines.append("\n结论与待核实信息（模型整理，来源 ID 可查）：\n" + json.dumps(brief["result"], ensure_ascii=False))
    lines.extend(["", "## 资料整理", ""])
    organization_batches = scope.objects('organization')
    for batch in organization_batches:
        lines.append('资料整理：' + batch['detail'])
        if batch.get('pending'):
            lines.append(f"- 仍有 {batch['pending']} 条资料待整理；下次执行资料整理会从未完成批次继续。")
    from .analysis_views import daily_lines
    lines.extend(daily_lines(scope))
    industry_reports = scope.objects('industry_report')
    for report in industry_reports:
        if report.get('pending'):
            lines.append(f"- 行业分析仍有 {report['pending']} 项证据待分析；下次执行行业分析会继续分批补齐。")
    lines.extend(["", "## 发布与互动", ""])
    for action in actions:
        result = json.loads(action["result"])
        target = json.loads(action["data"])["target"]
        lines.append(f"- {action['kind']} · {action['state']} · {target} · {action['created']} · "
                     f"{result.get('manual_verification', {}).get('evidence') or result.get('evidence') or result.get('error') or '暂无结果证据'} · {result.get('url', '')}")
        if result.get('manual_verification'):
            human = result['manual_verification']
            lines.append(f"  人工结论：{human['state']}；{human['actor']}；{human['at']}；自动核对事实保留如下。")
        if action['kind'] == 'publish':
            status = display(action)
            lines.append(f"  执行：{status['execution']}；平台审核：{status['platform']}；内容核对：{status['content']}。")
    completed = sum(complete(a) for a in actions)
    lines.append(f"\n已核对成功 {completed} 次；待审核或结果不明不计入成功。")
    for item in scope.objects("inbox"):
        if item.get("state") == "needs_review":
            lines.append(f"- 待处理 {item['kind']} · {item['id']} · {item.get('reason', '资料或授权依据不足')}")
    lines.extend(_consumption(scope, source_count, len(actions)))
    lines.extend(["", "## 异常与明日建议", ""])
    lines.extend(f"- 核对动作 {a['id']}：{a['state']}，未经核对不重复执行。" for a in actions if a["state"] in {"unknown", "blocked", "failed", "submitted"})
    lines.extend(f"- {json.loads(e['data']).get('error', '')}" for e in events if e["kind"].endswith("error"))
    feedback = review(store, day, scope=scope)
    lines.append(f"- {feedback['reason']}")
    lines.extend(f"- {s['text']}；依据：{', '.join(s['metric_ids'])}。{s['caveat']}。" for s in feedback["suggestions"])
    lines.append("- 优先处理未完成任务，结合已收集来源继续验证选题；不自动扩大权限或额度。")
    markdown = "\n".join(lines) + "\n"
    data = {"day": day, "markdown": markdown, "delayed": delayed, "created": now_iso(),
            "debug_id": run_scope if is_debug_scope else None,
            "coverage": {"quick": quick_coverage, "read_limit": coverage.get("read_limit"),
                         "query_limit": coverage.get("query_limit"),
                         "external_actions": "readiness_only" if quick_coverage else "enabled"}}
    identity = store.put("report", data, identity)
    return {"id": identity, **data}


def _consumption(scope, source_count, action_count):
    from .run_scope import call_count
    runs, events = scope.runs, scope.events
    seconds = sum(max(0, (datetime.fromisoformat(r["ended"]) - datetime.fromisoformat(r["started"])).total_seconds())
                  for r in runs if r["ended"])
    calls = call_count(events)
    lines = ["", "## 数据与消耗", "", f"来源 {source_count} 条；外部动作记录 {action_count} 条。",
             f"模型调用 {calls} 次；费用未知，不记为零。", f"已结束任务耗时合计 {seconds:.1f} 秒。"]
    for event in events:
        if event["kind"] == "usage":
            usage = json.loads(event["data"])
            lines.append(f"- 模型用量回执：{usage.get('tokens') or '缺失'}")
            if usage.get("cost") is not None:
                lines.append(f"- 已知单次费用：{usage['cost']}（{usage.get('currency') or '回执未提供币种'}）；其他缺失费用不作推测。")
    metrics = scope.objects("metric")
    lines.extend(f"- {m['name']}：{m.get('value')}；口径：{m.get('definition', '未提供')}；来源：{m.get('source', '人工录入')}；统计时间：{m.get('observed_at', '未提供')}" for m in metrics)
    if not metrics:
        lines.append("- 未取得平台指标，不生成增长或转化率结论。")
    return lines
