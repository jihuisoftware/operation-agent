"""Reuse only complete, rule-matched evidence while preserving each source's identity."""
import hashlib

from .collection_validation import canonical_url
from .source_documents import requires_repair
from .store import encoded

RULE = 'zh-evidence-v1'
FIELDS = ('category', 'relevant', 'summary', 'facts', 'opinions', 'uncertainties', 'keywords', 'format_warnings')


def signature(policy, source):
    if not source.get('url') or not source.get('text') or requires_repair(source):
        return None
    try:
        url = canonical_url(source['url'])
    except ValueError:
        return None
    from .organization import INSTRUCTION, CATEGORIES
    from .organization_segments import PROTOCOL
    return hashlib.sha256(encoded([RULE, PROTOCOL, INSTRUCTION, CATEGORIES, policy['topic'], url, source['text'], source.get('text_revision'),
                                  source.get('title'), source.get('published_at'), source.get('author'),
                                  source.get('document_version')]).encode()).hexdigest()


def bind(store, policy, day, version, pending):
    from .organization import save_rows
    cache = {r['reuse_signature']: r for r in store.objects('organized_source')
             if r.get('reuse_signature') and r.get('scope_topic') == policy['topic'] and not r.get('format_incomplete')
             and r.get('coverage', {}).get('complete')
             and r['coverage'].get('segments_completed') == r['coverage'].get('segments_total')}
    remaining, reused = [], 0
    for source in pending:
        previous = cache.get(signature(policy, source))
        if not previous:
            remaining.append(source)
            continue
        row = {key: previous[key] for key in FIELDS if key in previous}
        row.update(source_id=source['id'], reused_from=previous.get('reused_from') or previous['id'])
        save_rows(store, policy, day, version, [source], [row], segments_total=previous['coverage']['segments_total'])
        reused += 1
    return remaining, reused
