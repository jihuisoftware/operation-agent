"""Searchable collected materials and explicit cross-day reuse scoped to the active topic."""
import hashlib
import json

from .collection_validation import fingerprint as content_fingerprint
from .policy import now_iso
from .store import encoded


def pins(store, topic):
    with store.connection() as db:
        return {row[0] for row in db.execute(
            "SELECT json_extract(data,'$.source_id') FROM objects WHERE kind='source_pin' "
            "AND json_extract(data,'$.scope_topic')=? AND json_extract(data,'$.enabled')=1", (topic,))}


def available_sources(store, policy, day, *, include_history=False):
    selected = pins(store, policy["topic"])
    seen, rows = set(), []
    # Explicitly chosen material wins the bounded topic-model input budget.
    sources = sorted(store.objects("source"), key=lambda row: row["id"] not in selected)
    for row in sources:
        eligible = row["id"] in selected or (row.get("day") == day and row.get("scope_topic", policy["topic"]) == policy["topic"])
        eligible = eligible or (include_history and row.get('scope_topic') == policy['topic'])
        fingerprint = content_fingerprint(row.get("text", "")) or row["id"]
        if eligible and row.get("text") and fingerprint not in seen:
            seen.add(fingerprint)
            rows.append(row)
    return rows


def reuse(store, identity, body):
    if type(body.get("enabled")) is not bool:
        raise ValueError("请选择加入或移除")
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        setting = db.execute("SELECT version,data FROM settings WHERE id=1").fetchone()
        if setting["version"] != body.get("version"):
            raise ValueError("运营规则已变更，请刷新素材库")
        topic = json.loads(setting["data"])["topic"]
        if not topic:
            raise ValueError("请先设置运营主题")
        row = db.execute("SELECT data FROM objects WHERE kind='source' AND id=?", (identity,)).fetchone()
        if not row or not json.loads(row[0]).get("text"):
            raise ValueError("来源不存在或未取得正文，不能用于选题")
        key = "source-pin:" + hashlib.sha256(encoded([topic, identity]).encode()).hexdigest()
        data = {"source_id": identity, "scope_topic": topic, "enabled": body["enabled"], "updated": now_iso()}
        db.execute("INSERT OR REPLACE INTO objects VALUES (?, 'source_pin', ?, ?)", (key, encoded(data), now_iso()))
    return data


def catalog(store, query="", cursor=0):
    version, policy = store.policy()
    selected = pins(store, policy["topic"])
    with store.connection() as db:
        condition = "kind='source' AND (?='' OR instr(lower(data),lower(?))>0)"
        total = db.execute("SELECT count(*) FROM objects WHERE " + condition, (query, query)).fetchone()[0]
        rows = db.execute("SELECT rowid,id,data FROM objects WHERE " + condition +
                          " AND (?=0 OR rowid<?) ORDER BY rowid DESC LIMIT 25", (query, query, cursor, cursor)).fetchall()
    with store.connection() as db:
        latest = db.execute("SELECT data FROM objects WHERE kind='collection_run' AND json_extract(data,'$.scope_topic')=? ORDER BY created DESC LIMIT 1", (policy['topic'],)).fetchone()
    items = []
    for row in rows[:24]:
        item = json.loads(row["data"])
        items.append({**{k: item.get(k) for k in ("title", "url", "summary", "author", "published_at", "collected_at", "day", "state", "error", "scope_topic")},
                      "id": row["id"], "excerpt": item.get("text", "")[:500], "images": item.get("images", []), "selected": row["id"] in selected})
    return {"version": version, "topic": policy["topic"], "total": total, "selected_count": len(selected),
            "latest_collection": json.loads(latest[0]) if latest else None, "items": items, "next_cursor": rows[23]["rowid"] if len(rows) > 24 else None}


def detail(store, identity):
    with store.connection() as db:
        row = db.execute("SELECT data FROM objects WHERE kind='source' AND id=?", (identity,)).fetchone()
        if not row:
            raise ValueError("来源不存在")
        usages = [dict(r) for r in db.execute(
            "SELECT id,json_extract(data,'$.title') AS title,json_extract(data,'$.day') AS day FROM objects "
            "WHERE kind='content' AND EXISTS (SELECT 1 FROM json_each(objects.data,'$.source_ids') WHERE value=?) "
            "ORDER BY created DESC LIMIT 30", (identity,))]
    return {**json.loads(row[0]), "id": identity, "content_versions": usages}
