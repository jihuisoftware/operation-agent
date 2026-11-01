"""Append human conclusions without discarding automatic evidence."""
import json
import uuid
from .policy import now_iso
from .store import encoded


def resolve(store, identity, state, evidence):
    if state not in {'published', 'confirmed', 'confirmed_not_published', 'failed'} or not isinstance(evidence, str) or not evidence.strip():
        raise ValueError('请选择核对结果并填写证据或说明')
    if len(evidence) > 8000:
        raise ValueError('核对说明过长')
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM actions WHERE id=?', (identity,)).fetchone()
        if not row or row['state'] not in {'unknown', 'blocked', 'submitted', 'failed'}:
            raise ValueError('该动作当前不能人工核对')
        if (row['kind'] == 'publish' and state == 'confirmed') or (row['kind'] != 'publish' and state == 'published'):
            raise ValueError('核对结果与动作类型不匹配')
        previous = json.loads(row['result'])
        conclusion = {'id': uuid.uuid4().hex, 'action_id': identity, 'state': state,
                      'evidence': evidence.strip(), 'actor': '本机操作员', 'at': now_iso(), 'previous_state': row['state']}
        history = {**conclusion, 'previous_result': previous}
        db.execute("INSERT INTO objects VALUES (?, 'manual_conclusion', ?, ?)",
                   (conclusion['id'], encoded(history), conclusion['at']))
        result = {**previous, 'manual_verification': conclusion, 'verified_by': 'user'}
        db.execute('UPDATE actions SET state=?,result=? WHERE id=?', (state, encoded(result), identity))
        db.execute("UPDATE commands SET state='cancelled' WHERE kind='verify' AND state='queued' AND json_extract(payload,'$.verification_action_id')=?", (identity,))
        from .review_queue import load, save
        save(db, identity, {**load(db, identity), 'action_id': identity, 'state': 'manual', 'next_check_at': None})
        db.execute("INSERT INTO events(at,kind,data) VALUES (?, 'manual_resolution', ?)", (conclusion['at'], encoded(conclusion)))
    return conclusion
