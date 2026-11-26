"""Offer follow-back for a specific observed relationship, using the ordinary action queue."""

import json

from . import messages
from .policy import local_day, permitted, matching_follow_terms


def action_for(row):
    return {
        "kind": "follow",
        "account_id": row["account"],
        "target": row["target"],
        "item": json.loads(row["item"]),
        "reason": "运营人员按当前主题的回关规则办理",
    }


def eligibility(store, db, row, policy):
    from .readiness import web_block_reason

    action = action_for(row)
    terms = matching_follow_terms(policy, action["item"])
    if row["state"] not in ("auto", "manual", "working") or row["action_id"]:
        return terms, "此记录已有处理结论或外部动作"
    if row["slot"] != messages.slot_for(store, db):
        return terms, "主题关联账号已变更"
    reason = permitted(policy, action) or web_block_reason(db)
    if reason:
        return terms, reason
    if policy['deadline'] and local_day(policy) > policy['deadline'][:10]:
        return terms, '目标已超过期限'
    if store.workspace:
        account = db.execute("SELECT identity,conflict FROM directory.accounts WHERE id=?", (row["slot"],)).fetchone()
        if not account or account["conflict"] or (account["identity"] and account["identity"] != row["account"]):
            return terms, "业务账号需要重新核对"
    if store.workspace and store.workspace.blocked(store.scope):
        return terms, "业务或主题已暂停或归档"
    from .execution_pause import block

    blocked = block(store, db)
    if blocked:
        return terms, blocked.get("error") or "账号执行已暂停"
    from .store_reads import worker_status

    if not worker_status(db)["online"]:
        return terms, "桌面执行器离线，请先连接"
    used = db.execute(
        "SELECT count(*) FROM actions WHERE day=? AND kind='follow' AND state!='cancelled'",
        (local_day(policy),),
    ).fetchone()[0]
    if used >= policy["limits"]["follow"]:
        return terms, "主题当日回关额度已用完"
    if store.workspace:
        from .workspace_execution import budget_day

        limits = json.loads(
            db.execute("SELECT data FROM directory.preferences WHERE id='limits'").fetchone()[0]
        )
        used = db.execute(
            "SELECT coalesce(sum(amount),0) FROM directory.charges WHERE account_id=? AND kind='follow' AND day=?",
            (row["slot"], budget_day(store, local_day(policy), limits)),
        ).fetchone()[0]
        if used >= limits["follow"]:
            return terms, "账号当日共享回关额度已用完"
    return terms, ""


def request(store, identity, revision):
    with store.connection() as db:
        row = messages.lookup(store, db, identity)
        if row["kind"] != "follow":
            raise ValueError("请选择关注通知")
        if row["action_id"]:
            receipt = db.execute(
                "SELECT json_extract(data,'$.operator_follow_revision') FROM actions WHERE id=?",
                (row["action_id"],),
            ).fetchone()
            if receipt and receipt[0] == revision:
                return {"ok": True, "action_id": row["action_id"]}
        if messages.present(row)["revision"] != revision:
            raise messages.Conflict("关注状态已变化，请刷新")
        version, policy = store.policy()
        _, reason = eligibility(store, db, row, policy)
        if reason:
            raise ValueError(reason)
        action = action_for(row)
    action["operator_follow_revision"] = revision
    from .execution_pause import ExecutionPaused
    from .outcomes import StageSkipped
    try:
        result = store.reserve_action(action, version, follow_request=(identity, revision))
    except (ExecutionPaused, StageSkipped) as exc:
        raise messages.Conflict(str(exc)) from exc
    if not result:
        raise messages.Conflict("已有回关动作或记录已变化，请刷新")
    return {"ok": True, "action_id": result}


def check_revision(store, db, action, request):
    expected_id, revision = request
    identity = messages.message_id(
        messages.slot_for(store, db), action["account_id"], "follow", action["target"]
    )
    if identity != expected_id:
        raise messages.Conflict("关联账号已变更，请刷新")
    row = messages.lookup(store, db, identity)
    if (
        action["kind"] != "follow"
        or row["kind"] != "follow"
        or row["state"] not in ("auto", "manual", "working")
        or row["action_id"]
        or messages.present(row)["revision"] != revision
    ):
        raise messages.Conflict("关注状态已变化，请刷新后操作")
