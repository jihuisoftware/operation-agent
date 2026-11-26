"""Operator actions affect local ownership, never submit a platform reply."""

import json

from .message_storage import initialize, owner, table
from .messages import Conflict, lookup, present
from .policy import now_iso


def change(store, ident, body):
    operation, revision = body.get("operation"), body.get("revision")
    if operation not in ("take", "handle", "transfer", "ignore", "follow") or not isinstance(revision, str):
        raise ValueError("请选择操作并提交当前消息版本")
    if operation == "transfer" and not isinstance(body.get("target_topic"), str):
        raise ValueError("请选择目标主题")
    initialize(store)
    if operation == "follow":
        from .follower_messages import request as request_follow
        return request_follow(store, ident, revision)
    request = {
        "operation": operation,
        "revision": revision,
        "from": owner(store),
        "to": body.get("target_topic", "") if operation == "transfer" else "",
    }
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        saved = db.execute(f"SELECT history FROM {table(store)} WHERE id=?", (ident,)).fetchone()
        history = json.loads(saved[0]) if saved else []
        if any(entry.get("request") == request for entry in history):
            return {"ok": True}
        row = lookup(store, db, ident)
        if present(row)["revision"] != revision or row["state"] not in ("manual", "working", "auto"):
            raise Conflict("消息状态已变化，请刷新后处理")
        if operation == "ignore" and row["kind"] != "follow":
            raise ValueError("只有关注通知可忽略")
        next_topic = row["topic"]
        status = {"take": "working", "handle": "handled", "transfer": "manual", "ignore": "ignored"}[operation]
        if operation == "transfer":
            next_topic = transfer_target(store, db, row, request["to"])
        stamp = now_iso()
        history.append({"event": operation, "actor": "operator", "at": stamp, "request": request})
        reason = {"take": "人工已接手", "handle": "已在本地标记处理完成", "transfer": "由其他主题人工转交", "ignore": "人工已忽略此次关注"}[
            operation
        ]
        if operation == "transfer":
            snapshot = {
                **present(row),
                "state": "transferred",
                "message": ident,
                "updated": stamp,
                "target_topic": next_topic,
                "history": history,
            }
            db.execute(
                "INSERT INTO events(at,kind,data) VALUES (?,'message_transferred',?)",
                (stamp, json.dumps(snapshot)),
            )
        db.execute(
            f"UPDATE {table(store)} SET status=?,topic=?,revision=revision+1,history=?,reason=?,updated=? WHERE id=?",
            (status, next_topic, json.dumps(history), reason, stamp, ident),
        )
    return {"ok": True}


def transfer_target(store, db, row, topic):
    if not store.workspace or topic == row["topic"] or row["action_id"]:
        raise Conflict("当前消息不能转交")
    target = db.execute(
        "SELECT b.account FROM directory.topics t JOIN directory.businesses b ON b.id=t.business_id "
        "WHERE t.id=? AND t.archived=0 AND b.archived=0",
        (topic,),
    ).fetchone()
    original = db.execute(
        "SELECT account FROM directory.businesses WHERE id=? AND archived=0", (store.scope["business_id"],)
    ).fetchone()
    if not target or not original or original[0] != target[0] or target[0] != row["slot"] or not row["target"]:
        raise ValueError("只能转交给共用原账号的其他有效主题")
    db.execute(
        "INSERT INTO directory.account_claims VALUES(?,?,?,?,'') ON CONFLICT(account_id,kind,target) "
        "DO UPDATE SET topic_id=excluded.topic_id WHERE topic_id=? AND action_id=''",
        (row["slot"], row["kind"], row["target"], topic, row["topic"]),
    )
    if not db.execute("SELECT changes()").fetchone()[0]:
        raise Conflict("消息归属已变化，请刷新")
    return topic


def transfers(store, kind, before):
    if kind not in ("", "dm", "reply", "follow"):
        raise ValueError("未知消息类型")
    match = " FROM events WHERE kind='message_transferred' AND (?='' OR json_extract(data,'$.kind')=?)"
    with store.connection() as db:
        db.execute("BEGIN")
        total = db.execute("SELECT count(*)" + match, (kind, kind)).fetchone()[0]
        rows = db.execute(
            "SELECT id,data" + match + " AND (?=0 OR id<?) ORDER BY id DESC LIMIT 26",
            (kind, kind, before, before),
        ).fetchall()
    return {
        "items": [{**json.loads(r["data"]), "id": "transfer-" + str(r["id"])} for r in rows[:25]],
        "total": total,
        "next": rows[24]["id"] if len(rows) > 25 else None,
    }


def transfer_detail(db, identity):
    row = db.execute(
        "SELECT data FROM events WHERE kind='message_transferred' AND id=?", (identity[9:],)
    ).fetchone()
    if not row:
        raise KeyError("当前主题没有这条转交记录")
    return {**json.loads(row["data"]), "id": identity}
