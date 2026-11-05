"""Only confirmed publications are previous public articles; drafts are revision work."""
import json


def published(store, policy, day):
    from .analytics import valid
    enabled = any(policy['modules'].get(key) for key in ('analytics', 'industry'))
    with store.connection() as db:
        rows = db.execute("SELECT id,state,created,data FROM actions WHERE kind='publish' AND state IN ('published','confirmed') ORDER BY created DESC LIMIT 100").fetchall()
    result, seen = [], set()
    for row in rows:
        data = json.loads(row['data']).get('content', {})
        context = data.get('analysis_context')
        if context and (not enabled or not valid(store, context, policy, day)):
            continue
        identity = data.get('id', row['id'])
        if identity in seen:
            continue
        seen.add(identity)
        result.append({**data, 'id': identity, 'publication_state': row['state'], 'publication_recorded_at': row['created']})
        if len(result) == 15:
            break
    return result
