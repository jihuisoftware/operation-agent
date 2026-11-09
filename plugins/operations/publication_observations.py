"""Latest check and previously observed publication facts have separate provenance."""
import json

from .publication_status import normalize


def merge(previous, result, checked_at):
    value = {**previous, **result}
    before = previous.get('publication', {})
    current = result.get('publication', {})
    if not before and not current:
        return value
    status, inherited = {}, []
    times = dict(previous.get('publication_observed_at', {}))
    for field in ('execution', 'platform', 'content'):
        old, new = before.get(field, 'unknown'), current.get(field, 'unknown')
        unavailable = new == 'unknown' or (field == 'execution' and old == 'verified' and new == 'submitted')
        if unavailable and old != 'unknown':
            status[field] = old
            inherited.append(field)
            times.setdefault(field, previous.get('verified_at'))
        else:
            status[field] = new
            if new != 'unknown':
                times[field] = checked_at
    value.update(publication=status, publication_observed_at=times, publication_inherited=inherited,
                 verification_stale=bool(inherited), last_check={
                     'at': checked_at, **{key: result[key] for key in ('state', 'publication', 'evidence', 'error', 'error_code') if key in result}})
    return normalize(value)


def previous_facts(db, action):
    previous = json.loads(action['result'])
    if previous.get('last_check') or not previous.get('publication'):
        return previous
    # Upgrade old merged receipts lazily from immutable command evidence; do not
    # rewrite historical runs, commands, reports or manual conclusions.
    facts = dict(previous['publication'])
    for field in ('execution', 'platform', 'content'):
        if facts.get(field) not in (None, 'unknown') and not (field == 'execution' and facts[field] == 'submitted'):
            continue
        path = '$.publication.' + field
        row = db.execute("SELECT json_extract(result,?) AS fact FROM commands WHERE state='done' "
                         "AND (action_id=? OR json_extract(payload,'$.verification_action_id')=?) "
                         "AND json_extract(result,?) IS NOT NULL AND json_extract(result,?)!='unknown' "
                         "AND (?!='execution' OR json_extract(result,?)='verified') ORDER BY rowid DESC LIMIT 1",
                         (path, action['id'], action['id'], path, path, field, path)).fetchone()
        if row:
            facts[field] = row['fact']
    restored = merge({**previous, 'publication': facts}, previous, previous.get('verified_at'))
    return {**previous, **{key: restored[key] for key in ('publication', 'publication_observed_at', 'publication_inherited', 'verification_stale')}}
