"""Validated standing authorization, independent of model output."""
from copy import deepcopy
from datetime import datetime, UTC
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from .modules import TIMES, ACTION_MODULE
from .business_themes import validate_business_selection
from .model_budget_settings import DEFAULT_CALLS, POLICY_DEFAULTS, topic_config, validate as validate_model_budget

LIMITS = {"source": 10_000, "publish": 1, "comment": 5, "reply": 20, "dm": 10, "follow": 5}
DEFAULT = {"schema_version": 5, "modules": {k: False for k in TIMES}, "enabled": False, "paused": False, "topic": "", "audience": "", "goal": "",
           "style": "真实、清楚、具体", "brand": "", "image_mode": "magazine", "account_id": "", "timezone": "Asia/Shanghai",
           "sources": [], "rss_sources": [], "keywords": [], "knowledge": [], "follow_terms": [],
           "allowed": {k: k != "follow" for k in LIMITS if k != "source"}, "limits": LIMITS,
           "times": TIMES, "deadline": "", "priority": 1, "model_calls": DEFAULT_CALLS, **POLICY_DEFAULTS,
           "business_theme": "", "business_subtype": ""}


def now_iso():
    return datetime.now(UTC).isoformat()


def local_day(policy, now=None):
    return (now or datetime.now(UTC)).astimezone(ZoneInfo(policy["timezone"])).date().isoformat()


def public_url(value):
    parsed = urlsplit(value)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("信息源必须是无凭证的 HTTP/HTTPS 地址")
    return value


def validate_policy(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULT):
        raise ValueError("未知运营配置字段")
    result = deepcopy(DEFAULT)
    if value.get('schema_version', 5) != 5:
        raise ValueError('不支持旧运营规则，请重新配置')
    result.update(value)
    for key in ("enabled", "paused"):
        if not isinstance(result[key], bool):
            raise ValueError(f"{key} 必须是布尔值")
    for key in ("topic", "audience", "goal", "style", "account_id", "deadline", "brand", "business_theme", "business_subtype"):
        if not isinstance(result[key], str) or len(result[key]) > 8000:
            raise ValueError(f"{key} 格式错误")
    if not isinstance(result["image_mode"], str) or result["image_mode"] not in {"magazine", "basic"}:
        raise ValueError("配图方式必须为杂志组图或基础文字封面")
    validate_business_selection(result["business_theme"], result["business_subtype"])
    if type(result["priority"]) is not int or not 1 <= result["priority"] <= 5:
        raise ValueError("优先级必须是 1 到 5 的整数")
    ZoneInfo(result["timezone"])
    _validate_collections(result)
    validate_model_budget(topic_config(result))
    if result["schema_version"] != 5 or set(result["modules"]) != set(TIMES) or any(type(v) is not bool for v in result["modules"].values()):
        raise ValueError("运营模块格式错误")
    if result["enabled"] and not any(result["modules"].values()):
        raise ValueError("启用前至少选择一个运营模块")
    if result["enabled"] and not all(result[k].strip() for k in ("topic", "goal")):
        raise ValueError("启用前请填写主题和目标")
    if result["deadline"]:
        datetime.fromisoformat(result["deadline"])
    return result


def _validate_collections(result):
    for key in ("sources", "rss_sources", "keywords", "knowledge", "follow_terms"):
        if not isinstance(result[key], list) or len(result[key]) > 100:
            raise ValueError(f"{key} 最多 100 条")
        if any(not isinstance(v, str) or len(v) > 8000 for v in result[key]):
            raise ValueError(f"{key} 必须是文本列表")
    for url in result["sources"] + result["rss_sources"]:
        public_url(url)
    if set(result["limits"]) != set(LIMITS):
        raise ValueError("每日额度字段不完整")
    for kind, value in {**result["limits"], "model_calls": result["model_calls"]}.items():
        maximum = 10_000 if kind == "source" else 1000
        if type(value) is not int or not 0 <= value <= maximum:
            raise ValueError(f"{kind} 额度必须是 0 到 {maximum} 的整数")
    if set(result["allowed"]) != set(DEFAULT["allowed"]) or any(type(v) is not bool for v in result["allowed"].values()):
        raise ValueError("动作开关格式错误")
    if set(result["times"]) != set(TIMES):
        raise ValueError("每日时间表不完整")
    for values in result["times"].values():
        if not isinstance(values, list) or not 1 <= len(values) <= 12:
            raise ValueError("每类任务需配置 1 到 12 个时间")
        for value in values:
            if datetime.strptime(value, "%H:%M").strftime("%H:%M") != value:
                raise ValueError("时间应使用 HH:MM")


def permitted(policy, action):
    if not policy["enabled"] or policy["paused"]:
        return "运营计划未启用或已暂停"
    if not policy["modules"].get(ACTION_MODULE.get(action["kind"]), False) or not policy["allowed"].get(action["kind"], False):
        return "该动作未授权"
    if not isinstance(action.get("account_id"), str) or not action["account_id"].strip():
        return "尚未识别实际登录账号"
    if policy["account_id"] and action.get("account_id") != policy["account_id"]:
        return "目标账号不匹配"
    handlers = {"dm": _permit_dm, "follow": _permit_follow}
    check = handlers.get(action["kind"])
    return check(policy, action) if check else ""


def _permit_dm(policy, action):
    ids = action.get("knowledge_ids", [])
    if not action.get("inbound") or not ids:
        return "私信必须有收到的消息及知识依据"
    if any(type(i) is not int or not 0 <= i < len(policy["knowledge"]) for i in ids):
        return "知识条目已变更，请重新评估"
    if action.get("text") not in [policy["knowledge"][i] for i in ids]:
        return "私信超出当前已确认知识"
    return ""


def _permit_follow(policy, action):
    item = action.get("item", {})
    if not policy["follow_terms"]:
        return "尚未配置回关条件"
    if item.get("already_following") or not item.get("follows_me") or not any(
            term.casefold() in item.get("text", "").casefold() for term in policy["follow_terms"]):
        return "不满足当前回关条件"
    return ""
