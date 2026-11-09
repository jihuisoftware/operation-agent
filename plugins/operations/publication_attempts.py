"""Content identity prevents duplicate posts; execution identity makes safe retries independent."""
import json
from datetime import datetime

SUCCEEDED = {'published', 'confirmed'}
PENDING = {'queued', 'executing', 'submitted', 'unknown'}
TERMINAL_UNSENT = {'cancelled', 'failed', 'blocked', 'confirmed_not_published'}


def execution_target(store, action):
    target = action['target']
    if store.manual_run_id:
        return f'manual:{store.manual_run_id}:{target}'
    content = action.get('content') or {}
    if action.get('human_review') and content.get('id'):
        return f"release:{content['id']}:{action['human_review']}:{target}"
    if store.current_run_id:
        return f'run:{store.current_run_id}:{target}'
    return target


def rows(db, action):
    return [dict(row) for row in db.execute("SELECT * FROM actions WHERE kind='publish' "
            "AND json_extract(data,'$.account_id')=? AND json_extract(data,'$.target')=? ORDER BY created,id",
            (action['account_id'], action['target']))]


def started(db, command, after=None):
    return bool(db.execute("SELECT 1 FROM objects WHERE kind='browser_step' AND json_extract(data,'$.command_id')=? "
        "AND json_extract(data,'$.name') IN ('submit','submit_interaction') AND json_extract(data,'$.phase')='started' "
        "AND (? IS NULL OR created>?) LIMIT 1", (command['id'], after, after)).fetchone())


def unsent_receipt(result):
    return result.get('submitted') is False and result.get('dispatch_state') in {'not_started', 'read_only'}


def command_unsent(db, command):
    result = json.loads(command['result'])
    publication = result.get('publication') or {}
    if (command['state'] in {'queued', 'running'} or result.get('state') in {'published', 'confirmed', 'submitted'} or result.get('submitted') is True
            or result.get('dispatch_state') == 'submission_started'
            or publication.get('platform') in {'published', 'reviewing'}
            or publication.get('execution') in {'submitted', 'verified'} or started(db, command)):
        return False
    return unsent_receipt(result) or command['worker'] is None


def manually_cleared(db, action, command, commands):
    verified = json.loads(action['result']).get('manual_verification') or {}
    if verified.get('state') != 'confirmed_not_published' or not verified.get('at'):
        return False
    if started(db, command, verified['at']):
        return False
    boundary = next((row for row in commands if row['id'] == verified.get('command_id')), None)
    if boundary:
        return command['rowid'] <= boundary['rowid']
    # Legacy conclusions lack a command id. The first attempt and timestamped manual retries
    # can still be bound to the operator's conclusion; unidentifiable attempts stay blocked.
    if command['id'] == commands[0]['id']:
        at = action['created']
    else:
        row = db.execute("SELECT at FROM events WHERE kind='manual_retry' AND json_extract(data,'$.command_id')=? ORDER BY id LIMIT 1", (command['id'],)).fetchone()
        at = row[0] if row else None
    try:
        return bool(at and datetime.fromisoformat(at) <= datetime.fromisoformat(verified['at']))
    except (ValueError, TypeError):
        return False


def unsubmitted(db, action):
    if action['state'] not in TERMINAL_UNSENT:
        return False
    commands = [dict(row) for row in db.execute("SELECT rowid,* FROM commands WHERE action_id=? AND kind='publish' ORDER BY rowid", (action['id'],))]
    if any(row['state'] in {'queued', 'running'} for row in commands):
        return False
    if action['state'] == 'confirmed_not_published':
        return True
    if not commands:
        return unsent_receipt(json.loads(action['result']))
    return all(command_unsent(db, command) or manually_cleared(db, action, command, commands) for command in commands)


def guard(db, action, *, skip=None, scope=None):
    from .action_admission import ActionDeferred
    history = rows(db, action)
    for row in sorted(history, key=lambda item: item['state'] not in SUCCEEDED):
        if row['id'] == skip:
            continue
        if row['state'] in SUCCEEDED:
            raise ActionDeferred(row, publication=True, scope=scope, completed=True)
        if not unsubmitted(db, row):
            raise ActionDeferred(row, publication=True, scope=scope)
    return history


def quota(db, action, day):
    count = db.execute("SELECT count(DISTINCT json_array(json_extract(data,'$.account_id'),json_extract(data,'$.target'))) "
                       "FROM actions WHERE kind='publish' AND day=? AND state!='cancelled'", (day,)).fetchone()[0]
    reserved = db.execute("SELECT 1 FROM actions WHERE kind='publish' AND day=? AND state!='cancelled' "
                          "AND json_extract(data,'$.account_id')=? AND json_extract(data,'$.target')=? LIMIT 1",
                          (day, action['account_id'], action['target'])).fetchone()
    return count, bool(reserved)
