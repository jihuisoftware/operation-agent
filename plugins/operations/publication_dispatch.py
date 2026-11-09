"""Recheck duplicate evidence before claiming a command and before browser steps."""
import json


def check(store, db, command):
    if command['kind'] != 'publish' or not command['action_id']:
        return
    from .publication_attempts import guard
    from .publication_shared import history
    action = json.loads(command['payload'])
    guard(db, action, skip=command['action_id'])
    history(store, db, action)


def admit(store, db, command):
    from .action_admission import ActionDeferred
    from .store import encoded
    try:
        check(store, db, command)
    except ActionDeferred as exc:
        result = {**exc.result, 'dispatch_state': 'not_started'}
        db.execute("UPDATE commands SET state='done',result=? WHERE id=?", (encoded(result), command['id']))
        db.execute("UPDATE actions SET state='blocked',result=? WHERE id=?", (encoded(result), command['action_id']))
        from .workspace_execution import sync_actions
        sync_actions(store, db)
        return False
    return True
