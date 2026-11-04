"""Expected no-op outcomes are distinct from successful work and execution errors."""


class StageSkipped(Exception):
    """A stage cannot produce an output under the current conditions."""


def describe(stage, result):
    from .publication_status import normalize
    if stage == 'report' and isinstance(result, dict) and result.get('id'):
        return 'completed', '运营日报已保存'
    if stage == 'publish' and isinstance(result, dict):
        result = normalize(result)
    if stage == 'research' and isinstance(result, dict):
        partial = result['failed'] or result['search_errors'] or result['not_attempted'] or result.get('reason')
        return ('needs_attention' if partial else 'completed'), result['detail']
    if stage in {"analytics", "industry", "topics"} and isinstance(result, dict):
        return result["state"], result["detail"]
    if stage == 'organize' and isinstance(result, dict):
        return ('needs_attention' if result['pending'] else 'completed'), result['detail']
    if stage in {"publish", "comments", "dm", "follow"}:
        receipts = result if isinstance(result, list) else [result]
        pending = [r for r in receipts if isinstance(r, dict) and (
            r.get("state") not in {"confirmed", "published"} or not r.get("evidence"))]
        if pending:
            return "needs_attention", "已提交待核对或结果未知，尚不能计为成功：" + str(pending)
    if stage == "content" and isinstance(result, dict) and result.get("content_id"):
        detail = '草稿生成完成；' + ('已通过检查，可供发布' if result.get('ready') else '发布前仍需完善')
        if result.get("missing"):
            detail += "；" + "；".join(result["missing"])
        if result.get("reason"):
            detail += "\n自动检查：" + str(result["reason"])
        return 'completed', detail
    return "completed", str(result or "完成")
