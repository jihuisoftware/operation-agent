"""Reserve publication instants under the same attached directory write lock as manuscript approval."""

from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta, UTC
import json
import sqlite3
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .daily_tasks import valid_clock
from .store import encoded


def approval_policy(policy):
    import hashlib

    retained = {
        k: v
        for k, v in policy.items()
        if k not in ("enabled", "paused", "times", "work_start", "work_end", "draft_goal", "inbox_interval")
    }
    retained["modules"] = {k: v for k, v in policy["modules"].items() if k != "publish"}
    retained["limits"] = {k: v for k, v in policy["limits"].items() if k != "publish"}
    return hashlib.sha256(encoded(retained).encode()).hexdigest()


def account_key(store, db):
    if store.workspace:
        return db.execute(
            "SELECT account FROM directory.businesses WHERE id=?", (store.scope["business_id"],)
        ).fetchone()[0]
    return "local"


def settings(store, db, policy):
    key = "publish-calendar:" + account_key(store, db)
    row = db.execute(
        "SELECT data FROM directory.preferences WHERE id=?"
        if store.workspace
        else "SELECT data FROM objects WHERE id=?",
        (key,),
    ).fetchone()
    if row:
        return json.loads(row[0])
    limits = (
        json.loads(db.execute("SELECT data FROM directory.preferences WHERE id='limits'").fetchone()[0])
        if store.workspace
        else policy["limits"]
    )
    return {
        "timezone": limits.get("_timezone", policy["timezone"]),
        "slots": ["10:00"],
        "limit": limits["publish"],
        "revision": 0,
    }


def configure(store, body):
    _, policy = store.policy()
    slots, limit = body.get("slots"), body.get("limit")
    if not isinstance(slots, list) or len(slots) > 48 or not all(valid_clock(s) for s in slots):
        raise ValueError("发布时间应为 HH:MM，每账号最多 48 个时段")
    if type(limit) is not int or not 0 <= limit <= 1000:
        raise ValueError("账号每日发布额度应为 0 至 1000")
    try:
        ZoneInfo(body.get("timezone"))
    except (ZoneInfoNotFoundError, TypeError, ValueError) as exc:
        raise ValueError("请选择有效时区") from exc
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        current = settings(store, db, policy)
        account = account_key(store, db)
        if body.get("revision") != current["revision"] or body.get("account") != account:
            raise ValueError("账号或发布设置已变化，请刷新")
        value = {
            "revision": current["revision"] + 1,
            "timezone": body["timezone"],
            "slots": sorted(set(slots)),
            "limit": limit,
        }
        args = ("publish-calendar:" + account, encoded(value))
        if store.workspace:
            db.execute("INSERT OR REPLACE INTO directory.preferences(id,data) VALUES (?,?)", args)
        else:
            from .policy import now_iso

            db.execute(
                "INSERT OR REPLACE INTO objects VALUES (?, 'account_calendar', ?, ?)", (*args, now_iso())
            )
    return {**value, "account": account}


def entries(db):
    rows = db.execute("""SELECT data FROM objects WHERE kind='content_release'
        AND json_extract(data,'$.state') IN ('scheduled','waiting_slot')
        AND NOT EXISTS (SELECT 1 FROM actions WHERE kind='publish' AND json_extract(actions.data,'$.content.id')=json_extract(objects.data,'$.content_id'))""")
    return [json.loads(row[0]) for row in rows]


def peers(store, db, account, read):
    if not store.workspace:
        return []
    rows = db.execute(
        """SELECT file,(t.archived=0 AND b.archived=0 AND b.paused=0) FROM directory.topics t JOIN directory.businesses b ON b.id=t.business_id
        WHERE t.id!=? AND b.account=?""",
        (store.scope["id"], account),
    )
    result = []
    for row in rows:
        path = store.workspace.root / row[0]
        if path.exists():
            with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as peer:
                if peer.execute("SELECT 1 FROM sqlite_master WHERE name='objects'").fetchone():
                    result.extend(read(peer, bool(row[1])))
    return result


def competing_entries(db, account, active_scope):
    current = db.execute("SELECT version,data FROM settings WHERE id=1").fetchone()
    policy = json.loads(current[1])
    active = (
        active_scope
        and policy["enabled"]
        and not policy["paused"]
        and policy["modules"]["publish"]
        and policy["limits"]["publish"] > 0
    )
    return [
        r
        for r in entries(db)
        if r.get("account_scope", account) == account
        and (r["state"] == "scheduled" or active and r.get("version", current[0]) == current[0])
    ]


def queue(store, db):
    account = account_key(store, db)

    def summary(connection, _active_scope=True):
        rows = connection.execute("""SELECT r.data,json_extract(c.data,'$.title') FROM objects r LEFT JOIN objects c
            ON c.id=json_extract(r.data,'$.content_id') WHERE r.kind='content_release'
            AND json_extract(r.data,'$.state') IN ('waiting_slot','scheduled')""")
        result = []
        for raw, title in rows:
            release = json.loads(raw)
            if release.get("account_scope") and release["account_scope"] != account:
                continue
            result.append(
                {
                    **{
                        k: release.get(k)
                        for k in (
                            "content_id",
                            "topic_id",
                            "business_id",
                            "publish_at",
                            "reviewed_at",
                            "detail",
                        )
                    },
                    "title": title,
                }
            )
        return result

    return sorted(
        summary(db) + peers(store, db, account, summary),
        key=lambda r: (r["publish_at"] or "9999", r["reviewed_at"] or "", r["content_id"]),
    )


