"""On-demand seven-day observation, evaluated in the topic's own operations calendar."""
from datetime import date, timedelta
import json

from .collection_validation import canonical_url
from .policy import local_day


def report(store):
    _, policy = store.policy()
    topic, end = policy['topic'], local_day(policy)
    start = (date.fromisoformat(end) - timedelta(days=6)).isoformat()
    fixed = {canonical_url(url) for url in policy['sources']}
    with store.connection() as db:
        def records(kind):
            return [json.loads(r[0]) for r in db.execute(
                "SELECT data FROM objects WHERE kind=? AND json_extract(data,'$.day') BETWEEN ? AND ? "
                "AND json_extract(data,'$.scope_topic')=?", (kind, start, end, topic))]
        batches = [b for b in records('collection_run') if not b.get('debug_id')]
        attempts = sum(b.get('attempted', 0) for b in batches)
        added = sum(b.get('new', 0) for b in batches)
        rows = records('organized_source')
        relevant = {r['source_id'] for r in rows if r.get('relevant') and not r.get('debug_id')}
        documents = db.execute("SELECT id,json_extract(data,'$.fingerprint') FROM objects WHERE kind='source' "
                               "AND json_extract(data,'$.day') BETWEEN ? AND ? AND json_extract(data,'$.scope_topic')=? "
                               "AND json_extract(data,'$.debug_id') IS NULL", (start, end, topic))
        relevant_documents = {digest or identity for identity, digest in documents if identity in relevant}
        known = {term for b in batches for q in b.get('queries', []) for term in q.get('keywords', [q['keyword']])}
        cited = {identity for b in records('brief') if not b.get('debug_id') for entry in b.get('result', {}).get('topics', [])
                 if isinstance(entry, dict) for identity in (entry.get('source_ids') or [])}
        en, unknown = 0, 0
        for identity in cited:
            row = db.execute("SELECT json_extract(data,'$.document_language') FROM objects WHERE kind='source' AND id=?", (identity,)).fetchone()
            lang = row[0] if row else None
            en += int(lang == 'en')
            unknown += int(lang in (None, 'unknown'))
        calls = db.execute("SELECT count(*) FROM events e JOIN runs r ON r.id=json_extract(e.data,'$.run_id') "
                           "WHERE e.kind='model_call' AND r.stage='organize' AND r.day BETWEEN ? AND ? "
                           "AND json_extract(e.data,'$.debug_id') IS NULL AND r.slot NOT LIKE 'debug:%'", (start, end)).fetchone()[0]
        overdue = sum(not db.execute('SELECT 1 FROM collection_urls WHERE topic=? AND url=? AND last_day>=?',
                                     (topic, url, end)).fetchone() for url in fixed)
    return {'start': start, 'end': end, 'attempted': attempts, 'new': added,
            'new_per_100': round(100 * added / attempts, 1) if attempts else None,
            'relevant': len(relevant_documents),
            'relevant_per_100': round(100 * len(relevant_documents) / attempts, 1) if attempts else None, 'organization_calls': calls, 'fixed_not_read_today': overdue,
            'keywords': sorted(known), 'legacy_batches': sum('queries' not in b for b in batches),
            'cited_english': en, 'cited_unknown_language': unknown}
