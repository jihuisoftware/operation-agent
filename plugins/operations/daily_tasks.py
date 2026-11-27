"""Daily work is claimed through the existing topic run ledger, independently of the minute it starts."""

from datetime import datetime, timedelta, UTC
import hashlib
import json
import re
from zoneinfo import ZoneInfo

from .policy import local_day
from .topics import catalog

INTERNAL = ("research", "organize", "analytics", "industry", "topics", "content")
INBOX = {"comments": "reply", "dm": "dm", "follow": "follow"}


def valid_clock(value):
    return isinstance(value, str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value) is not None


def validate(policy):
    if (
        not all(valid_clock(policy[key]) for key in ("work_start", "work_end"))
        or policy["work_start"] >= policy["work_end"]
    ):
        raise ValueError("运营时段需在同一天内，结束时间应晚于开始时间")
    for key, label, maximum in [
        ("draft_goal", "每日新稿目标", 100),
        ("inbox_interval", "收件间隔（分钟）", 1440),
    ]:
        if type(policy[key]) is not int or not 1 <= policy[key] <= maximum:
            raise ValueError(f"{label}应为 1 至 {maximum} 的整数")


def signature(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def record_draft(store, db, row):
    if (
        getattr(store, "debug_id", None)
        or not (row.get("production_input") or row.get("manual"))
        or row.get("state") not in ("pending_review", "needs_review")
        or row.get("review_pending")
    ):
        return
    root = row.get("revision_root_id") or row["id"]
    lineage = db.execute(
        "SELECT json_extract(data,'$.debug_id'),json_extract(data,'$.draft_mode') FROM objects WHERE id=?",
        (root,),
    ).fetchone()
    if not lineage or lineage[0] or lineage[1] == "new_variant":
        return
    from .policy import now_iso

    key = "daily-draft:" + root
    data = {
        "day": row["day"],
        "root": root,
        "topic": (row.get("selected_topic") or {}).get("title") or row["title"],
    }
    db.execute(
        "INSERT OR IGNORE INTO objects VALUES (?, 'daily_draft', ?, ?)", (key, json.dumps(data), now_iso())
    )


def manuscripts(store, day):
    # Root versions count once, even if a child later needs a new cover or is published.
    with store.connection() as db:
        rows = db.execute(
            """SELECT id,json_extract(data,'$.revision_root_id'),json_extract(data,'$.selected_topic.title'),
            json_extract(data,'$.title'),json_extract(data,'$.ready'),json_extract(data,'$.state'),json_extract(data,'$.review_pending')
            FROM objects WHERE kind='content' AND json_extract(data,'$.day')=?
            AND (json_extract(data,'$.production_input') IS NOT NULL OR json_extract(data,'$.manual')=1) AND json_extract(data,'$.debug_id') IS NULL
            AND coalesce(json_extract(data,'$.draft_mode'),'reuse')!='new_variant'
            AND NOT EXISTS(SELECT 1 FROM objects root WHERE root.id=json_extract(objects.data,'$.revision_root_id')
                AND (json_extract(root.data,'$.debug_id') IS NOT NULL OR json_extract(root.data,'$.draft_mode')='new_variant'))""",
            (day,),
        ).fetchall()
    used = {
        (row[2] or row[3]).strip().casefold() for row in rows if not row[6] and row[5] != "needs_material"
    }
    completed = {
        row[1] or row[0]
        for row in rows
        if row[4] or row[5] in ("needs_review", "pending_review") and not row[6]
    }
    with store.connection() as db:
        for row in db.execute(
            "SELECT json_extract(data,'$.root'),json_extract(data,'$.topic') FROM objects WHERE kind='daily_draft' AND json_extract(data,'$.day')=?",
            (day,),
        ):
            completed.add(row[0])
            used.add(row[1].strip().casefold())
    return completed, used


def choose_topic(store, policy, day):
    data = catalog(store, policy, day)
    _, used = manuscripts(store, day)
    choices = [data["selected"]] if data["selected"] else []
    choices.extend(
        {**item, "brief_id": data["brief_id"], "origin": "recommended"} for item in data["candidates"]
    )
    return next((row for row in choices if row["title"].strip().casefold() not in used), None)


def material_state(store, day, policy):
    with store.connection() as db:
        rows = db.execute(
            """SELECT kind,id,json_extract(data,'$.text_revision'),json_extract(data,'$.fingerprint'),
            json_extract(data,'$.authorized'),json_extract(data,'$.revoked'),json_extract(data,'$.enabled')
            FROM objects WHERE kind IN ('source','organized_source','analytics_report','industry_report','task','asset','source_pin')
            AND (json_extract(data,'$.scope_topic') IS NULL OR json_extract(data,'$.scope_topic')=?)
            AND (kind!='asset' OR (coalesce(json_extract(data,'$.generated_typography'),0)=0
            AND coalesce(json_extract(data,'$.generated_magazine'),0)=0 AND coalesce(json_extract(data,'$.designer_cover'),0)=0
            AND coalesce(json_extract(data,'$.designer_background'),0)=0 AND coalesce(json_extract(data,'$.generated_visual_art'),0)=0))
            ORDER BY kind,id""",
            (policy["topic"],),
        )
        groups = {}
        for row in rows:
            groups.setdefault(row[0], []).append(tuple(row[1:]))
        return {key: signature(values) for key, values in groups.items()}


def internal_slots(store, policy, day):
    state = material_state(store, day, policy)
    deps = {
        "research": (),
        "organize": ("source", "source_pin", "organized_source"),
        "analytics": ("organized_source",),
        "industry": ("analytics_report",),
        "topics": ("organized_source", "industry_report"),
    }
    for stage, inputs in deps.items():
        if policy["modules"][stage]:
            yield stage, "daily:" + signature([state.get(key) for key in inputs])
    if not policy["modules"]["content"]:
        return
    completed, used = manuscripts(store, day)
    if len(completed) >= policy["draft_goal"]:
        return
    topic = choose_topic(store, policy, day)
    if not topic and (policy["modules"]["topics"] or used):
        return
    yield (
        "content",
        "daily:" + signature([topic, state.get("organized_source"), state.get("asset"), state.get("task")]),
    )


def period(policy, now):
    local = now.astimezone(ZoneInfo(policy["timezone"]))
    clock = local.strftime("%H:%M")
    return local, policy["work_start"] <= clock < policy["work_end"]


def remember_day(store, day, policy):
    from .collection_ledger import load, save

    key = "daily-plan:" + day
    previous = load(store, key)
    state = {"day": day, "goal": policy["draft_goal"], "end": policy["work_end"]}
    if not previous or any(previous.get(k) != v for k, v in state.items()):
        save(store, "daily_plan", key, state)


def candidates(store, policy, now):
    local, open_now = period(policy, now)
    day = local.date().isoformat()
    if policy["modules"]["report"]:
        with store.connection() as db:
            oldest = db.execute(
                """SELECT json_extract(p.data,'$.day') FROM objects p WHERE kind='daily_plan'
                AND json_extract(p.data,'$.day')<=? AND NOT EXISTS (SELECT 1 FROM runs r WHERE
                r.day=json_extract(p.data,'$.day') AND r.stage='report' AND r.slot='daily:close')
                ORDER BY p.id LIMIT 1""",
                (day,),
            ).fetchone()
        if oldest and (oldest[0] < day or local.strftime("%H:%M") >= policy["work_end"]):
            yield oldest[0], "report", "daily:close"
    if not open_now or (policy["deadline"] and day > policy["deadline"][:10]):
        return
    start = datetime.fromisoformat(day + "T" + policy["work_start"]).replace(tzinfo=local.tzinfo)
    bucket = int((local - start).total_seconds() // (60 * policy["inbox_interval"]))
    slot = "poll:" + (start + timedelta(minutes=bucket * policy["inbox_interval"])).strftime("%H:%M")
    from .message_intake import scan_enabled

    inbox = [
        stage
        for stage, kind in INBOX.items()
        if policy["modules"][stage] and scan_enabled(store, policy, kind)
    ]
    with store.connection() as db:
        last = dict(
            db.execute(
                "SELECT stage,max(rowid) FROM runs WHERE day=? AND slot LIKE 'poll:%' GROUP BY stage", (day,)
            )
        )
        internal_last = db.execute(
            "SELECT coalesce(max(rowid),0) FROM runs WHERE day=? AND slot LIKE 'daily:%' AND stage NOT IN ('comments','report')",
            (day,),
        ).fetchone()[0]
        received = db.execute(
            "SELECT 1 FROM runs WHERE day=? AND slot=? AND state IN ('completed','needs_attention') LIMIT 1",
            (day, slot),
        ).fetchone()
    work = list(internal_slots(store, policy, day))
    polls = [(stage, slot) for stage in sorted(inbox, key=lambda stage: last.get(stage, 0))]
    # Alternate between production and inbox work when both remain eligible.
    ordered = polls + work if internal_last > max(last.values(), default=0) else work + polls
    if policy["modules"]["comments"] and policy["allowed"]["comment"] and (not inbox or received):
        ordered.insert(0, ("comments", "daily:outreach"))
    for stage, slot in ordered:
        yield day, stage, slot


def available(store, policy, now):
    from .collection_ledger import load

    seeded = (load(store, "daily-seed:" + local_day(policy, now)) or {}).get("steps", {})
    with store.connection() as db:
        for day, stage, slot in candidates(store, policy, now):
            if day == local_day(policy, now) and slot == seeded.get(stage):
                continue
            prior = db.execute(
                "SELECT state FROM runs WHERE day=? AND stage=? AND slot=?", (day, stage, slot)
            ).fetchone()
            if not prior:
                yield day, stage, slot
            elif stage in INTERNAL:
                attempts = list(
                    db.execute(
                        "SELECT state,slot FROM runs WHERE day=? AND stage=? AND slot GLOB ? ORDER BY rowid",
                        (day, stage, slot + ":retry:*"),
                    )
                )
                last = attempts[-1][0] if attempts else prior[0]
                if last == "interrupted":
                    yield day, stage, slot + f":retry:{len(attempts) + 1}"
                retry = getattr(store, "daily_continue", None)
                if retry and last == "failed" and not any(r[1].endswith(":" + retry) for r in attempts):
                    yield day, stage, slot + ":retry:" + retry


def usage(store, day, policy):
    from .collection_ledger import budget
    from .model_budget_ledger import totals

    with store.connection() as db:
        calls = db.execute(
            "SELECT count(*) FROM events WHERE kind='model_call' AND json_extract(data,'$.day')=? AND coalesce(json_extract(data,'$.quota_exempt'),0)=0",
            (day,),
        ).fetchone()[0]
        tokens = totals(store, db, day)["tokens"]
    by_token = policy["model_budget_mode"] == "tokens"
    return {
        "source": budget(store, day),
        "source_limit": policy["limits"]["source"],
        "model": tokens if by_token else calls,
        "model_limit": policy["model_tokens"] if by_token else policy["model_calls"],
        "unit": "Token" if by_token else "次",
    }


def today(store, now=None):
    now = now or datetime.now(UTC)
    version, policy = store.policy()
    day = local_day(policy, now)
    _, open_now = period(policy, now)
    done, _ = manuscripts(store, day)
    with store.connection() as db:
        runs = [
            dict(r)
            for r in db.execute(
                """SELECT stage,slot,state,detail FROM runs WHERE day=?
            AND (slot LIKE 'daily:%' OR slot LIKE 'poll:%') ORDER BY rowid DESC LIMIT 60""",
                (day,),
            )
        ]
        queue = [
            json.loads(r[0])
            for r in db.execute("""SELECT data FROM objects WHERE kind='content_release'
            AND json_extract(data,'$.state') IN ('scheduled','waiting_slot') ORDER BY created LIMIT 50""")
        ]
    from .readiness import conditions

    setup = conditions(store, policy)
    reasons = {stage: row["reasons"] for stage, row in setup.items() if row["selected"] and row["reasons"]}
    if setup["organize"]["waiting_upstream"] and policy["modules"]["organize"]:
        reasons.setdefault("organize", []).append("等待采集来源")
    if setup["content"]["waiting_upstream"] and policy["modules"]["content"]:
        reasons.setdefault("content", []).append("等待可用的整理资料")
    can_run = any(
        readiness_stage not in reasons and (readiness_stage not in (*INBOX, "publish") or store.online())
        for _, readiness_stage, _ in available(store, policy, now)
    )
    waiting_topic = (
        policy["modules"]["content"]
        and policy["modules"]["topics"]
        and len(done) < policy["draft_goal"]
        and not choose_topic(store, policy, day)
    )
    allowance = usage(store, day, policy)
    if allowance["model"] >= allowance["model_limit"]:
        for stage in ("organize", "industry", "topics", "content"):
            if policy["modules"][stage]:
                reasons.setdefault(stage, []).append(
                    f"模型已用 {allowance['model']}/{allowance['model_limit']} {allowance['unit']}"
                )
    if allowance["source"] >= allowance["source_limit"] and policy["modules"]["research"]:
        reasons.setdefault("research", []).append("已达到每日采集上限")
    local = now.astimezone(ZoneInfo(policy["timezone"]))
    start = datetime.fromisoformat(day + "T" + policy["work_start"]).replace(tzinfo=local.tzinfo)
    minutes = (local - start).total_seconds() // 60
    following = start + timedelta(
        minutes=(minutes // policy["inbox_interval"] + 1) * policy["inbox_interval"]
    )
    if local < start:
        following = start
    elif (
        not open_now or following.date() != local.date() or following.strftime("%H:%M") >= policy["work_end"]
    ):
        following = start + timedelta(days=1)
    return {
        "version": version,
        "day": day,
        "topic": policy["topic"],
        "goal": policy["draft_goal"],
        "completed": len(done),
        "next_poll": following.isoformat() if any(policy["modules"][s] for s in INBOX) else None,
        "usage": allowance,
        "window": [policy["work_start"], policy["work_end"]],
        "can_run": can_run,
        "enabled": policy["enabled"]
        and not policy["paused"]
        and not (store.workspace and store.workspace.blocked(store.scope)),
        "open": open_now,
        "waiting_topic": bool(waiting_topic),
        "reasons": reasons,
        "runs": runs,
        "queue": [
            {
                "content_id": r["content_id"],
                "publish_at": r.get("publish_at"),
                "detail": r.get("detail"),
                "state": r["state"],
            }
            for r in queue
        ],
    }
