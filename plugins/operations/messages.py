"""One record per received platform message. The action ledger owns delivery evidence."""

import json

from .message_storage import initialize, message_id, owner, table
from .policy import now_iso

KINDS = ("reply", "dm", "follow")
STATE = """CASE WHEN status!='action' THEN status
 WHEN delivery='confirmed' AND kind='follow' THEN 'followed'
 WHEN delivery='confirmed' THEN 'replied'
 WHEN delivery IN ('queued','executing') THEN 'sending'
 WHEN delivery IN ('unknown','submitted') OR delivery IS NULL THEN 'verify'
 ELSE 'manual' END"""
STATES = ("auto", "manual", "working", "sending", "verify", "replied", "handled", "archived", "followed", "ignored")


class Conflict(ValueError):
    pass


def slot_for(store, db):
    if store.workspace:
        return db.execute(
            "SELECT account FROM directory.businesses WHERE id=?", (store.scope["business_id"],)
        ).fetchone()[0]
    return ""


def read_items(store, kind, account, items, *, auto, day, platform="xiaohongshu"):
    if platform == "zhihu":
        kind = "zhihu:" + kind
    initialize(store)
    from .run_scope import annotate

    accepted = []
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        slot = slot_for(store, db)
        if store.workspace:
            registered = db.execute("SELECT identity FROM directory.accounts WHERE id=?", (slot,)).fetchone()
            if slot != store.scope["account"] or (platform == "xiaohongshu" and registered and registered[0] and registered[0] != account):
                raise ValueError("业务关联账号或实际登录账号已变化，请刷新")
            if platform == "zhihu":
                db.execute("INSERT OR REPLACE INTO directory.preferences VALUES (?,?)",
                           ("notification-identity:zhihu:" + slot, account))
        for item in items:
            target = item.get("id")
            if (
                not isinstance(target, str)
                or not target.strip()
                or (kind == "dm" and item.get("inbound") is not True)
                or (kind == "follow" and item.get("follows_me") is not True)
            ):
                continue
            ident = message_id(slot, account, kind, target)
            if store.workspace:
                claim = db.execute(
                    "SELECT topic_id FROM directory.account_claims WHERE account_id=? AND kind=? AND target=?",
                    (slot, kind, target),
                ).fetchone()
                if claim and claim[0] != owner(store):
                    continue
            stamp = now_iso()
            db.execute(
                f"INSERT OR IGNORE INTO {table(store)}(id,slot,account,kind,target,topic,status,item,created,updated) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    ident,
                    slot,
                    account,
                    kind,
                    target,
                    owner(store),
                    "auto",
                    json.dumps(annotate(store, {**item, "day": day})),
                    stamp,
                    stamp,
                ),
            )
            row = db.execute(f"SELECT topic,status,item FROM {table(store)} WHERE id=?", (ident,)).fetchone()
            if row["topic"] != owner(store):
                continue
            if store.workspace:
                db.execute(
                    "INSERT OR IGNORE INTO directory.account_claims VALUES(?,?,?,?,'')",
                    (slot, kind, target, owner(store)),
                )
            if kind == "follow" and item.get("already_following") and row["status"] in ("auto","manual","working"):
                db.execute(f"UPDATE {table(store)} SET status='followed',reason='平台已显示关注关系',revision=revision+1,updated=? WHERE id=?", (stamp, ident))
            elif row["status"] == "auto":
                if not auto:
                    divert(store, db, ident, "仅接收消息，等待人工处理")
                else:
                    accepted.append(item)
            payload = {**json.loads(row["item"]), **item}
            if json.loads(row["item"]) != payload:
                db.execute(
                    f"UPDATE {table(store)} SET item=?,updated=?,revision=revision+1 WHERE id=?",
                    (json.dumps(payload), stamp, ident),
                )
    return accepted


def pending(store, account, kind, *, auto):
    """Retry durable work even when a previous viewport has scrolled out of view."""
    with store.connection() as db:
        args = (owner(store), slot_for(store, db), account, kind)
        match = " WHERE topic=? AND slot=? AND account=? AND kind=? AND status='auto'"
        if not auto:
            db.execute(
                f"UPDATE {table(store)} SET status='manual',reason='仅接收消息，等待人工处理',"
                "revision=revision+1,updated=?" + match,
                (now_iso(), *args),
            )
            return []
        rows = db.execute(f"SELECT item FROM {table(store)}" + match + " ORDER BY rowid LIMIT 30", args)
        return [json.loads(r[0]) for r in rows]


def divert(store, db, ident, reason):
    db.execute(
        f"UPDATE {table(store)} SET status='manual',reason=?,revision=revision+1,updated=? "
        "WHERE id=? AND topic=? AND status='auto'",
        (reason, now_iso(), ident, owner(store)),
    )