def used_days(store, db, zone, account):
    def attempts(conn, _active_scope=True):
        return [
            row[0]
            for row in conn.execute("""SELECT min(created) FROM actions WHERE kind='publish'
            AND state!='cancelled' GROUP BY coalesce(json_extract(data,'$.publication_reservation_id'),id)""")
        ]

    stamps = attempts(db) + peers(store, db, account, attempts)
    return Counter(datetime.fromisoformat(stamp).astimezone(zone).date() for stamp in stamps)


def quota_available(store, db, policy, now):
    config = settings(store, db, policy)
    if config["revision"] == 0:
        return True  # Existing topic and shared limits already guard uncustomized accounts.
    zone = ZoneInfo(config["timezone"])
    return used_days(store, db, zone, account_key(store, db))[now.astimezone(zone).date()] < config["limit"]


def enforce_limit(store, db, policy):
    now = getattr(store, "execution_now", None) or datetime.now(UTC)
    if not quota_available(store, db, policy, now):
        raise ValueError("已达到账号每日发布额度")


def allocation(store, db, policy, now, release):
    config = settings(store, db, policy)
    if (
        not policy["enabled"]
        or policy["paused"]
        or not policy["modules"]["publish"]
        or (store.workspace and store.workspace.blocked(store.scope))
    ):
        return None, "发布已暂停，等待恢复"
    if not config["slots"] or not config["limit"] or not policy["limits"]["publish"]:
        return None, "等待设置可用的发布时段或额度"
    own = [r for r in entries(db) if r["content_id"] != release["content_id"]]
    account = account_key(store, db)
    others_list = peers(store, db, account, lambda peer, active: competing_entries(peer, account, active))
    ordered = (release["reviewed_at"], release["content_id"])
    if any(
        r["state"] == "waiting_slot" and (r["reviewed_at"], r["content_id"]) < ordered
        for r in own + others_list
    ):
        return None, "等待先审核通过的稿件排期"
    zone = ZoneInfo(config["timezone"])
    topic_zone = ZoneInfo(policy["timezone"])
    local = now.astimezone(zone)

    def stamps(rows):
        return [datetime.fromisoformat(r["publish_at"]) for r in rows if r.get("publish_at")]

    reserved = set(stamps(own + others_list))
    account_days = Counter(s.astimezone(zone).date() for s in stamps(own + others_list))
    account_days.update(used_days(store, db, zone, account))
    topic_days = Counter(s.astimezone(topic_zone).date() for s in stamps(own))
    if store.workspace:
        shared = json.loads(
            db.execute("SELECT data FROM directory.preferences WHERE id='limits'").fetchone()[0]
        )
        shared_zone = ZoneInfo(shared.get("_timezone", policy["timezone"]))
        shared_days = Counter(s.astimezone(shared_zone).date() for s in stamps(own + others_list))
        for charged_day, count in db.execute(
            "SELECT day,sum(amount) FROM directory.charges WHERE kind='publish' AND account_id=? GROUP BY day",
            (account,),
        ):
            shared_days[datetime.fromisoformat(charged_day).date()] += count
    from .automatic_schedule import capacity

    for offset in range(366):
        day = local.date() + timedelta(days=offset)
        for clock in config["slots"]:
            slot = datetime.fromisoformat(f"{day}T{clock}").replace(tzinfo=zone)
            utc = slot.astimezone(UTC)
            if (
                utc <= now
                or utc in reserved
                or utc.astimezone(zone).replace(tzinfo=None) != slot.replace(tzinfo=None)
            ):
                continue
            if store.workspace and shared_days[slot.astimezone(shared_zone).date()] >= shared["publish"]:
                continue
            topic_day = slot.astimezone(topic_zone).date()
            if account_days[day] < config["limit"] and topic_days[topic_day] < capacity(
                store, policy, topic_day.isoformat(), db, at=slot
            ):
                return utc.isoformat(), ""
    return None, "当前可排日期额度已满，等待下一个可用时段"


def assign(store, db, policy, now, release):
    stamp, reason = allocation(store, db, policy, now, release)
    release.update(state="scheduled" if stamp else "waiting_slot", publish_at=stamp, detail=reason)


def drain(store, now):
    version, policy = store.policy()
    with store.connection() as db:
        if not db.execute(
            "SELECT 1 FROM objects WHERE kind='content_release' AND json_extract(data,'$.state')='waiting_slot' LIMIT 1"
        ).fetchone():
            return
        db.execute("BEGIN IMMEDIATE")
        waiting = sorted(
            (r for r in entries(db) if r["state"] == "waiting_slot"),
            key=lambda r: (r["reviewed_at"], r["content_id"]),
        )
        for row in waiting:
            if row.get("reviewer") == "human" and row.get("approval_policy") == approval_policy(policy):
                row["version"] = version
            if row.get("version", version) != version:
                row.update(state="needs_attention", detail="运营规则已变化，请重新审核")
            elif row.get("account_scope") and row["account_scope"] != account_key(store, db):
                row.update(state="needs_attention", detail="关联账号已变更，请重新审核")
            else:
                assign(store, db, policy, now, row)
            db.execute(
                "UPDATE objects SET data=? WHERE id=?", (encoded(row), "content-release:" + row["content_id"])
            )
