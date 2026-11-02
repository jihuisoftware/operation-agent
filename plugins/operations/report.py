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
    with store.connection() as db:
        runs = [dict(r) for r in db.execute("SELECT * FROM runs WHERE day=? AND stage!='report' ORDER BY started", (day,))]
        actions = [dict(r) for r in db.execute("SELECT * FROM actions WHERE day=? ORDER BY created", (day,))]
        events = [dict(r) for r in db.execute("SELECT * FROM events WHERE json_extract(data,'$.day')=? ORDER BY id", (day,))]
    version, policy = store.policy()
    versions = sorted({r["version"] for r in runs} | {a["version"] for a in actions})
    history = {p["version"]: p["policy"] for p in store.objects("policy")}
    goals = [history[v]["goal"] for v in versions if v in history] or [policy["goal"]]
    sources = store.objects("source", day)
    referenced = {source_id for c in store.objects("content", day) for source_id in c.get("source_ids", [])}
    referenced.update(source_id for a in actions for source_id in json.loads(a["data"]).get("content", {}).get("source_ids", []))
    reused = [s for s in store.objects("source") if s["id"] in referenced and s.get("day") != day]
    lines = [f"# {day} 运营日报", "", f"目标：{'；'.join(dict.fromkeys(goals))}", f"生成时间：{now_iso()}",
             f"规则版本：{versions or [version]}", f"延迟补生成：{'是' if delayed else '否'}", "", "## 任务与执行", ""]
    if store.scope:
        lines.insert(2, f"业务：{store.scope['business_name']}；主题：{policy['topic']}；归属：{store.scope['business_id']} / {store.scope['id']}")
    lines.extend(f"- {r['stage']} · {r['state']} · {r['detail'] or '无补充说明'}" for r in runs)
    if not runs:
        lines.append("- 当日无执行记录；未据此推断任务已完成。")
    lines.extend(f"- 临时任务：{t['text']} · {t.get('state', 'pending')}" for t in store.objects("task", day))
    lines.extend(["", "## 信息来源", ""])
    lines.append(f"当日采集 {len(sources)} 条；本日内容引用既有资料 {len(reused)} 条。")
    for batch in store.objects('collection_run', day):
        lines.append(f"- 采集批次 {batch['started']}：读取 {batch['attempted']}，成功 {batch['succeeded']}，"
                     f"新资料 {batch['new']}，正文重复 {batch['duplicate_content']}，失败 {batch['failed']}，"
                     f"已采集跳过 {batch['already_read']}，未尝试 {batch['not_attempted']}；{batch['state']}")
    for source in sources + reused:
        summary = source.get("summary") or ("原文已记录" if source.get("text") else source.get("error") or "未取得正文")
        origin = "既有资料 · " if source.get("day") != day else ""
        lines.append(f"- [{source['title']}]({source['url']}) · {origin}{source['state']} · {summary}")
    for brief in store.objects("brief", day):
        lines.append("\n结论与待核实信息（模型整理，来源 ID 可查）：\n" + json.dumps(brief["result"], ensure_ascii=False))
    lines.extend(["", "## 资料整理", ""])
    for batch in store.objects('organization', day):
        lines.append('资料整理：' + batch['detail'])
    from .analysis_views import daily_lines
    lines.extend(daily_lines(store, day))
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
    for item in store.objects("inbox", day):
        if item.get("state") == "needs_review":
            lines.append(f"- 待处理 {item['kind']} · {item['id']} · {item.get('reason', '资料或授权依据不足')}")
    lines.extend(_consumption(store, day, runs, events, len(sources), len(actions)))
    lines.extend(["", "## 异常与明日建议", ""])
    lines.extend(f"- 核对动作 {a['id']}：{a['state']}，未经核对不重复执行。" for a in actions if a["state"] in {"unknown", "blocked", "failed", "submitted"})
    lines.extend(f"- {json.loads(e['data']).get('error', '')}" for e in events if e["kind"].endswith("error"))
    feedback = review(store, day)
    lines.append(f"- {feedback['reason']}")
    lines.extend(f"- {s['text']}；依据：{', '.join(s['metric_ids'])}。{s['caveat']}。" for s in feedback["suggestions"])
    lines.append("- 优先处理未完成任务，结合已收集来源继续验证选题；不自动扩大权限或额度。")
    markdown = "\n".join(lines) + "\n"
    data = {"day": day, "markdown": markdown, "delayed": delayed, "created": now_iso()}
    identity = store.put("report", data, identity)
    return {"id": identity, **data}


def _consumption(store, day, runs, events, source_count, action_count):
    seconds = sum(max(0, (datetime.fromisoformat(r["ended"]) - datetime.fromisoformat(r["started"])).total_seconds())
                  for r in runs if r["ended"])
    lines = ["", "## 数据与消耗", "", f"来源 {source_count} 条；外部动作记录 {action_count} 条。",
             f"模型调用 {sum(e['kind'] == 'model_call' for e in events)} 次；费用未知，不记为零。", f"已结束任务耗时合计 {seconds:.1f} 秒。"]
    for event in events:
        if event["kind"] == "usage":
            usage = json.loads(event["data"])
            lines.append(f"- 模型用量回执：{usage.get('tokens') or '缺失'}")
            if usage.get("cost") is not None:
                lines.append(f"- 已知单次费用：{usage['cost']}（{usage.get('currency') or '回执未提供币种'}）；其他缺失费用不作推测。")
    metrics = store.objects("metric", day)
    lines.extend(f"- {m['name']}：{m.get('value')}；口径：{m.get('definition', '未提供')}；来源：{m.get('source', '人工录入')}；统计时间：{m.get('observed_at', '未提供')}" for m in metrics)
    if not metrics:
        lines.append("- 未取得平台指标，不生成增长或转化率结论。")
    return lines
