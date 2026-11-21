"""Automatic reviews use the existing publication ledger; scheduling never submits a post."""
from datetime import datetime, timedelta, UTC
from zoneinfo import ZoneInfo
import json

from .content_release import manuscript, load, review
from .automatic_review import decision_current


def capacity(store, policy, day, db, *, at=None):
    limit = policy['limits']['publish']
    used = db.execute("SELECT count(DISTINCT coalesce(json_extract(data,'$.publication_reservation_id'),id)) FROM actions WHERE kind='publish' AND day=? AND state!='cancelled'", (day,)).fetchone()[0]
    remaining = max(0, limit - used)
    if store.workspace:
        limits = json.loads(db.execute("SELECT data FROM directory.preferences WHERE id='limits'").fetchone()[0])
        account = store.scope['account'] if 'account' in store.scope else store.workspace.resolve(store.scope['business_id'], store.scope['id'])['account']
        instant = at or datetime.fromisoformat(day + 'T12:00:00').replace(tzinfo=ZoneInfo(policy['timezone']))
        shared_day = instant.astimezone(ZoneInfo(limits.get('_timezone', 'Asia/Shanghai'))).date().isoformat()
        charged = db.execute("SELECT coalesce(sum(amount),0) FROM directory.charges WHERE day=? AND kind='publish' AND account_id=?", (shared_day, account)).fetchone()[0]
        remaining = min(remaining, max(0, limits['publish'] - charged))
    return remaining


def next_slot(store, policy, now, *, exclude=None):
    if not policy['times'].get('publish') or policy['limits']['publish'] <= 0:
        return None
    zone = ZoneInfo(policy['timezone'])
    local = now.astimezone(zone)
    with store.connection() as db:
        booked = [json.loads(row[0]) for row in db.execute("SELECT data FROM objects WHERE kind='content_release' AND json_extract(data,'$.state')='scheduled'")]
        booked = [r for r in booked if r['content_id'] != exclude and not db.execute("SELECT 1 FROM actions WHERE kind='publish' AND json_extract(data,'$.content.id')=?", (r['content_id'],)).fetchone()]
        for offset in range(366):
            date = local.date() + timedelta(days=offset)
            stamps = [datetime.fromisoformat(r['publish_at']).astimezone(zone) for r in booked]
            for clock in sorted(policy['times'].get('publish', [])):
                hour, minute = map(int, clock.split(':'))
                stamp = datetime(date.year, date.month, date.day, hour, minute, tzinfo=zone)
                if stamp.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != stamp.replace(tzinfo=None):
                    continue
                if stamp > now and stamp not in stamps and capacity(store, policy, date.isoformat(), db, at=stamp) > sum(s.date() == date for s in stamps):
                    return stamp.astimezone(UTC).isoformat()
    return None


def schedule_one(store, identity, now=None):
    if getattr(store, 'debug_id', None):
        return None
    now = now or getattr(store, 'execution_now', None) or datetime.now(UTC)
    draft = manuscript(store, identity)
    decision = draft.get('automatic_review') or {}
    version, policy = store.policy()
    if not policy['enabled'] or policy['paused'] or not policy['modules']['publish']:
        return None
    with store.connection() as db:
        previous = load(db, identity)
        if previous and previous['state'] != 'cancelled':
            return previous
        if not decision_current(db, draft, decision):
            return None
        if db.execute("SELECT 1 FROM actions WHERE kind='publish' AND json_extract(data,'$.content.id')=?", (identity,)).fetchone():
            return None
    slot = next_slot(store, policy, now)
    if slot is None:
        return None
    try:
        return review(store, identity, {'expected_revision': (previous or {}).get('revision', 0),
                      'version': version, 'content_revision': decision['content_revision'], 'publish_at': slot}, automatic=decision)
    except ValueError as exc:
        store.event('automatic_schedule_waiting', {'content_id': identity, 'reason': str(exc)})
        return None


def schedule_pending(store, now):
    from .review_policy import get
    settings = get(store)
    if settings['mode'] == 'manual':
        return
    with store.connection() as db:
        rows = db.execute("SELECT id FROM objects c WHERE kind='content' "
            "AND json_extract(data,'$.automatic_review.approved')=1 "
            "AND json_extract(data,'$.automatic_review.policy_revision')=? "
            "AND NOT EXISTS(SELECT 1 FROM objects r WHERE r.id='content-release:'||c.id AND json_extract(r.data,'$.state')!='cancelled') "
            "AND NOT EXISTS(SELECT 1 FROM actions a WHERE a.kind='publish' AND json_extract(a.data,'$.content.id')=c.id) "
            "ORDER BY created,id LIMIT 50", (settings['revision'],)).fetchall()
    for row in rows:
        schedule_one(store, row['id'], now)


def defer_for_capacity(store, release, policy, now):
    if release.get('reviewer') != 'automatic':
        return False
    from .policy import local_day
    with store.connection() as db:
        if capacity(store, policy, local_day(policy, now), db, at=now) > 0:
            return False
    slot = next_slot(store, policy, now, exclude=release['content_id'])
    from .store import encoded
    with store.connection() as db:
        current = load(db, release['content_id'])
        if current and current['revision'] == release['revision'] and current['state'] == 'scheduled':
            current.update(detail='额度不足，等待后续可用发布时段')
            if slot:
                current.update(publish_at=slot)
            db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(current), 'content-release:' + release['content_id']))
    return True