def quota_wait(store, account, kind):
    with store.connection() as db:
        reason = "本轮回复额度已用完，保留到后续排期"
        db.execute(
            f"UPDATE {table(store)} SET reason=?,updated=?,revision=revision+1 "
            "WHERE slot=? AND topic=? AND account=? AND kind=? AND status='auto' AND reason!=?",
            (reason, now_iso(), slot_for(store, db), owner(store), account, kind, reason),
        )


def record_decision(store, account, kind, target, *, reason="", reply="", human=False):
    with store.connection() as db:
        ident = message_id(slot_for(store, db), account, kind, target)
        db.execute(
            f"UPDATE {table(store)} SET reason=?,reply=?,updated=?,revision=revision+1 WHERE id=? AND topic=? AND status='auto' AND (reason!=? OR reply!=?)",
            (reason, reply, now_iso(), ident, owner(store), reason, reply),
        )
        if human:
            divert(store, db, ident, reason)


def reserve(store, db, action, identity, *, operator=False):
    if action["kind"] not in KINDS:
        return True
    ident = message_id(slot_for(store, db), action["account_id"], action["kind"], action["target"])
    row = db.execute(f"SELECT topic,status,action_id FROM {table(store)} WHERE id=?", (ident,)).fetchone()
    if not row:
        # Older direct callers may reserve without a preceding inventory pass.
        stamp = now_iso()
        db.execute(
            f"INSERT INTO {table(store)}(id,slot,account,kind,target,topic,status,item,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                ident,
                slot_for(store, db),
                action["account_id"],
                action["kind"],
                action["target"],
                owner(store),
                "auto",
                json.dumps(action.get("item", {})),
                stamp,
                stamp,
            ),
        )
    return bool(
        db.execute(
            f"UPDATE {table(store)} SET status='action',action_id=?,reply=?,reason=?,updated=?,revision=revision+1 "
            "WHERE id=? AND topic=? AND (status='auto' OR (? AND status IN ('manual','working')))",
            (identity, action.get("text", ""), action.get("reason", ""), now_iso(), ident, owner(store), operator),
        ).rowcount
    )


def projection(store):
    return (
        f"(SELECT records.*, {STATE} AS state FROM (SELECT m.*,m.rowid AS cursor,"
        f"a.state AS delivery,a.result AS receipt FROM {table(store)} m "
        "LEFT JOIN main.actions a ON a.id=m.action_id AND m.topic=?) records)"
    )


def account_query(store, kind="", state="", platform=""):
    if not store.workspace:
        return query(store, kind, state, platform)
    condition, args = filters(kind, state, platform)
    # The action and its receipt belong to the handling topic. For peers, use the
    # account-wide action ledger so a confirmed reply isn't shown as unverified.
    source = (
        f" FROM (SELECT records.*, {STATE} AS state FROM ("
        "SELECT m.*,m.rowid AS cursor,t.name AS owner_topic,m.topic!=? AS read_only,"
        "CASE WHEN m.topic=? THEN a.state ELSE shared.state END AS delivery,a.result AS receipt "
        "FROM directory.inbound_messages m JOIN directory.businesses b ON b.account=m.slot "
        "JOIN directory.accounts acct ON acct.id=b.account JOIN directory.topics t ON t.id=m.topic "
        "LEFT JOIN main.actions a ON a.id=m.action_id AND m.topic=? "
        "LEFT JOIN directory.account_actions shared ON shared.topic_id=m.topic "
        "AND shared.action_id=m.action_id AND shared.account_id=m.slot "
        "LEFT JOIN directory.preferences zh ON zh.id='notification-identity:zhihu:'||m.slot "
        "WHERE b.id=? AND ((m.kind LIKE 'zhihu:%' AND m.account=zh.data) OR (m.kind NOT LIKE 'zhihu:%' AND ((acct.identity!='' AND acct.identity=m.account) "
        "OR (m.topic=? AND (acct.identity='' OR m.account='')))))) records) WHERE 1=1"
    )
    topic = owner(store)
    return source + condition, [topic, topic, topic, store.scope["business_id"], topic, *args]


def filters(kind, state, platform=""):
    if kind not in ("", *KINDS, "reaction") or state not in ("", "attention", *STATES):
        raise ValueError("消息筛选无效")
    if platform not in ("", "xiaohongshu", "zhihu"):
        raise ValueError("消息平台无效")
    where, args = [], []
    if platform:
        where.append("kind LIKE 'zhihu:%'" if platform == "zhihu" else "kind NOT LIKE 'zhihu:%'")
    if kind:
        where.append("kind IN (?,?)")
        args.extend((kind, "zhihu:" + kind))
    if state == "attention":
        where.append("state IN ('manual','working')")
    elif state:
        where.append("state=?")
        args.append(state)
    return "".join(" AND " + f for f in where), args


def query(store, kind="", state="", platform=""):
    condition, args = filters(kind, state, platform)
    return " FROM " + projection(store) + " WHERE topic=?" + condition, [owner(store), owner(store), *args]


