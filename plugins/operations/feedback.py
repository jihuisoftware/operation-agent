"""Evidence-bound next-day suggestions; never edits standing authorization."""
from collections import defaultdict


def review(store, day, *, scope=None):
    groups = defaultdict(list)
    for metric in scope.objects("metric") if scope else store.objects("metric", day):
        if type(metric.get("value")) in {int, float} and metric.get("content_id"):
            groups[(metric["name"], metric.get("definition", ""))].append(metric)
    suggestions = []
    for (name, definition), metrics in groups.items():
        if len(metrics) < 2:
            continue
        ranked = sorted(metrics, key=lambda m: m["value"], reverse=True)
        suggestions.append({"text": f"同口径指标 {name}（{definition}）中，内容 {ranked[0]['content_id']} 排在前列；复查其选题是否仍符合目标。",
                            "metric_ids": [m["id"] for m in ranked], "content_id": ranked[0]["content_id"],
                            "caveat": "观察数据不代表因果，不调整权限或额度"})
    result = {"day": day, "suggestions": suggestions, "reason": "同口径有数值的内容指标排序" if suggestions else "可比较数据不足，不推断优劣"}
    store.put("review", result, f"review:{day}" + (f":manual:{scope.batch}" if scope and scope.batch else ""))
    return result
