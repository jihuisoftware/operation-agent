"""Continue proved-unsubmitted actions without resetting identities, budgets or subtask progress."""
import json
import time
import uuid

from .execution_pause import identity, load
from .store import encoded

KINDS = {'comments': ('comment', 'reply'), 'publish': ('publish',), 'comment': ('comment',),
         'reply': ('reply',), 'dm': ('dm',), 'follow': ('follow',)}


def _belongs(store, data, original_run):
    if store.manual_run_id:
        return data.get('manual_run_id') == store.manual_run_id
    return data.get('resume_key') == identity(store) or data.get('run_id') in {identity(store), original_run}


def _kinds(store, task, original_run):
    kinds = KINDS.get(task, ())
    if task != 'comments':
        return kinds
    with store.connection() as db:
        row = db.execute("SELECT json_extract(payload,'$.kind') AS kind FROM commands "
                         "WHERE json_extract(payload,'$.run_id')=? AND json_extract(payload,'$.kind') IN ('comment','reply') "
                         'ORDER BY rowid DESC LIMIT 1', (original_run,)).fetchone()
    return kinds[kinds.index(row['kind']):] if row else kinds


def _proved_unsubmitted(db, row, result):
    if result.get('submitted') is not False:
        return False
    if result.get('dispatch_state') in {'not_started', 'read_only'}:
        return True
    if result.get('dispatch_state') == 'submission_started':
        return False
    command = db.execute('SELECT id FROM commands WHERE action_id=? ORDER BY rowid DESC LIMIT 1', (row['id'],)).fetchone()
    return not command or not db.execute("SELECT 1 FROM objects WHERE kind='browser_step' AND json_extract(data,'$.command_id')=? "
        "AND json_extract(data,'$.name') IN ('submit','submit_interaction') AND json_extract(data,'$.phase')='started'", (command['id'],)).fetchone()


def _continue_action(store, row, data, policy, day, version):
    if row['version'] != version or row['day'] != day:
        raise ValueError('待恢复动作的日期或规则已变化')
    from .debug_authorization import allowed
    from .policy import permitted
    effective = {**policy, 'allowed': {**policy['allowed'], row['kind']: allowed(store, policy, row['kind'])}}
    if data.get('human_review'):
        from .content_release import authorization
        with store.connection() as db:
            effective['allowed'][row['kind']] = authorization(store, db, data, version, policy)
    reason = permitted(effective, data)
    if reason:
        raise ValueError(reason)
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        current = db.execute('SELECT * FROM actions WHERE id=?', (row['id'],)).fetchone()
        if current['state'] not in {'blocked', 'confirmed_not_published'} or not _proved_unsubmitted(db, current, json.loads(current['result'])):
            raise ValueError('原动作提交证据不明确或状态已变化，请先核对，不能自动重发')
        from .action_admission import check_replay
        check_replay(store, db, data, row['id'])
        from .publication_snapshot import capture
        data = capture(db, {**data, 'resume_key': identity(store)}, version, effective)
        from .browser_evidence import command_context
        payload = {**data, **command_context(store), 'policy_version': version}
        kind = 'publish' if row['kind'] == 'publish' else 'interact'
        db.execute("UPDATE actions SET state='queued',data=? WHERE id=?", (encoded(data), row['id']))
        db.execute("INSERT INTO commands VALUES (?,?,?,?,'queued',NULL,?,'{}')",
                   (uuid.uuid4().hex, row['id'], kind, encoded(payload), time.time() + 120))
        from .workspace_execution import sync_actions
        sync_actions(store, db)
    from .workflow import browser
    return browser(store, kind, payload, row['id'])


def continue_actions(store, task, policy, day, version):
    if not getattr(store, 'resume_attempt', 0) or task not in KINDS:
        return None
    pause = load(store, identity(store))
    original_run = (pause or {}).get('run_id')
    kinds = _kinds(store, task, original_run)
    with store.connection() as db:
        rows = db.execute("SELECT * FROM actions WHERE state IN ('blocked','confirmed_not_published') ORDER BY created,rowid").fetchall()
    results, resumed = [], set()
    for row in rows:
        data = json.loads(row['data'])
        if row['kind'] not in kinds or not _belongs(store, data, original_run):
            continue
        results.append(_continue_action(store, row, data, policy, day, version))
        resumed.add(row['kind'])
    if task == 'comments' and (results or kinds != KINDS[task]):
        remaining = tuple(kind for kind in kinds if kind not in resumed)
        if remaining:
            from .workflow import interact
            from .outcomes import StageSkipped
            try:
                results.extend(interact(store, policy, day, version, kinds=remaining))
            except StageSkipped as exc:
                store.event('interaction_resume_skipped', {'day': day, 'kinds': remaining, 'detail': str(exc)})
                if not results:
                    raise
    if not results:
        return None
    return results[0] if task == 'publish' else results
