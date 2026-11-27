"""Attribute platform receipts to the day observed, including receipts after a daily report closed."""

import json

from .policy import local_day, now_iso


def record(db, command):
    if command["kind"] == "verify":
        identity = json.loads(command["payload"]).get("verification_action_id")
    elif command["kind"] == "publish":
        identity = command["action_id"]
    else:
        return
    row = db.execute(
        "SELECT day,state,json_extract(data,'$.content.title') AS title FROM actions WHERE id=? AND kind='publish'",
        (identity,),
    ).fetchone()
    if not row:
        return
    policy = json.loads(db.execute("SELECT data FROM settings WHERE id=1").fetchone()[0])
    from datetime import datetime

    stamp = now_iso()
    value = {
        "day": local_day(policy, datetime.fromisoformat(stamp)),
        "action_day": row["day"],
        "action_id": identity,
        "title": row["title"],
        "state": row["state"],
        "command_id": command["id"],
    }
    db.execute(
        "INSERT INTO events(at,kind,data) VALUES (?,'publication_receipt',?)",
        (stamp, json.dumps(value, ensure_ascii=False)),
    )


def markdown(db, report, text):
    if report.get("debug_id") or report.get("manual_run_id") or not report.get("created"):
        return text
    rows = db.execute(
        """SELECT at,json_extract(data,'$.title'),json_extract(data,'$.state') FROM events
        WHERE kind='publication_receipt' AND json_extract(data,'$.day')=?
        AND (at>? OR json_extract(data,'$.action_day')!=?) ORDER BY id""",
        (report["day"], report["created"], report["day"]),
    )
    labels = {
        "published": "已发布",
        "confirmed": "已确认",
        "submitted": "已提交",
        "unknown": "待核对",
        "blocked": "受阻",
        "failed": "失败",
        "cancelled": "已取消",
    }
    lines = [f"- {at} · {title or '稿件'} · {labels.get(state, state)}" for at, title, state in rows]
    return text + "\n\n### 补充发布回执\n\n" + "\n".join(lines) if lines else text