def listing(store, kind="", state="", before=0, *, account_view=False, platform=""):
    from .message_time import ordered_page
    initialize(store)
    if state == "transferred":
        from .message_actions import transfers

        return transfers(store, kind, before, platform)
    source, args = (account_query if account_view else query)(store, kind, state, platform)
    with store.connection() as db:
        db.execute("BEGIN")
        total = db.execute("SELECT count(*)" + source, args).fetchone()[0]
        rows, cursor = ordered_page(db, source, args, before)
    return {
        "total": total,
        "items": [present(r) for r in rows],
        "next": cursor,
    }


def present(row, detailed=False):
    item = json.loads(row["item"])
    result = {
        k: row[k]
        for k in (
            "id",
            "kind",
            "account",
            "target",
            "state",
            "reason",
            "reply",
            "action_id",
            "created",
            "updated",
        )
    }
    platform, _, source = row["kind"].partition(":")
    result.update(
        platform="zhihu" if source and platform == "zhihu" else "xiaohongshu",
        kind=source or row["kind"],
        platform_time=item.get("platform_time", ""),
        platform_time_sort=item.get("platform_time_sort"),
        text=item.get("text", ""),
        url=item.get("url", ""),
        revision=f"{row['revision']}:{row['delivery'] or ''}",
    )
    if "read_only" in row.keys():
        result.update(read_only=bool(row["read_only"]), owner_topic=row["owner_topic"])
    if row["kind"] == "follow":
        result.update(follows_me=item.get("follows_me"), already_following=item.get("already_following"))
    if detailed:
        result.update(history=json.loads(row["history"]), receipt=json.loads(row["receipt"] or "{}"))
    return result


def lookup(store, db, ident, *, account_view=False):
    source, args = account_query(store) if account_view else query(store)
    row = db.execute("SELECT *" + source + " AND id=?", (*args, ident)).fetchone()
    if not row:
        raise KeyError("当前主题没有这条消息")
    return row


def detail(store, ident, *, account_view=False):
    initialize(store)
    with store.connection() as db:
        if ident.startswith("transfer-"):
            from .message_actions import transfer_detail

            return transfer_detail(db, ident)
        try:
            row = lookup(store, db, ident, account_view=account_view)
        except KeyError:
            alias = legacy_id(store, ident)
            if not alias:
                raise
            row = lookup(store, db, alias, account_view=account_view)
        result = present(row, True)
        if result.get("read_only"):
            return result
        if row['kind'] == 'follow':
            from .follower_messages import eligibility
            result['matching_terms'], result['follow_disabled_reason'] = eligibility(store, db, row, store.policy()[1])
        if row["action_id"]:
            action = db.execute(
                "SELECT id,kind,version,day,state,result FROM actions WHERE id=?", (row["action_id"],)
            ).fetchone()
            result["action"] = dict(action) if action else None
        return result


def can_reserve(store, db, action, *, retry_id=None):
    if action["kind"] not in KINDS:
        return True
    ident = message_id(slot_for(store, db), action["account_id"], action["kind"], action["target"])
    row = db.execute(f"SELECT topic,status,action_id FROM {table(store)} WHERE id=?", (ident,)).fetchone()
    if not row:
        return retry_id is None
    if row["topic"] != owner(store):
        return False
    return (row["status"] == "action" and row["action_id"] == retry_id) if retry_id else row["status"] == "auto"


def legacy_id(store, ident):
    initialize(store)
    with store.connection() as db:
        row = db.execute(
            f"SELECT id FROM {table(store)} WHERE topic=? AND (id=? OR action_id=? OR EXISTS (SELECT 1 FROM "
            "json_each(history) WHERE json_extract(value,'$.event')='legacy' AND json_extract(value,'$.id')=?))",
            (owner(store), ident, ident, ident),
        ).fetchone()
    return row[0] if row else None


def inbox_records(store, day=None, limit=None):
    """Project the existing report/snapshot contract from canonical messages and other work items."""
    initialize(store)
    source, args = query(store)
    with store.connection() as db:
        rows = db.execute(
            "SELECT *"
            + source
            + " AND (? IS NULL OR json_extract(item,'$.day')=?) ORDER BY cursor DESC LIMIT ?",
            (*args, day, day, -1 if limit is None else limit),
        ).fetchall()
        others = db.execute(
            "SELECT * FROM objects WHERE kind='inbox' AND json_extract(data,'$.kind') ='comment' "
            "AND (? IS NULL OR json_extract(data,'$.day')=?) ORDER BY rowid DESC LIMIT ?",
            (day, day, -1 if limit is None else limit),
        ).fetchall()
    result = [{**json.loads(r["data"]), "id": r["id"], "created": r["created"]} for r in others]
    for row in rows:
        state = "needs_review" if row["state"] in ("manual", "working") else row["state"]
        result.append(
            {
                **json.loads(row["item"]),
                "id": row["id"],
                "state": state,
                "kind": row["kind"],
                "account_id": row["account"],
                "reason": row["reason"],
                "legacy_state": json.loads(row["item"]).get("state"),
                "created": row["created"],
            }
        )
    return sorted(result, key=lambda r: r["created"], reverse=True)[:limit]
