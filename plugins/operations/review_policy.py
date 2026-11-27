"""Topic-local review choices, independent of the operating policy version."""
import json
from .store import encoded
from .policy import now_iso

DEFAULT = {'mode': 'manual', 'threshold': 85, 'revision': 0}
MODES = {'manual', 'automatic', 'score'}


def read(db):
    row = db.execute("SELECT data FROM objects WHERE id='review-policy' AND kind='review_policy'").fetchone()
    return json.loads(row[0]) if row else dict(DEFAULT)


def get(store):
    with store.connection() as db:
        return read(db)


def update(store, body):
    if not isinstance(body.get('mode'), str) or body.get('mode') not in MODES or type(body.get('threshold')) is not int or not 0 <= body['threshold'] <= 100:
        raise ValueError('审核模式或评分门槛无效')
    if type(body.get('expected_revision')) is not int:
        raise ValueError('审核策略修订号无效')
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        previous = read(db)
        if previous['revision'] != body['expected_revision']:
            raise ValueError('审核策略已变化，请刷新后重试')
        if (previous['mode'], previous['threshold']) == (body['mode'], body['threshold']):
            return previous
        value = {k: body[k] for k in ('mode', 'threshold')}
        value.update(revision=previous['revision'] + 1, updated_at=now_iso())
        db.execute("INSERT OR REPLACE INTO objects VALUES ('review-policy','review_policy',?,?)", (encoded(value), now_iso()))
        # Submitted/unknown work retains its evidence. Only unsubmitted automatic releases are revoked.
        rows = db.execute("SELECT id,data FROM objects WHERE kind='content_release' AND json_extract(data,'$.reviewer')='automatic'").fetchall()
        for row in rows:
            release = json.loads(row['data'])
            active = db.execute("SELECT 1 FROM actions WHERE kind='publish' AND json_extract(data,'$.content.id')=? AND state NOT IN ('queued','cancelled','confirmed_not_published','failed','blocked')", (release['content_id'],)).fetchone()
            if release['state'] in ('scheduled','waiting_slot') and not active:
                db.execute("UPDATE commands SET state='cancelled' WHERE state='queued' AND action_id IN (SELECT id FROM actions WHERE kind='publish' AND json_extract(data,'$.content.id')=? AND state='queued')", (release['content_id'],))
                db.execute("UPDATE actions SET state='cancelled' WHERE kind='publish' AND json_extract(data,'$.content.id')=? AND state='queued'", (release['content_id'],))
                release.update(state='cancelled', revision=release['revision'] + 1, detail='审核策略已变化，等待重新审核')
                db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(release), row['id']))
        invalidate_waiting(db)
    store.event('review_policy_changed', value)
    return value


def hold_manuscript(db, identity, reason):
    row = db.execute("SELECT data FROM objects WHERE kind='content' AND id=?", (identity,)).fetchone()
    if row:
        content = json.loads(row[0])
        content['review_control_revision'] = content.get('review_control_revision', 0) + 1
        if content.get('automatic_review'):
            content['automatic_review'].update(approved=False, reason=reason)
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(content), identity))


def invalidate_waiting(db):
    candidates = db.execute("SELECT c.id FROM objects c WHERE c.kind='content' AND json_extract(c.data,'$.automatic_review.approved')=1 "
        "AND NOT EXISTS(SELECT 1 FROM actions a WHERE a.kind='publish' AND json_extract(a.data,'$.content.id')=c.id AND a.state NOT IN ('queued','cancelled','confirmed_not_published','failed','blocked')) "
        "AND NOT EXISTS(SELECT 1 FROM objects r WHERE r.id='content-release:'||c.id AND json_extract(r.data,'$.reviewer')='human' AND json_extract(r.data,'$.state')!='cancelled')").fetchall()
    for candidate in candidates:
        hold_manuscript(db, candidate['id'], '审核策略已变化，等待重新检查或人工审核')
