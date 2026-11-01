"""Content production and quality checks, independent of external publishing."""
import hashlib
import json
from .model import generate
from .policy import now_iso
from .organization import production_evidence
from .outcomes import StageSkipped


def content_digest(content):
    return hashlib.sha256(json.dumps([content["title"], content["body"]], ensure_ascii=False).encode()).hexdigest()


def validate_content(content, sources, assets, *, require_assets=False):
    if not isinstance(content.get("title"), str) or not isinstance(content.get("body"), str) or not 0 < len(content["title"]) <= 20 or not 0 < len(content["body"]) <= 900:
        raise ValueError("内容长度或格式不符合要求")
    if not content.get("source_ids") or not set(content["source_ids"]) <= {s["id"] for s in sources}:
        raise ValueError("内容引用来源不匹配")
    ids = content.get("asset_ids", [])
    if not isinstance(ids, list) or not set(ids) <= {a["id"] for a in assets}:
        raise ValueError("内容引用素材不匹配")
    if require_assets and not ids:
        raise ValueError("缺少获授权图片，请完善内容版本后发布")


def check_content(store, policy, day, version, content, sources, *, publishing=False):
    from .industry import check_public_context
    check_public_context(store, content, policy, day)
    digest = content_digest(content)
    from .analytics import valid
    history = [c for c in store.objects("content") if not c.get("analysis_context") or valid(store, c["analysis_context"], policy, day)]
    if publishing:
        with store.connection() as db:
            history = [json.loads(row[0])["content"] for row in db.execute(
                "SELECT data FROM actions WHERE kind='publish' AND state IN ('published','confirmed') ORDER BY created DESC")]
    history = [c for c in history if not c.get("analysis_context") or valid(store, c["analysis_context"], policy, day)]
    history = [c for c in history if c.get("id") not in {digest, content.get("id")} and content_digest(c) != digest][:15]
    assets = [a for a in store.objects("asset") if a["id"] in content.get("asset_ids", [])]
    result = generate(store, policy, day,
        '核对文本是否符合主题、受众、风格，事实是否有来源，是否复制原文或编造经历，是否重复提供的历史内容。'
        'assets 是素材元数据，只核对引用与授权，不宣称已看过图片或完成视觉一致性检查。'
        '返回 {"pass":true或false,"reason":"具体依据"}，不确定时 pass 为 false。此为自动检查，不是人工审核。',
        {"policy": policy, "content": content, "sources": sources, "assets": assets, "history": history})
    result.update(scope="text_and_asset_metadata", visual_review="not_performed")
    store.put("check", {"day": day, "content_id": content.get("id", digest), "version": version, "automatic": True, "result": result})
    return result


def produce_content(store, policy, day, version):
    from .topics import production_topic
    from .industry import production_context, preferred_sources
    analysis = production_context(store, policy, day)
    topic = production_topic(store, policy, day)
    sources, evidence = production_evidence(store, policy, day, topic.get('source_ids', []) if topic else preferred_sources(analysis))
    if topic and topic.get("source_ids"):
        sources = [source for source in sources if source["id"] in topic["source_ids"]]
        evidence = [row for row in evidence if row['id'] in topic['source_ids']]
    if not sources:
        raise StageSkipped("缺少可追溯来源，暂不生成内容")
    assets = [a for a in store.objects("asset") if a.get("authorized") and not a.get("revoked")]
    content = generate(store, policy, day,
        '生成小红书图文草稿，返回 {"title":"", "body":"", "asset_ids":[], "source_ids":[], "reason":""}。'
        '标题不超过20字，正文不超过900字。只能使用提供的来源和素材，缺少图片时保留文本草稿。'
        'selected_topic 不为空时必须围绕指定选题写作，不得另换题目；标题可精炼但保持原主题。'
        'analysis 非空时优先参考其可公开结论与指标，保留适用范围；不使用内部经营数据。'
        '主要参考 sources 中已整理的摘要、分类和事实陈述；观点明确归属，待核实信息不得写成确定事实。'
        '不适合生产时返回空标题和原因。不要执行发布。',
        {"analysis": analysis, "policy": policy, "sources": evidence, "assets": assets, "tasks": store.objects("task", day),
         "selected_topic": topic, "recent_content": public_history(store, policy, day), "performance_review": []})
    if not content.get("title"):
        raise StageSkipped(content.get("reason", "无合适选题"))
    content["analysis_context"] = analysis
    content["selected_topic"] = topic
    validate_content(content, sources, assets)
    cited = [row for row in evidence if row['id'] in content['source_ids']]
    content['organization_ids'] = [row['organization_id'] for row in cited]
    content['organized_evidence'] = cited
    quality = check_content(store, policy, day, version, content, sources)
    ready = quality.get("pass") is True and bool(content.get("asset_ids"))
    missing = ([] if content.get("asset_ids") else ["缺少获授权图片"]) + ([] if quality.get("pass") is True else ["自动质量检查未通过"])
    identity = store.put("content", {**content, "day": day, "version": version, "ready": ready,
                                    "state": "ready" if ready else "needs_material" if not content.get("asset_ids") else "needs_review",
                                    "quality": quality, "selected_topic": topic, "created": now_iso()})
    return {"content_id": identity, "ready": ready, "missing": missing, "reason": quality.get("reason")}


def public_history(store, policy, day):
    from .analytics import valid
    enabled = any(policy['modules'].get(k) for k in ('analytics', 'industry'))
    return [c for c in store.objects('content') if not c.get('analysis_context') or (enabled and valid(store, c['analysis_context'], policy, day))][:15]
