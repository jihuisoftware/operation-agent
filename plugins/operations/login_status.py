"""Advisory login observations, scoped to a Profile and a live Desktop worker."""
from datetime import datetime, UTC
import time

PLATFORMS = (
    ("xiaohongshu", "小红书", "https://www.xiaohongshu.com/explore"),
    ("zhihu", "知乎", "https://www.zhihu.com/"),
    ("bilibili", "B 站", "https://www.bilibili.com/"),
    ("wechat", "微信公众号后台", "https://mp.weixin.qq.com/"),
    ("douyin", "抖音", "https://www.douyin.com/"),
)
STATES = {"logged_in", "logged_out", "verification", "unknown"}


def observe(store, body):
    platform, worker = body.get("platform"), body.get("worker")
    state, account = body.get("state"), body.get("account_id", "")
    if platform not in {p[0] for p in PLATFORMS} or state not in STATES:
        raise ValueError("未知平台或登录状态")
    if not isinstance(worker, str) or not 1 <= len(worker) <= 128:
        raise ValueError("执行窗口标识无效")
    if not isinstance(account, str) or len(account) > 128 or any(c in account for c in "\r\n\t"):
        raise ValueError("账号标识格式错误")
    if set(body) - {"platform", "worker", "state", "account_id"}:
        raise ValueError("登录观察只接受状态与账号标识，不接受凭证或网页内容")
    now = time.time()
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if not db.execute("SELECT 1 FROM workers WHERE id=? AND seen>?", (worker, now - 15)).fetchone():
            raise ValueError("执行窗口离线，请重新连接后检查")
        db.execute("INSERT OR REPLACE INTO platform_logins VALUES (?,?,?,?,?)",
                   (platform, worker, state, account if state == "logged_in" else "", now))
        if state in {"logged_in", "logged_out"}:
            db.execute("INSERT OR REPLACE INTO platform_login_evidence VALUES (?,?,?,?,?)",
                       (platform, worker, state, account if state == "logged_in" else "", now))
    from .workspace_execution import observe_account
    observe_account(store, body)
    from .execution_pause import observe as observe_execution
    observe_execution(store, body)
    return {"ok": True}


def catalog(store, worker=None):
    now = time.time()
    _, policy = store.policy()
    with store.connection() as db:
        online = bool(
            db.execute("SELECT 1 FROM workers WHERE id=? AND seen>?", (worker, now - 15)).fetchone()
            if worker else db.execute("SELECT 1 FROM workers WHERE seen>?", (now - 15,)).fetchone()
        )
        rows = []
        for platform, name, url in PLATFORMS:
            record = db.execute("SELECT * FROM platform_logins WHERE platform=? ORDER BY checked DESC, rowid DESC LIMIT 1",
                                (platform,)).fetchone()
            evidence = db.execute("SELECT * FROM platform_login_evidence WHERE platform=? ORDER BY checked DESC, rowid DESC LIMIT 1",
                                  (platform,)).fetchone()
            if store.workspace:
                import json
                shared = db.execute('SELECT record,evidence FROM directory.account_logins WHERE account_id=(SELECT account FROM directory.businesses WHERE id=?) AND platform=?', (store.scope['business_id'], platform)).fetchone()
                record, evidence = None, None
                if shared:
                    record, evidence = json.loads(shared['record']), json.loads(shared['evidence']) if shared['evidence'] else None
            rows.append(_row(platform, name, url, record, evidence, worker, policy))
    return {"platforms": rows, "worker_online": online}


def _row(platform, name, url, record, evidence, worker, policy):
    item = {"id": platform, "name": name, "url": url, "state": "unchecked", "observed_state": None,
            "checked_at": None, "confirmed_at": None, "account_id": "", "account_mismatch": False,
            "checked_in_current_window": False, "reason": "尚无登录检查记录"}
    if record is None:
        return item
    item.update(observed_state=record["state"], checked_at=_timestamp(record["checked"]),
                checked_in_current_window=record["worker"] == worker)
    state = evidence["state"] if evidence else record["state"]
    item.update(state=state, account_id=evidence["account_id"] if evidence else "", reason={
        "logged_in": "已确认登录；未发现明确失效，保留已登录状态。任务执行前仍核对实际账号。",
        "logged_out": "页面明确要求重新登录，请处理后再执行任务。",
        "verification": "页面要求安全验证，请人工处理。",
        "unknown": "尚未获得明确登录证据，请打开页面检查。",
    }[state])
    if evidence:
        item["confirmed_at"] = _timestamp(evidence["checked"])
    if state == "logged_in" and record["state"] == "verification":
        item["reason"] = "已登录，但页面要求安全验证；处理后再继续任务。"
    item["account_mismatch"] = bool(state == "logged_in" and platform == "xiaohongshu" and
                                    policy["account_id"] and item["account_id"] != policy["account_id"])
    return item


def _timestamp(value):
    return datetime.fromtimestamp(value, UTC).isoformat()
