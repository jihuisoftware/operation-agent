"""Source discovery, bounded retries, validated snapshots and per-batch accounting."""
import asyncio
import hashlib
import json
import uuid
from xml.etree.ElementTree import ParseError

import httpx

from .collection_ledger import budget, check, load, reserve, save
from .collection_search import search
from .collection_validation import canonical_url, document, fingerprint
from .policy import now_iso


def candidates(store, policy, day, stats, previous, *, discover=True):
    from .feeds import feed_entries
    rows = [{'url': url, 'title': url} for url in policy['sources']]
    key = 'collection-queue:' + hashlib.sha256(f"{day}:{policy['topic']}".encode()).hexdigest()
    rows.extend((load(store, key) or {}).get('items', []))
    rows.extend(row for row in previous.values() if not row.get('text'))
    for feed in policy.get('rss_sources', []) if discover else []:
        check(store, policy)
        try:
            rows.extend(feed_entries(feed))
        except (OSError, ValueError, httpx.HTTPError, ParseError) as exc:
            stats['search_errors'] += 1
            store.event('source_error', {'day': day, 'url': feed, 'error': str(exc)})
    if discover:
        rows.extend(search(store, policy, day, stats))
    urls = {}
    for row in rows:
        try:
            url = canonical_url(row.get('url', ''))
        except ValueError:
            stats['invalid_urls'] += 1
            continue
        if url in urls:
            stats['duplicate_links'] += 1
        else:
            urls[url] = row
    save(store, 'collection_queue', key, {'day': day, 'items': list(urls.values())})
    return urls


def read(store, policy, day, url, candidate, attempt, previous, fingerprints):
    from tools.web_tools import web_extract_tool
    from .source_media import capture, image_urls
    store.progress('正在读取来源正文', {'url': url, 'attempt': attempt})
    try:
        extracted = json.loads(asyncio.run(web_extract_tool([url], char_limit=10000, include_metadata=True)))
        pages = extracted.get('results', [])
        page = pages[0] if pages else {}
        text, error = document(page, extracted.get('error'))
    except (OSError, ValueError, httpx.HTTPError) as exc:
        page, text, error = {}, '', str(exc)
    check(store, policy)
    if error:
        from tools.web_result_cache import extract_cache_invalidate
        extract_cache_invalidate(url)
    digest = fingerprint(text)
    prior_id = fingerprints.get(digest) if digest else None
    record = {'day': day, 'url': url, 'original_url': candidate.get('url'),
              'title': page.get('title') or candidate.get('title') or url,
              'author': page.get('author') or candidate.get('author'),
              'published_at': page.get('published_at') or candidate.get('published_at'),
              'collected_at': now_iso(), 'text': text, 'state': 'read' if text else 'unavailable',
              'error': error, 'summary': '', 'fingerprint': digest, 'attempts': attempt,
              'truncated': page.get('truncated', False), 'original_chars': page.get('original_chars', len(text)),
              'is_new': bool(text and not prior_id), 'previous_source_id': prior_id, 'scope_topic': policy['topic'],
              'images': capture(store, image_urls(page, candidate, url, text), url) if text else []}
    identity = previous['id'] if previous else hashlib.sha256(f'{day}:{url}'.encode()).hexdigest()
    save(store, 'source', identity, record)
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
                                'failed', 'not_attempted', 'retried', 'duplicate_links', 'invalid_urls', 'searches', 'search_errors')}
    stats.update(day=day, scope_topic=policy['topic'], started=now_iso(), state='running', limit=policy['limits']['source'])
    save(store, 'collection_run', identity, stats)
    try:
        check(store, policy)
        rows = store.objects('source')
        previous = {canonical_url(row['url']): row for row in rows if row.get('day') == day}
        fingerprints = {fingerprint(row['text']): row['id'] for row in rows if row.get('text')}
        used = budget(store, day)
        if used >= stats['limit']:
            stats['reason'] = '当日读取额度已用完，未发起检索或读取'
        urls = candidates(store, policy, day, stats, previous, discover=used < stats['limit'])
        stats['candidates'] = len(urls)
        for url, candidate in urls.items():
            prior = previous.get(url)
            if prior and prior.get('text'):
                stats['already_read'] += 1
                continue
            attempt = reserve(store, policy, day, url, prior) if used < stats['limit'] else None
            if attempt is None:
                stats['not_attempted'] += 1
                continue
            used += 1
            stats['used'] = used
            stats['attempted'] += 1
            stats['retried'] += int(attempt > 1)
            record = read(store, policy, day, url, candidate, attempt, prior, fingerprints)
            success = bool(record['text'])
            stats['succeeded'] += int(success)
            stats['failed'] += int(not success)
            stats['new'] += int(record['is_new'])
            stats['duplicate_content'] += int(success and not record['is_new'])
            save(store, 'collection_run', identity, stats)
        stats['state'] = 'completed'
    finally:
        stats.update(used=budget(store, day), ended=now_iso())
        if stats['state'] == 'running':
            stats['state'] = 'interrupted'
        save(store, 'collection_run', identity, stats)
        store.event('collection_result', stats)
    return stats
