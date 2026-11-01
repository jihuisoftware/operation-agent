"""Expected no-op outcomes are distinct from successful work and execution errors."""


class StageSkipped(Exception):
    """A stage cannot produce an output under the current conditions."""


def describe(stage, result):
    if stage == 'research' and isinstance(result, dict):
        partial = result['failed'] or result['search_errors'] or result['not_attempted'] or result.get('reason')
        return ('needs_attention' if partial else 'completed'), result['detail']
    if stage == 'organize' and isinstance(result, dict):
        return ('needs_attention' if result['pending'] else 'completed'), result['detail']
    if stage in {"publish", "comments", "dm", "follow"}:
        receipts = result if isinstance(result, list) else [result]
        pending = [r for r in receipts if isinstance(r, dict) and (
            r.get("state") not in {"confirmed", "published"} or not r.get("evidence"))]
        if pending:
            return "needs_attention", "已提交待核对或结果未知，尚不能计为成功：" + str(pending)
    if stage == "content" and isinstance(result, dict) and result.get("content_id"):
        state = "completed" if result.get("ready") else "needs_attention"
        detail = f"草稿已保存，版本 {result['content_id']}；" + ("可供发布" if result.get("ready") else "待完善，尚不可发布")
        if result.get("missing"):
            detail += "；" + "；".join(result["missing"])
        if result.get("reason"):
            detail += "\n自动检查：" + str(result["reason"])
        return state, detail
    return "completed", str(result or "完成")
