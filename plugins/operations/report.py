"""Immutable, timestamped daily snapshots built exclusively from durable records."""
import json
from datetime import datetime
from .feedback import review
from .policy import now_iso


def daily_report(store, day, delayed=False):
    existing = store.objects("report", day)
    if existing:
        return existing[0]
    with store.connection() as db:
        runs = [dict(r) for r in db.execute("SELECT * FROM runs WHERE day=? AND stage!='report' ORDER BY started", (day,))]
        actions = [dict(r) for r in db.execute("SELECT * FROM actions WHERE day=? ORDER BY created", (day,))]
        events = [dict(r) for r in db.execute("SELECT * FROM events WHERE json_extract(data,'$.day')=? ORDER BY id", (day,))]
    version, policy = store.policy()
    versions = sorted({r["version"] for r in runs} | {a["version"] for a in actions})
    history = {p["version"]: p["policy"] for p in store.objects("policy")}
    goals = [history[v]["goal"] for v in versions if v in history] or [policy["goal"]]
    sources = store.objects("source", day)
    lines = [f"# {day} 运营日报", "", f"目标：{'；'.join(dict.fromkeys(goals))}", f"生成时间：{now_iso()}",
             f"规则版本：{versions or [version]}", f"延迟补生成：{'是' if delayed else '否'}", "", "## 任务与执行", ""]
    lines.extend(f"- {r['stage']} · {r['state']} · {r['detail'] or '无补充说明'}" for r in runs)
    if not runs:
        lines.append("- 当日无执行记录；未据此推断任务已完成。")
    lines.extend(f"- 临时任务：{t['text']} · {t.get('state', 'pending')}" for t in store.objects("task", day))
    lines.extend(["", "## 信息来源", ""])
    for source in sources:
        summary = source.get("summary") or ("原文已记录" if source.get("text") else source.get("error") or "未取得正文")
        lines.append(f"- [{source['title']}]({source['url']}) · {source['state']} · {summary}")
    for brief in store.objects("brief", day):
        lines.append("\n结论与待核实信息（模型整理，来源 ID 可查）：\n" + json.dumps(brief["result"], ensure_ascii=False))
    lines.extend(["", "## 发布与互动", ""])
    for action in actions:
        result = json.loads(action["result"])
        lines.append(f"- {action['kind']} · {action['state']} · {action['target']} · {action['created']} · "
                     f"{result.get('evidence') or result.get('error') or '暂无结果证据'} · {result.get('url', '')}")
    completed = sum(a["state"] in {"published", "confirmed"} for a in actions)
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
    identity = store.put("report", data, f"report:{day}")
    return {"id": identity, **data}


def _consumption(store, day, runs, events, source_count, action_count):
    seconds = sum(max(0, (datetime.fromisoformat(r["ended"]) - datetime.fromisoformat(r["started"])).total_seconds())
                  for r in runs if r["ended"] and r["state"] != "migrated")
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
