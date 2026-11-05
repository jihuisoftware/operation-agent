"""Content production and quality checks, independent of external publishing."""
import hashlib
import json
from .model import generate
from .policy import now_iso
from .organization import production_evidence
from .outcomes import StageSkipped
from . import model_inputs as inputs
from .store import encoded


def content_digest(content):
    return hashlib.sha256(json.dumps([content["title"], content["body"]], ensure_ascii=False).encode()).hexdigest()


def validate_content(content, sources, assets, *, require_assets=False):
    if not isinstance(content.get("title"), str) or not isinstance(content.get("body"), str) or not 0 < len(content["title"]) <= 20 or not 0 < len(content["body"]) <= 900:
        raise ValueError("内容长度或格式不符合要求")
    source_ids = content.get('source_ids')
    if not isinstance(source_ids, list) or not source_ids or any(not isinstance(identity, str) for identity in source_ids) or not set(source_ids) <= {s["id"] for s in sources}:
        raise ValueError("内容引用来源不匹配")
    ids = content.get("asset_ids", [])
    if not isinstance(ids, list) or not set(ids) <= {a["id"] for a in assets}:
        raise ValueError("内容引用素材不匹配")
    if require_assets and not ids:
        raise ValueError("缺少获授权图片，请完善内容版本后发布")


