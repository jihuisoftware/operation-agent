"""Evidence-bound editorial planning, checkpointed drafting and targeted text revision."""

import hashlib
import time

from . import model_inputs as inputs
from .collection_ledger import load
from .content_evidence import review_sources
from .model import generate
from .model_errors import ModelOutputError
from .outcomes import StageSkipped
from .store import encoded
from .writing_agent import complete

PLAN = (
    "你是小红书责任编辑。先策划，不写正文。围绕 selected_topic 回答目标读者的一个具体问题。"
    "优先选择资料中有细节、能解释怎样做或何时适用的角度。区分事实、引述、作者推论和未知事项。"
    "若提供 prior_article，找一个确有资料支持的不同角度。不要替换选题，也不要换同义词冒充新角度。"
    '返回 {"question":"读者的问题","angle":"切入点","points":[{"claim":"关键事实及其限定",'
    '"source_ids":["实际来源ID"],"use":"可借鉴的做法或案例","limit":"适用边界"}]}，选1至4个有依据的要点。'
    '资料不足则返回 {"gap":"具体缺少什么证据","points":[]}。'
)
DRAFT = (
    "你是中文实用文章编辑。结合提纲和原文节选写一篇可独立阅读的小红书稿件。开头给出读者会遇到的"
    "具体情形或判断；用来源中的案例解释做法、原因及适用条件。证据只有转述时标出归属。建议用“可以先试”引出，不得把建议的顺序、因果、人物身份写成来源陈述。"
    "只写透一个决策，优先使用最相关的一至两个例子，可以舍弃其他提纲要点。正文目标350至550个字符（英文逐字母计数），避免反复罗列来源局限。读者应能照着试一步或判断何时不该用。删除空泛开场、宣传口号和套模板的总结。"
)
REVISE = (
    "你是本稿的文字编辑。针对 review 指出的原句逐处修订，核对原文节选；缺证据的论断删除或限定。"
    "保留已核实内容、有效的写作角度和原素材。保留原稿的事实与推论边界。"
)
CONTRACT = (
    "只使用本轮给出的来源、已授权素材和可公开分析。不编造亲历、数字、日期或效果。采集日不是发表日，"
    "历史分析注明时间窗口；区分作者发文日期与转述报道日期。证据为节选时用“现有资料无法确认”，不声称全文没有讨论某点。引用ID仅放在source_ids，正文用来源名称。标题最多20字，正文最多900字。仅返回 JSON 对象"
    '{"title":"","body":"","source_ids":[],"asset_ids":[],"reason":""}。无法成稿时返回空标题和具体原因。'
)


def turn(store, policy, day, stage, instruction, data, validate):
    from .policy import now_iso

    data = inputs.checked(store, stage, data)
    store.progress("正在" + LABELS[stage])
    started = time.monotonic()
    state = "failed"
    try:
        result = generate(store, policy, day, instruction, data, completion=complete)
        result = validate(result)
        state = "completed"
        return result
    except Exception as exc:
        if isinstance(exc, StageSkipped):
            state = "skipped"
        if isinstance(exc, (ValueError, RuntimeError, StageSkipped)):
            exc.args = (f"{LABELS[stage]}：{exc}",)
        store.event("writing_error", {"stage": stage, "error": str(exc), "day": day})
        raise
    finally:
        store.event(
            "writing_turn",
            {
                "stage": stage,
                "state": state,
                "day": day,
                "ended": now_iso(),
                "duration_ms": round((time.monotonic() - started) * 1000),
            },
        )


LABELS = {
    "writing_outline": "策划稿件",
    "writing_draft": "撰写正文",
    "writing_revision": "修订正文",
    "writing_shorten": "压缩超长稿件",
}


def check_inputs(store, policy, version, day, analysis):
    from .batch_cancellation import check
    from .plan_controls import check_cancelled
    from .industry import check_public_context

    check(store)
    check_cancelled(store)
    store.renew()
    if store.policy() != (version, policy):
        raise ValueError("运营规则已变化，停止本次写稿")
    check_public_context(store, {"analysis_context": analysis}, policy, day)


def checked_outline(value, available):
    points = value.get("points")
    if points == [] and isinstance(value.get("gap"), str) and value["gap"].strip():
        raise StageSkipped("策划证据不足：" + value["gap"])
    if not isinstance(points, list) or not 1 <= len(points) <= 4:
        raise ModelOutputError("策划未返回1至4个有来源的要点")

    def field(row, name):
        text = row.get(name)
        if not isinstance(text, str) or not text.strip() or len(text) > 1000:
            raise ModelOutputError("策划字段无效：" + name)
        return text.strip()

    outline = {k: field(value, k) for k in ("question", "angle")}
    clean = []
    for point in points:
        ids = point.get("source_ids") if isinstance(point, dict) else None
        if not valid_ids(ids, available) or not ids:
            raise ModelOutputError("策划要点引用了本轮以外的来源或缺少来源")
        clean.append(
            {
                **{k: field(point, k) for k in ("claim", "use", "limit")},
                "source_ids": list(dict.fromkeys(ids)),
            }
        )
    return {**outline, "points": clean}


