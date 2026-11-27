"""Manually receive the three notification tabs into the bound account inbox."""
import hashlib
import json
import uuid

from .message_time import observation_time, platform_fields
from .messages import read_items
from .policy import local_day
from .workflow import browser, resolve_account
from .workspace_execution import check_running

SOURCES = ("reply", "reaction", "follow")


def retry_account(store, policy, platform="xiaohongshu"):
    """Only a terminal, unsubmitted notification read can authorize a new read-only probe."""
    from .execution_pause import block
    from .readiness import web_block_reason

    with store.connection() as db:
        stopped = block(store, db)
        if not stopped or stopped.get("error_code") not in ("BROWSER_UNAVAILABLE", "SYSTEM_SUSPENDED", "COMMAND_EXPIRED"):
            return None
        if stopped.get("submitted") is not False or stopped.get("dispatch_state") not in ("read_only", "not_started"):
            return None
        row = db.execute("SELECT payload FROM commands WHERE id=? AND kind IN ('inbox','account') "
                         "AND action_id IS NULL AND state IN ('done','interrupted')",
                         (stopped.get("cause_command_id"),)).fetchone()
        if not row:
            return None
        payload = json.loads(row["payload"])
        if platform == "zhihu" and payload.get("readonly_inventory") == "zhihu_notifications":
            return True
        account = payload.get("account_id")
        if not account or payload.get("notification_source") not in SOURCES:
            return None
        held = web_block_reason(db)
        if held:
            raise ValueError(held)
        if store.workspace:
            linked = db.execute("SELECT identity FROM directory.accounts WHERE id=?", (store.scope["account"],)).fetchone()
            if not linked or (linked["identity"] and linked["identity"] != account):
                raise ValueError("原收件账号与当前绑定不一致，请重新核对账号")
        if policy["account_id"] and account != policy["account_id"]:
            raise ValueError("原收件账号与当前计划不一致，请重新核对账号")
        return account


def sync(store, *, platform="xiaohongshu"):
    if platform not in ("xiaohongshu", "zhihu"):
        raise ValueError("请选择小红书或知乎")
    version, policy = store.policy()
    check_running(store)
    retry = retry_account(store, policy, platform)
    if not retry:
        check_running(store, web=True)
    if not policy["enabled"] or policy["paused"]:
        raise ValueError("请启用当前主题计划并解除暂停，再接收平台通知")
    token = uuid.uuid4().hex
    if not store.lease(token):
        raise ValueError("当前主题有任务在运行，请在任务完成后接收")
    try:
        if platform == "zhihu":
            return receive_zhihu(store, policy, version)
        account = retry or resolve_account(store, policy)
        counts = {}
        for kind in SOURCES:
            payload = {"kind": kind, "notification_source": kind, "account_id": account}
            if retry:
                check_running(store)
                if retry_account(store, policy) != account:
                    check_running(store, web=True)
                result = browser(store, "account", {**payload, "resume_probe": True, "readonly_inventory": "notifications"})
            else:
                result = browser(store, "inbox", payload)
            if result.get("account_id") != account or result.get("notification_source") != kind or not isinstance(result.get("items"), list):
                raise ValueError("桌面端未确认通知来源与账号，请刷新 Desktop 后重试")
            if store.policy()[0] != version:
                raise ValueError("接收期间规则已变化，请刷新后重试")
            items = result["items"]
            observed = observation_time()
            for item in items:
                item.update(platform_fields(item, observed))
                identity = item.get("id")
                if not isinstance(identity, str) or not identity:
                    raise ValueError("通知条目缺少标识")
                if identity.startswith("["):
                    item["id"] = "notification:" + hashlib.sha256(identity.encode()).hexdigest()
            read_items(store, kind, account, items, auto=False, day=local_day(policy))
            counts[kind] = len(items)
        return counts
    finally:
        store.release(token)


def receive_zhihu(store, policy, version):
    from .readiness import web_block_reason
    with store.connection() as db:
        reason = web_block_reason(db)
    if reason:
        raise ValueError(reason)
    result = browser(store, "account", {"readonly_inventory": "zhihu_notifications", "resume_probe": True})
    account, groups = result.get("platform_identity"), result.get("groups")
    if result.get("notification_platform") != "zhihu" or not isinstance(account, str) or not account:
        raise ValueError("请刷新桌面端，并在当前业务账号中登录知乎")
    if not isinstance(groups, dict) or set(groups) != set(SOURCES):
        raise ValueError("知乎通知分类未完整返回")
    check_running(store)
    if store.policy()[0] != version:
        raise ValueError("接收期间规则已变化，请重新接收")
    observed = observation_time()
    for items in groups.values():
        if not isinstance(items, list):
            raise ValueError("知乎通知列表格式错误")
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
                raise ValueError("知乎通知缺少标识")
            item["id"] = hashlib.sha256(json.dumps([account, item["id"]]).encode()).hexdigest()
            item.update(platform_fields(item, observed))
    day = local_day(policy)
    for source, items in groups.items():
        read_items(store, source, account, items, auto=False, day=day, platform="zhihu")
    return {source: len(items) for source, items in groups.items()}
