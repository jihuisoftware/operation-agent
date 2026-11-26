"""Source discovery, bounded retries, validated snapshots and per-batch accounting."""
import asyncio
import hashlib
import json
import uuid

import httpx

from .collection_ledger import budget, check, check_persisted, load, release_read, reserve, save, write
from .collection_candidates import candidates
from .collection_language import language
from .collection_revisit import snapshot, observation, ordered, save_observation
from .collection_validation import document, failure_hint
from .policy import now_iso
from .store import encoded


def read(store, policy, day, url, candidate, attempt, previous, fingerprints, last=None, claim=None):
    from tools.web_result_cache import extract_cache_invalidate
    from tools.web_tools import web_extract_tool
    from .source_documents import EXTRACT_LIMIT, prepared
    from .source_media import capture, image_urls
    store.progress('正在读取来源正文', {'url': url, 'attempt': attempt})
    if last:
        extract_cache_invalidate(url)
    try:
        extracted = json.loads(asyncio.run(web_extract_tool([url], char_limit=EXTRACT_LIMIT, include_metadata=True)))
        pages = extracted.get('results', [])
        page = pages[0] if pages else {}
        text, error = document(page, extracted.get('error'))
    except (OSError, ValueError, httpx.HTTPError) as exc:
        page, text, error = {}, '', str(exc)
    check(store, policy)
    if error:
        extract_cache_invalidate(url)
    projection = prepared(text, truncated=page.get('truncated', False), original_chars=page.get('original_chars'))
    text, digest = projection['text'], projection['fingerprint']
    if not text and not error:
        error = '页面仅有登录或导航内容，未取得正文'
    prior_id = fingerprints.get(digest) if digest else None
    record = {'day': day, 'url': url, 'original_url': candidate.get('url'),
              'title': page.get('title') or candidate.get('title') or url,
              'author': page.get('author') or candidate.get('author'),
              'published_at': page.get('published_at') or candidate.get('published_at'),
              'collected_at': now_iso(), 'text': text, 'state': 'read' if text else 'unavailable',
              'error': error, 'error_hint': failure_hint(error) if error else None, 'summary': '', 'fingerprint': digest, 'attempts': attempt,
              'truncated': page.get('truncated', False), 'original_chars': page.get('original_chars', len(text)),
              'is_new': bool(text and not prior_id), 'previous_source_id': prior_id, 'scope_topic': policy['topic'],
              'images': capture(store, image_urls(page, candidate, url, text), url) if text else [], **projection}
    outcome, unchanged = observation(last, digest)
    from .organization_reuse import RULE
    record.update(organization_protocol=RULE, origins=candidate.get('origins', []), document_language=language(text),
                  feed_updated=candidate.get('feed_updated'), read_outcome=outcome if text else 'failed',
                  previous_url_source_id=last['source_id'] if last else None)
    if getattr(store, 'debug_id', None):
        record['debug_id'] = store.debug_id
    identity = previous['id'] if previous else hashlib.sha256(f'{day}:{url}'.encode()).hexdigest()
    if previous and previous.get('text'):
        identity = hashlib.sha256(encoded([day, url, attempt, record['feed_updated']]).encode()).hexdigest()
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        check_persisted(db, policy)
        if claim and not release_read(db, policy['topic'], url, claim):
            raise ValueError('采集读取租约已变化，未覆盖更新的正文')
        write(store, db, 'source', identity, record)
        if text:
            save_observation(db, record, identity, unchanged)
    if store.current_run_id:
        from .progress import saved
        saved(store, 'source', identity, record)
    store.event('source_attempt', {'day': day, 'source_id': identity, 'url': url, 'attempt': attempt,
                                   'state': record['state'], 'error': error, 'duplicate_of': prior_id})
    if digest:
        fingerprints.setdefault(digest, identity)
    return record


def collect(store, policy, day):
    identity = 'collection:' + uuid.uuid4().hex
    stats = {key: 0 for key in ('candidates', 'attempted', 'succeeded', 'new', 'duplicate_content', 'already_read',
                                'failed', 'not_attempted', 'new_reads', 'rechecks', 'changed', 'unchanged', 'deferred_rechecks', 'retried', 'duplicate_links', 'invalid_urls', 'searches', 'search_errors')}
    stats.update(queries=[], english_reason='本批未执行检索', day=day, scope_topic=policy['topic'], started=now_iso(), state='running', limit=policy['limits']['source'], failure_reasons=[])
    if getattr(store, 'debug_id', None):
        stats['debug_id'] = store.debug_id
    options = store.run_options or {}
    stats['read_limit'] = options.get('read_limit', stats['limit'])
    stats['query_limit'] = options.get('query_limit', 12)
    save(store, 'collection_run', identity, stats)
    try:
        check(store, policy)
        history, previous, fingerprints = snapshot(store, policy['topic'], day)
        used = budget(store, day)
        if used >= stats['limit']:
            stats['reason'] = '当日读取额度已用完，未发起检索或读取'
        urls = candidates(store, policy, day, stats, history, discover=used < stats['limit'])
        stats['candidates'] = len(urls)
        day_budget = load(store, 'collection-budget:' + day) or {}
        order = ordered(urls, history, previous, day, stats, used, day_budget.get('rechecks', 0))
        for url, candidate in order:
            prior = previous.get(url)
            attempt = None
            if used < stats['limit'] and stats['attempted'] < stats['read_limit']:
                attempt = reserve(store, policy, day, url, recheck=url in history, claim=identity,
                                  expected_source=(history.get(url) or {}).get('source_id'))
            if attempt is None:
                stats['not_attempted'] += 1
                continue
            used += 1
            stats['used'] = used
            stats['attempted'] += 1
            stats['retried'] += int(attempt > 1)
            stats['rechecks' if url in history else 'new_reads'] += 1
            record = read(store, policy, day, url, candidate, attempt, prior, fingerprints, history.get(url), identity)
            if record['read_outcome'] in ('changed', 'unchanged'):
                stats[record['read_outcome']] += 1
            success = bool(record['text'])
            stats['succeeded'] += int(success)
            stats['failed'] += int(not success)
            stats['new'] += int(record['is_new'])
            stats['duplicate_content'] += int(success and not record['is_new'])
            if record['error_hint'] and record['error_hint'] not in stats['failure_reasons']:
                stats['failure_reasons'].append(record['error_hint'])
            save(store, 'collection_run', identity, stats)
        stats['state'] = 'completed'
    finally:
        stats.update(used=budget(store, day), ended=now_iso())
        if stats['state'] == 'running':
            stats['state'] = 'interrupted'
        save(store, 'collection_run', identity, stats)
        store.event('collection_result', stats)
    return stats