def valid_ids(values, allowed):
    return isinstance(values, list) and all(isinstance(v, str) and v in allowed for v in values)


class DraftTooLong(ModelOutputError):
    def __init__(self, draft, field, limit):
        super().__init__(f"{field} 为 {len(draft[field].strip())} 字，最多允许 {limit} 字")
        self.draft = draft


def checked_draft(value, sources, assets):
    if value.get("title") == "" and isinstance(value.get("reason"), str) and value["reason"].strip():
        raise StageSkipped(value["reason"])
    for field, limit in (("title", 20), ("body", 900)):
        text = value.get(field)
        if isinstance(text, str) and len(text.strip()) > limit:
            raise DraftTooLong(value, field, limit)
        if not isinstance(text, str) or not text.strip():
            raise ModelOutputError(f"写稿 Agent 的{field}为空或超过 {limit} 字")
    if not value.get("source_ids") or not valid_ids(value["source_ids"], sources):
        raise ModelOutputError("写稿 Agent 缺少引用或引用了未提供的来源")
    if not valid_ids(value.get("asset_ids", []), assets):
        raise ModelOutputError("写稿 Agent 引用了未提供的素材")
    return {
        **inputs.fields(value, ("source_ids", "reason", "asset_ids", "visual_plan")),
        "title": value["title"].strip(),
        "body": value["body"].strip(),
        "asset_ids": value.get("asset_ids", []),
    }


def variant_key(store, base):
    if getattr(store, "draft_mode", "reuse") == "new_variant":
        return hashlib.sha256(encoded(["debug-variant", store.debug_id, base]).encode()).hexdigest()
    return base


def write(store, policy, day, version, analysis, data, sources, signature, prior):
    key = f"writing-outline:v1:{day}:{signature}"
    saved = load(store, key)
    state = "resumed_outline" if saved else "generated"
    if not saved:
        outline_data = dict(data)
        if prior:
            outline_data["prior_article"] = inputs.fields(prior, ("title", "body"))
        check_inputs(store, policy, version, day, analysis)
        outline = turn(
            store,
            policy,
            day,
            "writing_outline",
            PLAN,
            outline_data,
            lambda value: checked_outline(value, {s["id"] for s in sources}),
        )
        check_inputs(store, policy, version, day, analysis)
        store.put("writing_outline", {"outline": outline, "day": day, "version": version}, key)
    else:
        outline = saved["outline"]
    ids = list(dict.fromkeys(i for point in outline["points"] for i in point["source_ids"]))
    excerpts = review_sources(
        {"title": outline["question"], "body": encoded(outline), "source_ids": ids}, sources
    )
    if not excerpts or any(not s["text"].strip() for s in excerpts):
        raise StageSkipped("成稿依据缺少原文，请补齐来源后继续")
    metadata = {
        s["id"]: inputs.fields(s, ("category", "summary", "facts", "opinions", "uncertainties", "images"))
        for s in data["sources"]
    }
    for row in excerpts:
        row.update(metadata[row["id"]])
    drafting = {
        **inputs.fields(data, ("policy", "selected_topic", "assets", "analysis", "tasks", "recent_content")),
        "outline": outline,
        "sources": excerpts,
    }
    check_inputs(store, policy, version, day, analysis)

    def validate(value):
        return checked_draft(value, set(ids), {a["id"] for a in drafting["assets"]})

    try:
        value = turn(store, policy, day, "writing_draft", DRAFT + CONTRACT, drafting, validate)
    except DraftTooLong as error:
        check_inputs(store, policy, version, day, analysis)
        data = {
            **drafting,
            "draft": inputs.fields(error.draft, ("title", "body")),
            "editor_feedback": str(error),
        }
        value = turn(
            store,
            policy,
            day,
            "writing_shorten",
            "压缩这篇草稿到350至450个字符。只保留一个案例和一条建议。" + CONTRACT,
            data,
            validate,
        )
    check_inputs(store, policy, version, day, analysis)
    return value, state, key


def revise(store, policy, day, data):
    return turn(
        store,
        policy,
        day,
        "writing_revision",
        REVISE + CONTRACT,
        data,
        lambda value: checked_draft(
            value, {s["id"] for s in data["sources"]}, {a["id"] for a in data["assets"]}
        ),
    )
