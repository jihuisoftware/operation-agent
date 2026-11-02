"""Operations templates compose one policy; they never instantiate prompt-only cron jobs."""
from copy import deepcopy
from datetime import datetime, timedelta, UTC
import hashlib
from zoneinfo import ZoneInfo

from .modules import TIMES, ACTION_MODULE
from .policy import validate_policy, now_iso
from .store import encoded
from .scenarios import SCENARIOS
from .business_themes import BUSINESS_THEMES

TEMPLATES = [
    {"id": "daily", "title": "每日自动运营", "category": "完整流程", "description": "围绕一个目标组合每日流程，共享账号、额度与执行记录。", "output": "可追溯的运营成果与日报", "modules": ["research", "organize", "analytics", "industry", "topics", "content", "publish", "comments", "dm", "report"]},
    *BUSINESS_THEMES,
    *SCENARIOS,
    {"id": "research", "title": "信息采集", "category": "信息来源", "description": "按主题检索网页与 RSS，读取正文、去重并保留原始链接。", "output": "可追溯来源与采集结果", "modules": ["research"]},
    {"id": "organize", "title": "资料整理与归类", "category": "信息来源", "description": "将采集资料归类，区分事实陈述、观点与待核实信息，增量保存可复用资料。", "output": "分类资料库、摘要与原始出处", "modules": ["organize"]},
    {"id": "analytics", "title": "数据分析", "category": "分析研究", "description": "统计完整范围的来源、运营和导入业务数据，保留口径。", "output": "趋势图、指标与历史统计快照", "modules": ["analytics"]},
    {"id": "industry", "title": "行业分析", "category": "分析研究", "description": "依据有效分析分别形成内容运营和市场经营建议。", "output": "有出处的行业结论与证据不足项", "modules": ["industry"]},
    {"id": "topics", "title": "选题策划", "category": "内容与发布", "description": "使用已整理资料生成候选选题和依据，也可在选题管理中手动指定题目。", "output": "候选选题、事实结论与选题依据", "modules": ["topics"]},
    {"id": "content", "title": "图文内容生产", "category": "内容与发布", "description": "结合来源和授权素材生成草稿；缺图片时保留待完善版本。", "output": "内容版本与自动质量检查", "modules": ["content"]},
    {"id": "publish", "title": "小红书图文发布", "category": "内容与发布", "description": "使用已选定的内容版本，提交前核对账号、素材和规则。", "output": "发布回执、外部链接与异常记录", "modules": ["publish"]},
    {"id": "comments", "title": "评论互动", "category": "账号互动", "description": "回复自己笔记的评论，或在相关笔记下发表有内容的评论。", "output": "评论与回复的执行证据", "modules": ["comments"]},
    {"id": "dm", "title": "收到私信处理", "category": "账号互动", "description": "仅依据已确认知识回应收到的私信，不确定的问题转待处理。", "output": "回复记录与待处理咨询", "modules": ["dm"]},
    {"id": "follow", "title": "条件回关", "category": "账号互动", "description": "核对已关注本账号、尚未回关且符合配置条件的对象。", "output": "候选名单、判断依据与回关结果", "modules": ["follow"]},
    {"id": "report", "title": "运营日报与复盘", "category": "日报复盘", "description": "依据持久化记录汇总成果、失败、消耗和次日建议。", "output": "可导出的 Markdown 日报", "modules": ["report"]},
]
LABELS = {t["id"]: t["title"] for t in TEMPLATES}


def requirements(policy, module, assets):
    missing = []
    if not policy["topic"].strip():
        missing.append("填写运营主题")
    if not policy["goal"].strip():
        missing.append("填写运营目标")
    actions = [a for a, m in ACTION_MODULE.items() if m == module]
    if actions and not any(policy["allowed"][a] for a in actions):
        missing.append("选择并授权至少一个对应动作")
    if module == "publish" and not any(a.get("authorized") and not a.get("revoked") for a in assets):
        missing.append("上传获授权图片")
    if module == "dm" and not policy["knowledge"]:
        missing.append("补充已确认的回复知识")
    if module == "follow" and not policy["follow_terms"]:
        missing.append("填写回关匹配条件")
    return missing


def timeline(policy, now=None):
    now = (now or datetime.now(UTC)).astimezone(ZoneInfo(policy["timezone"]))
    rows = []
    for module in TIMES:
        if not policy["modules"][module]:
            continue
        for slot in sorted(set(policy["times"][module])):
            due = datetime.fromisoformat(f"{now.date()}T{slot}").replace(tzinfo=now.tzinfo)
            next_due = due if due > now else due + timedelta(days=1)
            rows.append({"module": module, "label": LABELS[module], "time": slot, "next_at": next_due.isoformat()})
    return sorted(rows, key=lambda row: (row["time"], list(TIMES).index(row["module"])))


