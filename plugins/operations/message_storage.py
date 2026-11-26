"""Account-wide ownership with topic-scoped access and a transactional legacy import."""

from contextlib import closing
import hashlib
import json
import sqlite3

TABLE = """CREATE TABLE inbound_messages(
 id TEXT PRIMARY KEY,slot TEXT NOT NULL,account TEXT NOT NULL,kind TEXT NOT NULL,target TEXT NOT NULL,
 topic TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, item TEXT NOT NULL,
 reason TEXT NOT NULL DEFAULT '', reply TEXT NOT NULL DEFAULT '', action_id TEXT NOT NULL DEFAULT '',
 created TEXT NOT NULL, updated TEXT NOT NULL, history TEXT NOT NULL DEFAULT '[]')"""


def table(store):
    return "directory.inbound_messages" if store.workspace else "main.inbound_messages"


def owner(store):
    return store.scope["id"] if store.scope else ""


def message_id(slot, account, kind, target):
    return hashlib.sha256(json.dumps([slot, account, kind, target], ensure_ascii=False).encode()).hexdigest()


def initialize(store):
    directory = store.workspace
    with directory.connection() if directory else store.connection() as db:
        if exists(db, "inbound_messages"):
            return
        db.execute("BEGIN IMMEDIATE")
        if exists(db, "inbound_messages"):
            return
        db.execute(TABLE)
        db.execute("CREATE INDEX inbound_topic ON inbound_messages(topic,status,kind)")
        if not directory:
            import_topic(db, db, "", "")
            return
        for row in db.execute(
            "SELECT t.id,t.file,b.account FROM topics t JOIN businesses b ON b.id=t.business_id ORDER BY t.rowid"
        ):
            path = directory.root / row["file"]
            if path.is_file():
                with closing(
                    sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=15)
                ) as source:
                    source.row_factory = sqlite3.Row
                    import_topic(db, source, row["id"], row["account"])


def exists(db, name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()


def import_topic(db, source, topic, slot):
    if not exists(source, "objects"):
        return
    for row in source.execute("SELECT * FROM objects WHERE kind='inbox'"):
        data = json.loads(row["data"])
        if data.get("kind") in ("comment", "follow"):
            continue
        if data.get("kind") not in ("reply", "dm"):
            data["kind"] = "legacy"
        state = data.get("state")
        legacy(db, topic, slot, data, row, "handled" if state in ("handled", "transferred") else "manual")
    for row in source.execute("SELECT * FROM actions WHERE kind IN ('reply','dm') ORDER BY rowid"):
        data = json.loads(row["data"])
        item = {
            **data.get("item", {}),
            "id": data.get("target"),
            "kind": row["kind"],
            "account_id": data.get("account_id"),
        }
        if "inbound" in data:
            item["inbound"] = data["inbound"]
        legacy(db, topic, slot, item, row, "action", action=row["id"], reply=data.get("text", ""))


def legacy(db, topic, slot, data, row, state, action="", reply=""):
    kind, account, target = data["kind"], data.get("account_id") or "", data.get("id") or ""
    # Keep unidentifiable records for review without inventing a platform identity.
    identity = (
        message_id(slot, account, kind, target)
        if account and target
        else message_id(topic, "", kind, row["id"])
    )
    if not (account and target) or kind == "legacy" or (kind == "dm" and data.get("inbound") is not True):
        state = "archived"
    entry = {
        "event": "legacy",
        "topic": topic,
        "id": row["id"],
        "state": data.get("state") or state,
        "at": row["created"],
        "text": data.get("text", ""),
        "reason": data.get("reason", ""),
        "action_id": action,
        "delivery": row["state"] if action else "",
    }
    claim = (
        db.execute(
            "SELECT topic_id FROM account_claims WHERE account_id=? AND kind=? AND target=?",
            (slot, kind, target),
        ).fetchone()
        if slot
        else None
    )
    owned = claim[0] if claim else topic
    saved = db.execute("SELECT * FROM inbound_messages WHERE id=?", (identity,)).fetchone()
    reason = data.get("reason") or "历史记录，需人工核对"
    if not saved:
        db.execute(
            "INSERT INTO inbound_messages(id,slot,account,kind,target,topic,status,item,reason,reply,action_id,created,updated,history) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                identity,
                slot,
                account,
                kind,
                target,
                owned,
                state,
                json.dumps(data),
                reason,
                reply,
                action,
                row["created"],
                row["created"],
                json.dumps([entry]),
            ),
        )
        return
    past = json.loads(saved["history"])
    history = past + [entry]
    db.execute("UPDATE inbound_messages SET history=? WHERE id=?", (json.dumps(history), identity))
    if owned != topic or (not action and saved["action_id"]):
        return
    if action:
        if saved["status"] == "handled" and row["state"] in (
            "failed",
            "cancelled",
            "blocked",
            "confirmed_not_published",
        ):
            return
        # Multiple legacy manual batches could target one incoming message.
        # Preserve stronger delivery evidence when a later attempt failed.
        previous = next((e for e in reversed(past) if e["action_id"] == saved["action_id"]), {})
        rank = {"confirmed": 3, "unknown": 2, "submitted": 2, "queued": 2, "executing": 2}
        if rank.get(previous.get("delivery"), 0) > rank.get(entry["delivery"], 0):
            return
    elif saved["topic"] != owned and not claim:
        if state != "handled" or saved["action_id"]:
            return
        owned = saved["topic"]
    if (
        action
        or state == "handled"
        or data.get("transferred_from")
        or (state == saved["status"] == "manual" and data.get("reason"))
    ):
        db.execute(
            "UPDATE inbound_messages SET topic=?,status=?,item=?,reason=?,reply=?,action_id=? WHERE id=?",
            (owned, state, json.dumps(data), reason, reply, action, identity),
        )
