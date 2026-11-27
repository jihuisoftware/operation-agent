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
    # if not isinstance(content.get("title"), str) or not isinstance(content.get("body"), str) or not 0 < len(content["title"]) <= 20 or not 0 < len(content["body"]) <= 900:
    #     raise ValueError("内容长度或格式不符合要求")
    source_ids = content.get('source_ids')
    from .writing_origin import original
    if not isinstance(source_ids, list) or (not source_ids and not original(content)) or any(not isinstance(identity, str) for identity in source_ids) or not set(source_ids) <= {s["id"] for s in sources}:
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
    from .review_scores import instruction as score_instruction
    instruction += score_instruction('text')
    if any(asset.get('cover_spec') for asset in assets):
        instruction += 'cover_spec是实际绘制的封面文案，也应核对是否含有无依据的数字、承诺或实测说法；不评价图片视觉质量。'
    if any(asset.get('visual_page') for asset in assets):
        instruction += 'visual_page是实际组图的所有可见文案，同样逐条核对事实、范围和来源；AI插画为概念示意，不是实拍或真实界面。'
    visual = None
    if any(asset.get('generated_magazine') for asset in assets):
        from .visual_review import for_assets
        visual = for_assets(store, content.get('asset_ids', []))
    data = inputs.checked(store, 'content_check', {"policy": inputs.policy(policy),
         "content": {**inputs.fields(content, ('id', 'title', 'body', 'source_ids', 'asset_ids')), 'selected_topic': inputs.selected_topic(content.get('selected_topic'))},
         "sources": review_sources(content, sources), "assets": inputs.assets(assets), "history": inputs.history(history),
         **({"visual_review": visual} if visual else {})})
    signature = hashlib.sha256(encoded({'instruction': instruction, 'data': data, 'version': version}).encode()).hexdigest()
    cached = next((row for row in store.objects('check', day) if row.get('input_signature') == signature and row['result'].get('pass') is True), None)
    from .review_policy import get as review_settings
    from .review_scores import score
    if cached and (review_settings(store)['mode'] != 'score' or score(cached['result'], 'text') is not None):
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
    if visual:
        result['visual_review'] = visual
        if visual.get('pass') is not True:
            result['pass'] = False
            result['reason'] = visual.get('reason') or '组图视觉检查未通过'
            result['issues'] = [*issues, {'code': 'visual', 'message': result['reason']}]

    store.put("check", {"day": day, "content_id": content.get("id", digest), "version": version, "automatic": True, "input_signature": signature, "result": result})
    return result


def produce_content(store, policy, day, version):
    from .review_policy import get as review_settings
    review_revision = review_settings(store)['revision']
    from .topics import production_topic
    from .industry import production_context, preferred_sources
    analysis = production_context(store, policy, day)
    topic = production_topic(store, policy, day)
    preferred = topic.get('source_ids', []) if topic else preferred_sources(analysis)
    sources, evidence = production_evidence(store, policy, day, preferred)
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
    from .content_recovery import fingerprint, pending
    data = inputs.checked(store, 'content', {"analysis": inputs.analysis(analysis, evidence), "policy": inputs.policy(policy), "sources": evidence,
         "assets": inputs.assets([asset for asset in assets if not any(asset.get(key) for key in ('generated_typography', 'generated_magazine', 'generated_visual_art', 'designer_background', 'designer_cover'))]), "tasks": inputs.tasks(store.objects("task", day)),
         "image_mode": policy.get("image_mode", "magazine"), "selected_topic": inputs.selected_topic(topic), "recent_content": inputs.history(public_history(store, policy, day)), "performance_review": []})
    from . import content_writer
    from .automatic_review import finish_production
    base = fingerprint(data, version, analysis)
    signature = content_writer.variant_key(store, base)
    draft = pending(store, day, signature)
    mode = getattr(store, 'draft_mode', 'reuse')
    if draft:
        validate_content(draft, sources, assets)
        store.event('content_reused', {'content_id': draft['id'], 'source_ids': draft['source_ids'], 'revision_index': draft.get('revision_index', 0)})
        store.progress('复用已保存图文，继续尚未完成的检查或修订', {'content_id': draft['id']})
        return {**finish_production(store, policy, day, version, draft, sources), 'writing_state': 'reused', 'draft_mode': mode}
    prior = pending(store, day, base) if signature != base else None
    content, writing_state, outline_id = content_writer.write(store, policy, day, version, analysis, data, sources, signature, prior)
    content["analysis_context"] = analysis
    content["selected_topic"] = topic
    if production_topic(store, policy, day) != topic:
        raise StageSkipped('写稿期间选题已变化，请按当前选题重新生成')
    current_sources, current_evidence = production_evidence(store, policy, day, preferred)
    current_ids = {row['id']: row['organization_id'] for row in current_evidence}
    if any(current_ids.get(row['id']) != row['organization_id'] for row in evidence if row['id'] in content['source_ids']):
        raise StageSkipped('写稿期间引用资料已变化，请按最新资料重新生成')
    validate_content(content, current_sources, [a for a in store.objects('asset') if a.get('authorized') and not a.get('revoked')])
    content['visual_required'] = policy.get('image_mode', 'magazine') == 'magazine'
    content['designer_required'] = not content['visual_required']
    content['asset_ids'] = []
    cited = [row for row in source_evidence if row['id'] in content['source_ids']]
    content['organization_ids'] = [row['organization_id'] for row in cited]
    content['organized_evidence'] = cited
    draft = {**content, "day": day, "version": version, "ready": False, "review_pending": True,
             "production_input": signature, "writing_outline_id": outline_id, "draft_mode":mode, "state": "needs_review", "created": now_iso(),
             "quality": {"pass": False, "reason": "草稿已保存，等待自动质量检查"},
             **({'debug_id': store.debug_id} if getattr(store, 'debug_id', None) else {})}
    draft['review_policy_revision'] = review_revision
    if getattr(store, 'daily_writing', False):
        from .daily_tasks import manuscripts
        completed, _ = manuscripts(store, day)
        if len(completed) >= policy['draft_goal']:
            raise StageSkipped('今日新稿目标已完成')
    draft['id'] = store.put('content', draft)
    return {**finish_production(store, policy, day, version, draft, sources), 'writing_state': writing_state, 'draft_mode': mode}


def public_history(store, policy, day):
    from .content_history import published
    return published(store, policy, day)
