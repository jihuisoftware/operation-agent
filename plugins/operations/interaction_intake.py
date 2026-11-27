"""Complete the due inbox reads before an engagement stage can propose or send actions."""

from datetime import datetime
from zoneinfo import ZoneInfo

from .collection_ledger import load, save
from .message_intake import scan_enabled

STAGES = {"reply": "comments", "dm": "dm", "follow": "follow"}


def inventory(store, policy, day, kind, account, *, receiving=False):
    from .workflow import browser

    payload = {"kind": kind, "account_id": account, "keywords": policy["keywords"]}
    if receiving:
        payload["interaction_phase"] = "receive"
    result = browser(store, "inbox", payload)
    if not isinstance(result.get("items"), list):
        raise ValueError("读取平台列表未返回明确结果")
    missing = result.get("unidentified", 0) + result.get("unknownDirection", 0)
    if missing:
        store.event(
            "inventory_warning",
            {
                "day": day,
                "kind": kind,
                "count": missing,
                "reason": "部分网页条目缺少稳定标识或收发方向，已跳过",
            },
        )
    if result.get("evidence"):
        store.event("inventory", {"day": day, "kind": kind, "evidence": result["evidence"]})
    return result


def _slots(store, policy, kinds, account, version):
    selected = {kind: None for kind in STAGES if kind in kinds and scan_enabled(store, policy, kind)}
    if getattr(store, "debug_id", None):
        return _debug_slots(store, policy, kinds, selected)
    if not getattr(store, "current_run_id", None):
        return selected
    with store.connection() as db:
        run = db.execute("SELECT day,stage,slot FROM runs WHERE id=?", (store.current_run_id,)).fetchone()
    if not run or run["stage"] not in STAGES.values():
        return selected
    slot = run["slot"].split(":resume:", 1)[0]
    if slot.startswith('poll:'):
        return {kind: (run['day'], slot) for kind, stage in STAGES.items()
                if policy['modules'][stage] and scan_enabled(store, policy, kind)}
    if slot == 'daily:outreach':
        return {}
    if slot.startswith("manual:"):
        due = {stage: (run["day"], slot) for stage in STAGES.values() if policy["modules"][stage]}
    else:
        from .occurrences import latest_due

        stamp = datetime.fromisoformat(f"{run['day']}T{slot}").replace(tzinfo=ZoneInfo(policy["timezone"]))
        now = getattr(store, "execution_now", None) or stamp
        due = {
            stage: (at.date().isoformat(), at.strftime("%H:%M"))
            for stage, at in latest_due(store, policy, now).items()
        }
    due[run["stage"]] = (run["day"], slot)
    return _participating(store, policy, run["stage"], due, selected, account, version)


def _debug_slots(store, policy, kinds, selected):
    batch = load(store, store.debug_id) or {}
    if not batch.get("steps") or not set(kinds).intersection(("comment", "reply", "dm", "follow")):
        return selected
    # A future debug step cannot lend its one-shot grant to the current step.
    planned = {
        step["id"] for step in batch["steps"] if step["state"] not in ("completed", "cancelled", "skipped")
    }
    return {
        kind: (batch["day"], store.debug_id)
        for kind in STAGES
        if kind in selected
        or (kind in planned and policy["allowed"][kind] and scan_enabled(store, policy, kind))
    }


def _key(store, version, date, slot, kind, account):
    import hashlib
    from .store import encoded

    account_slot = (store.scope or {}).get("account")
    return (
        "inbox-scan:"
        + hashlib.sha256(encoded([version, date, slot, kind, account, account_slot]).encode()).hexdigest()
    )


def _participating(store, policy, current_stage, due, selected, account, version):
    from .blueprints import requirements

    slots = {}
    with store.connection() as db:
        for kind, stage in STAGES.items():
            if stage not in due or not scan_enabled(store, policy, kind):
                continue
            date, slot = due[stage]
            if stage != current_stage:
                existing = db.execute(
                    "SELECT state FROM runs WHERE day=? AND stage=? AND slot=?", (date, stage, slot)
                ).fetchone()
                if existing:
                    if existing[0] == "cancelled" or due[stage] != due[current_stage]:
                        continue
                    # Completed legacy runs have no scan receipt and must not be replayed.
                    prior = load(store, _key(store, version, date, slot, kind, account))
                    if not prior or prior["state"] == "complete":
                        continue
                if requirements(policy, stage, []):
                    continue
            elif kind not in selected:
                continue
            slots[kind] = (date, slot)
    return slots


def _scan(store, policy, day, kind, account):
    from .messages import read_items, pending
    from .message_intake import automatic_reply

    items = inventory(store, policy, day, kind, account, receiving=True)["items"]
    if any(not isinstance(i.get("id"), str) or not i["id"].strip() for i in items):
        store.event("inventory_warning", {"kind": kind, "day": day, "reason": "存在缺少平台标识的条目，已跳过"})
    auto = automatic_reply(store, policy, kind)
    observed = read_items(store, kind, account, items, auto=auto, day=day)
    if not auto:
        pending(store, account, kind, auto=False)
    store.event("message_scan", {"kind": kind, "day": day, "count": len(items)})
    store.progress({"reply": "接收评论完成", "dm": "接收私信完成", "follow": "接收关注完成"}[kind], {"读取条目": len(items)})
    return {item["id"] for item in observed}


def receive(store, policy, day, version, kinds, account):
    from .execution_pause import ExecutionPaused

    slots = _slots(store, policy, kinds, account, version)
    visible, failures = {}, []
    for kind, occurrence in slots.items():
        key = None
        if occurrence:
            date, slot = occurrence
            key = _key(store, version, date, slot, kind, account)
        previous = load(store, key) if key else None
        if previous and previous["state"] == "complete":
            visible[kind] = set(previous["visible"])
            continue
        if previous and previous["state"] == "paused" and not getattr(store, "resume_attempt", 0):
            failures.append(previous["reason"])
            continue
        try:
            visible[kind] = _scan(store, policy, day, kind, account)
            if key:
                save(store, "inbox_scan", key, {"state": "complete", "visible": sorted(visible[kind])})
        except ExecutionPaused as exc:
            if key:
                save(store, "inbox_scan", key, {"state": "paused", "reason": str(exc)})
            raise
        except ValueError as exc:
            if key:
                save(store, "inbox_scan", key, {"state": "failed", "reason": str(exc)})
            failures.append(str(exc))
            store.event("interaction_error", {"kind": kind, "day": day, "error": str(exc)})
    if failures:
        raise ValueError("收件未完成，本轮不发送互动：" + "；".join(failures))
    return visible