def check_content(store, policy, day, version, content, sources):
    from .industry import check_public_context
    check_public_context(store, content, policy, day)
    digest = content_digest(content)
    history = public_history(store, policy, day)
    assets = [a for a in store.objects("asset") if a["id"] in content.get("asset_ids", [])]
    from .content_evidence import review_sources
    instruction = (
        '核对文本是否符合主题、受众、风格，事实是否有来源，是否复制原文或编造经历，是否重复提供的历史内容。'
        'history只包含实际已发布文章，未发布草稿与本稿修改版本不构成重复发布；仅话题相同不算重复。'
        'assets 是素材元数据，只核对引用与授权，不宣称已看过图片或完成视觉一致性检查。'
        'generated_typography=true表示系统制作的标题文字封面，不是现场照片；不要求正文声明封面引用关系，不另加此类阻断条件。'
        '日期严格区分：day/collected_at是采集时间，不是原文发布时间；分析窗口不是来源发布日期范围。'
        'history.day是内容生成日期，publication_recorded_at是提交记录时间，不代表平台发布时间。'
        '返回 {"pass":true或false,"reason":"具体依据","issues":[{"code":"unsupported_fact/date_scope/duplicate/asset/other",'
        '"quote":"稿件中有问题的原句","source_ids":[],"message":"原因","suggestion":"具体修改建议"}]}。通过时issues为空。'
        '不确定时pass为false；这是自动检查，不是人工审核。source_truncated表示抓取缺失，excerpted表示本轮节选；'
        '不能把未提供的原文当作已经核对或断言原文没有相关内容，证据不足时指出具体需补证的句子。')
    data = inputs.checked(store, 'content_check', {"policy": inputs.policy(policy),
         "content": {**inputs.fields(content, ('id', 'title', 'body', 'source_ids', 'asset_ids')), 'selected_topic': inputs.selected_topic(content.get('selected_topic'))},
         "sources": review_sources(content, sources), "assets": inputs.assets(assets), "history": inputs.history(history)})
    signature = hashlib.sha256(encoded({'instruction': instruction, 'data': data, 'version': version}).encode()).hexdigest()
    cached = next((row for row in store.objects('check', day) if row.get('input_signature') == signature and row['result'].get('pass') is True), None)
    if cached:
        store.event('content_check_reused', {'content_id': content.get('id'), 'check_id': cached['id']})
        return cached['result']
    result = generate(store, policy, day, instruction, data)
    from .model_errors import ModelOutputError
    if type(result.get('pass')) is not bool:
        raise ModelOutputError('质量检查没有返回明确的通过或不通过结论')
    issues = result.get('issues') or []
    if not isinstance(issues, list) or any(not isinstance(issue, dict) for issue in issues):
        raise ModelOutputError('质量检查的问题列表格式无效，保留草稿等待复检')
    if issues:
        result['pass'] = False
    result.update(scope="text_and_asset_metadata", visual_review="not_performed")
    store.put("check", {"day": day, "content_id": content.get("id", digest), "version": version, "automatic": True, "input_signature": signature, "result": result})
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
    source_evidence = evidence
    evidence = inputs.evidence(evidence, topic.get('source_ids', []) if topic else ())
    included = {row['id'] for row in evidence}
    sources = [row for row in sources if row['id'] in included]
    assets = [a for a in store.objects("asset") if a.get("authorized") and not a.get("revoked")]
    from .content_recovery import fingerprint, pending, review
    data = inputs.checked(store, 'content', {"analysis": inputs.analysis(analysis, evidence), "policy": inputs.policy(policy), "sources": evidence,
         "assets": inputs.assets([asset for asset in assets if not asset.get('generated_typography')]), "tasks": inputs.tasks(store.objects("task", day)),
         "selected_topic": inputs.selected_topic(topic), "recent_content": inputs.history(public_history(store, policy, day)), "performance_review": []})
    signature = fingerprint(data, version, analysis)
    draft = pending(store, day, signature)
    if draft:
        validate_content(draft, sources, assets)
        store.event('content_reused', {'content_id': draft['id'], 'source_ids': draft['source_ids'], 'revision_index': draft.get('revision_index', 0)})
        store.progress('复用已保存图文，继续尚未完成的检查或修订', {'content_id': draft['id']})
        return review(store, policy, day, version, draft, sources)
    content = generate(store, policy, day,
        '生成小红书图文草稿，返回 {"title":"", "body":"", "asset_ids":[], "source_ids":[], "reason":""}。'
        '标题不超过20字，正文不超过900字。只能使用提供的来源和素材，缺少图片时保留文本草稿。'
        'selected_topic 不为空时必须围绕指定选题写作，不得另换题目；标题可精炼但保持原主题。'
        'analysis 非空时优先参考其可公开结论与指标，保留适用范围；不使用内部经营数据。'
        'analysis_origin=historical 的结论属于 origin_window 的历史证据分析，不得改称今日趋势。'
        '主要参考 sources 中已整理的摘要、分类和事实陈述；观点明确归属，待核实信息不得写成确定事实。'
        '采集日期、统计窗口不是文章发布时间；无法确认发布时间时使用“根据已采集的公开资料整理”，不要编造“本周发布”等时间结论。'
        '不适合生产时返回空标题和原因。不要执行发布。coverage 标明本轮提供的分析范围，不外推未提供的资料。',
        data)
    if not content.get("title"):
        raise StageSkipped(content.get("reason", "无合适选题"))
    content = inputs.fields(content, ('title', 'body', 'source_ids', 'asset_ids', 'reason'))
    content["analysis_context"] = analysis
    content["selected_topic"] = topic
    validate_content(content, sources, assets)
    from .content_cover import ensure_cover
    content = ensure_cover(store, content)
    cited = [row for row in source_evidence if row['id'] in content['source_ids']]
    content['organization_ids'] = [row['organization_id'] for row in cited]
    content['organized_evidence'] = cited
    draft = {**content, "day": day, "version": version, "ready": False, "review_pending": True,
             "production_input": signature, "state": "needs_review", "created": now_iso(),
             "quality": {"pass": False, "reason": "草稿已保存，等待自动质量检查"},
             **({'debug_id': store.debug_id} if getattr(store, 'debug_id', None) else {})}
    draft['id'] = store.put('content', draft)
    return review(store, policy, day, version, draft, sources)


def public_history(store, policy, day):
    from .content_history import published
    return published(store, policy, day)
