"""Small read model for the Profile overview; never load collected source bodies."""
import time

from .blueprints import timeline
from .login_status import catalog as login_catalog
from .policy import local_day, now_iso


def overview(store):
    version, policy = store.policy()
    paused = policy['paused'] or bool(store.workspace and store.workspace.blocked(store.scope))
    day = local_day(policy)
    with store.connection() as db:
        db.execute("BEGIN")
        counts = _counts(db, day)
        pending = _pending(db, day)
        runs = [dict(row) for row in db.execute(
            "SELECT id,stage,state,substr(detail,1,600) AS detail,started,ended FROM runs "
            "WHERE day=? ORDER BY started DESC,rowid DESC LIMIT 6", (day,))]
        publications = [dict(row) for row in db.execute(
            "SELECT id,created,state,json_extract(data,'$.content.title') AS title,"
            "json_extract(data,'$.account_id') AS account_id,json_extract(result,'$.url') AS url "
            "FROM actions WHERE day=? AND kind='publish' AND state IN ('published','confirmed') "
            "ORDER BY created DESC,rowid DESC LIMIT 4", (day,))]
        report = db.execute(
            "SELECT id,created,json_extract(data,'$.day') AS day FROM objects "
            "WHERE kind='report' ORDER BY created DESC,rowid DESC LIMIT 1").fetchone()
        online = bool(db.execute("SELECT 1 FROM workers WHERE seen>?", (time.time() - 15,)).fetchone())
    scheduled = timeline(policy) if policy["enabled"] and not paused else []
    return {
        "day": day, "timezone": policy["timezone"], "updated_at": now_iso(), "version": version,
        "topic": policy["topic"], "goal": policy["goal"], "enabled": policy["enabled"],
        "paused": paused, "online": online, "counts": counts, "pending": pending,
        "runs": runs, "publications": publications, "report": dict(report) if report else None,
        "schedule": sorted(scheduled, key=lambda row: row["next_at"])[:6],
        "analysis": _analysis(store, policy),
        "platforms": login_catalog(store)["platforms"],
    }


def _counts(db, day):
    rows = db.execute(
        "SELECT kind,json_extract(data,'$.state') AS state,count(*) AS n FROM objects "
        "WHERE json_extract(data,'$.day')=? AND kind IN ('source','content') GROUP BY kind,state", (day,))
    counts = {"sources": 0, "sources_read": 0, "content": 0, "topics": 0, "published": 0, "interactions": 0}
    for row in rows:
        if row["kind"] == "source":
            counts["sources"] += row["n"]
            if row["state"] == "read":
                counts["sources_read"] += row["n"]
        else:
            counts["content"] += row["n"]
    brief = db.execute(
        "SELECT json_array_length(data,'$.result.topics') FROM objects WHERE kind='brief' "
        "AND json_extract(data,'$.day')=? ORDER BY created DESC,rowid DESC LIMIT 1", (day,)).fetchone()
    counts["topics"] = (brief[0] or 0) if brief else 0
    for row in db.execute(
        "SELECT kind,count(*) AS n FROM actions WHERE day=? AND state IN ('published','confirmed') GROUP BY kind", (day,)):
        if row["kind"] == "publish":
            counts["published"] += row["n"]
        elif row["kind"] in {"comment", "reply", "dm", "follow"}:
            counts["interactions"] += row["n"]
    counts["model_calls"] = db.execute(
        "SELECT count(*) FROM events WHERE kind='model_call' AND json_extract(data,'$.day')=?", (day,)).fetchone()[0]
    return counts


def _pending(db, day):
    # Categories can refer to the same business item; never sum them into a fake unique total.
    return {
        "unverified": db.execute("SELECT count(*) FROM actions WHERE state IN ('submitted','unknown')").fetchone()[0],
        "failed_today": db.execute("SELECT count(*) FROM runs WHERE day=? AND state='failed'", (day,)).fetchone()[0],
        "inbox": db.execute("SELECT count(*) FROM objects WHERE kind='inbox' AND json_extract(data,'$.state')='needs_review'").fetchone()[0],
        "content": db.execute("SELECT count(*) FROM objects WHERE kind='content' AND json_extract(data,'$.state') IN ('needs_material','needs_review')").fetchone()[0],
    }


def _analysis(store, policy):
    with store.connection() as db:
        return [dict(r) for r in db.execute("SELECT id,kind,json_extract(data,'$.created') AS created,json_extract(data,'$.detail') AS detail "
                "FROM objects WHERE kind IN ('analytics_report','industry_report') AND json_extract(data,'$.scope_topic')=? ORDER BY created DESC LIMIT 2", (policy['topic'],))]
