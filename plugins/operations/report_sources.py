"""Source accounting and links for a daily or batch-scoped report."""
import json


def source_lines(scope, actions):
    sources = scope.objects('source')
    collection_runs = scope.objects('collection_run')
    new_sources = [source for source in sources if source.get("is_new", True)]
    duplicate_sources = [source for source in sources if not source.get("is_new", True) and source.get("text")]
    contents = scope.objects("content")
    referenced = {source_id for c in contents for source_id in c.get("source_ids", [])}
    for event in scope.events:
        if event['kind'] == 'content_reused':
            referenced.update(json.loads(event['data']).get('source_ids', []))
    referenced.update(source_id for a in actions for source_id in json.loads(a["data"]).get("content", {}).get("source_ids", []))
    collected_ids = {source["id"] for source in sources}
    reused = [s for s in scope.store.objects("source") if s["id"] in referenced and s["id"] not in collected_ids]
    lines = []
    lines.extend(["", "## 信息来源", ""])
    lines.append(f"当日采集 {len(sources)} 条；本日内容引用既有资料 {len(reused)} 条。今日新增来源 {len(new_sources)} 条；历史资料复用 {len(reused)} 条。")
    if duplicate_sources:
        lines.append(f"今日读取但与已有内容重复 {len(duplicate_sources)} 条，未计入今日新增来源。")
    for batch in collection_runs:
        lines.append(f"- 采集批次 {batch['started']}：读取 {batch['attempted']}，成功 {batch['succeeded']}，"
                     f"新资料 {batch['new']}，正文重复 {batch['duplicate_content']}，失败 {batch['failed']}，"
                     f"已采集跳过 {batch['already_read']}，未尝试 {batch['not_attempted']}；{batch['state']}")
    if new_sources:
        lines.append("\n### 今日新增来源")
        for source in new_sources:
            summary = source.get("summary") or ("原文已记录" if source.get("text") else source.get("error") or "未取得正文")
            lines.append(f"- [{source['title']}]({source['url']}) · {source['state']} · {summary}")
    if reused:
        lines.append("\n### 历史资料复用")
        for source in reused:
            summary = source.get("summary") or ("原文已记录" if source.get("text") else source.get("error") or "未取得正文")
            lines.append(f"- [{source['title']}]({source['url']}) · 既有资料 · {source['state']} · {summary}")
    unavailable = [source for source in sources if source.get('state') == 'unavailable']
    if unavailable:
        lines.append('\n### 读取失败的来源')
        lines.extend(f"- [{source['title']}]({source['url']}) · {source.get('error') or '未取得正文'}" for source in unavailable)
    return lines, len(sources)