def catalog(store):
    version, policy = store.policy()
    assets = store.objects("asset")
    with store.connection() as db:
        import time
        online = bool(db.execute("SELECT 1 FROM workers WHERE seen>?", (time.time() - 15,)).fetchone())
    templates = []
    for template in TEMPLATES:
        modules = template["modules"] if template["id"] != "daily" else [m for m in TIMES if policy["modules"][m]]
        selected = bool(modules) and all(policy["modules"][m] for m in modules)
        if template.get("kind") == "business":
            selected = policy["business_theme"] == template["id"]
        missing = list(dict.fromkeys(item for m in modules for item in requirements(policy, m, assets)))
        status = "未加入" if not selected else "待完善" if missing else "已暂停" if not policy["enabled"] or policy["paused"] else "已加入"
        templates.append({**template, "status": status, "missing": missing, "times": {m: policy["times"][m] for m in template["modules"]}})
    from .runtime import schedule_state
    schedule = schedule_state(store)
    rows = timeline(policy)
    drafts = store.objects("blueprint_draft")
    from .readiness import refresh, model_setup
    return {"model_ready": model_setup(), "readiness": refresh(store), "version": version, "policy": policy, "online": online, "templates": templates,
            "schedule_state": schedule, "timeline": rows, "next_at": min((r["next_at"] for r in rows), default=None) if policy["enabled"] and not policy["paused"] and schedule == "ready" else None,
            "draft": drafts[0] if drafts else None,
            "assets": [{"id": a["id"], "name": a["name"], "revoked": a.get("revoked", False)} for a in assets]}


def preview(store, body, *, check_version=True):
    version, current = store.policy()
    if check_version and body["version"] != version:
        raise ValueError("配置已变更，请刷新后重新配置")
    candidate = deepcopy(body["policy"])
    candidate["enabled"] = False
    candidate = validate_policy(candidate)
    for action, module in ACTION_MODULE.items():
        if not candidate["modules"][module]:
            candidate["allowed"][action] = False
    missing = {m: requirements(candidate, m, store.objects("asset")) for m in TIMES if candidate["modules"][m]}
    if not any(candidate["modules"].values()):
        missing["plan"] = ["至少选择一个运营模块"]
    blocking = []
    if not candidate['topic'].strip():
        blocking.append('填写运营主题')
    if not any(candidate['modules'].values()):
        blocking.append('至少选择一个运营模块')
    if not candidate['goal'].strip() and candidate['topic'].strip():
        candidate['goal'] = f"围绕「{candidate['topic']}」收集可靠资料，制作有依据的内容并记录运营成果。"
    from .readiness import conditions
    readiness = conditions(store, candidate)
    candidate["enabled"] = True
    candidate["paused"] = False
    changes = [{"field": key, "before": current[key], "after": value} for key, value in candidate.items() if value != current[key]]
    return {"version": version, "policy": candidate, "missing": {k: v for k, v in missing.items() if v},
            "blocking": blocking, "readiness": readiness, "changes": changes, "timeline": timeline(candidate)}


def apply(store, body):
    from .runtime import ensure_schedule
    request_id = body.get("request_id")
    mode = body.get("mode")
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100 or mode not in {"draft", "enable"}:
        raise ValueError("无效的应用请求")
    digest = hashlib.sha256(encoded({k: body[k] for k in ("version", "policy", "mode")}).encode()).hexdigest()
    result = _saved_result(store, request_id, digest, mode)
    if result is None:
        result = _save(store, body, digest)
    # Retrying repairs a failure between the durable policy commit and cron registration.
    if mode == "enable" and store.policy()[1]["enabled"]:
        result["job_id"] = ensure_schedule(store)
    return result


def _saved_result(store, request_id, digest, mode):
    import json
    with store.connection() as db:
        row = db.execute("SELECT data FROM objects WHERE id=?", ("apply:" + request_id,)).fetchone()
    if not row:
        return None
    saved = json.loads(row[0])
    if saved["hash"] != digest:
        raise ValueError("同一请求 ID 不能用于不同配置")
    return {"version": saved["version"], "draft": mode == "draft"}


def _save(store, body, digest):
    result = preview(store, body, check_version=False)
    if body["version"] != result["version"]:
        receipt = _saved_result(store, body["request_id"], digest, body["mode"])
        if receipt is not None:
            return receipt
        raise ValueError("配置已变更，请刷新后重新配置")
    if body["mode"] == "enable":
        if result["blocking"]:
            raise ValueError("；".join(result["blocking"]))
        version = store.configure(result["policy"], body["version"], request_id=body["request_id"], request_hash=digest, activation=True)
        return {"version": version, "draft": False}
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        saved = db.execute("SELECT data FROM objects WHERE id=?", ("apply:" + body["request_id"],)).fetchone()
        if saved:
            import json
            receipt = json.loads(saved[0])
            if receipt["hash"] != digest:
                raise ValueError("同一请求 ID 不能用于不同配置")
            return {"version": receipt["version"], "draft": True}
        if db.execute("SELECT version FROM settings WHERE id=1").fetchone()[0] != body["version"]:
            raise ValueError("配置已变更，请刷新后重新配置")
        db.execute("INSERT OR REPLACE INTO objects VALUES ('blueprint-draft', 'blueprint_draft', ?, ?)",
                   (encoded({"policy": result["policy"], "version": body["version"], "created": now_iso()}), now_iso()))
        db.execute("INSERT OR IGNORE INTO objects VALUES (?, 'application', ?, ?)",
                   ("apply:" + body["request_id"], encoded({"version": body["version"], "hash": digest}), now_iso()))
    return {"version": body["version"], "draft": True}
