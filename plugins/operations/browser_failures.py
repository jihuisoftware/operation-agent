"""Recover only readiness failures proved to precede submission; preserve uncertain action guards."""
import json

from .policy import now_iso
from .run_scope import annotate

CODES = {'PAGE_NOT_READY', 'PAGE_UNAVAILABLE', 'CAPABILITY_UNAVAILABLE', 'CONTROL_PAUSED'}
LEGACY_TIMEOUT = '等待网页就绪超时，未执行后续提交'


def retryable(db, command, result):
    if result.get('state') != 'blocked':
        return False
    structured = result.get('submitted') is False and result.get('error_code') in CODES
    legacy = LEGACY_TIMEOUT in str(result.get('error', ''))
    if not structured and not legacy:
        return False
    if command['kind'] in {'inbox', 'account'}:
        return True
    if command['kind'] not in {'interact', 'publish'}:
        return False
    steps = [json.loads(row[0]) for row in db.execute(
        "SELECT data FROM objects WHERE kind='browser_step' AND json_extract(data,'$.command_id')=?", (command['id'],))]
    if any(row['name'] in {'submit', 'submit_interaction'} and row['phase'] == 'started' for row in steps):
        return False
    return structured or any(row['name'] in {'prepare_interaction', 'open_editor', 'upload', 'fill'} and row['phase'] == 'failed' for row in steps)


def should_pause(db, command, result):
    return result.get('state') == 'blocked' and command['kind'] not in {'account', 'verify'} and not retryable(db, command, result)


def active_block(store, db, kind, version):
    if not db.in_transaction:
        db.execute('BEGIN IMMEDIATE')
    rows = db.execute("SELECT id,data FROM objects WHERE kind='block' AND json_extract(data,'$.kind')=? AND json_extract(data,'$.version')=?", (kind, version)).fetchall()
    blocked = False
    for row in rows:
        block = json.loads(row['data'])
        commands = db.execute("SELECT * FROM commands WHERE state='done' AND json_extract(payload,'$.kind')=? "
                              "AND json_extract(payload,'$.policy_version')=? AND json_extract(result,'$.error')=?", (kind, version, block.get('error'))).fetchall()
        if not commands or not all(retryable(db, command, json.loads(command['result'])) for command in commands):
            blocked = True
            continue
        block.update(recovered_at=now_iso(), recovery_reason='就绪失败发生于提交前，允许新的显式尝试')
        db.execute("UPDATE objects SET kind='block_recovered',data=? WHERE id=?", (json.dumps(block, ensure_ascii=False), row['id']))
        data = annotate(store, {'kind': kind, 'version': version, 'block_id': row['id'], 'reason': block['recovery_reason']})
        db.execute("INSERT INTO events(at,kind,data) VALUES (?,'capability_recovered',?)", (now_iso(), json.dumps(data, ensure_ascii=False)))
    return blocked
