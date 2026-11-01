"""One latest due occurrence per module, shared by execution and its UI projections."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .modules import TIMES


def latest_due(store, policy, now):
    local = now.astimezone(ZoneInfo(policy['timezone']))
    with store.connection() as db:
        first = db.execute("SELECT min(at) FROM events WHERE kind='policy'").fetchone()[0]
    first_day = datetime.fromisoformat(first).astimezone(local.tzinfo).date() if first else local.date()
    result = {}
    for stage in TIMES:
        if not policy['modules'][stage]:
            continue
        candidates = []
        for offset in (-1, 0):
            day = local.date() + timedelta(days=offset)
            if offset < 0 and day < first_day:
                continue
            for slot in policy['times'][stage]:
                due = datetime.fromisoformat(f'{day}T{slot}').replace(tzinfo=local.tzinfo)
                if due <= local:
                    candidates.append(due)
        if candidates:
            # Select BEFORE consulting history: a completed/cancelled latest slot must
            # never expose an older slot as the next catch-up candidate.
            result[stage] = max(candidates)
    return result


def visible_occurrences(store, policy, now):
    local = now.astimezone(ZoneInfo(policy['timezone']))
    candidates = list(latest_due(store, policy, now).items())
    for offset in (0, 1):
        day = local.date() + timedelta(days=offset)
        for stage in TIMES:
            if not policy['modules'][stage]:
                continue
            for slot in sorted(set(policy['times'][stage])):
                due = datetime.fromisoformat(f'{day}T{slot}').replace(tzinfo=local.tzinfo)
                if due > local:
                    candidates.append((stage, due))
    return candidates
