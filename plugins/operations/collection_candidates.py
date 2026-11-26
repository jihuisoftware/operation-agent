"""Discovery provenance and bounded carry-over within the current topic."""
import hashlib
from datetime import date, timedelta
from xml.etree.ElementTree import ParseError

import httpx

from .collection_ledger import check, load, save
from .collection_validation import canonical_url
from .collection_search import search


def origin_key(origin):
    return tuple(origin.get(k, '') for k in ('type', 'feed', 'query', 'language', 'keyword'))


def merge_origins(origins):
    by_key = {}
    for item in origins:
        key = origin_key(item)
        if key not in by_key or item['seen'] >= by_key[key]['seen']:
            by_key[key] = item
    return list(by_key.values())


def queue_key(policy, day):
    return 'collection-queue:' + hashlib.sha256(f"{day}:{policy['topic']}".encode()).hexdigest()


def discovered(store, policy, day, stats, discover):
    from .feeds import feed_entries
    rows = [{'url': url, 'title': url, 'origins': [{'type': 'configured'}]} for url in policy['sources']]
    options = None
    if discover:
        for feed in policy.get('rss_sources', []):
            check(store, policy)
            try:
                rows.extend({**r, 'origins': [{'type': 'rss', 'feed': feed}]} for r in feed_entries(feed))
            except (OSError, ValueError, httpx.HTTPError, ParseError) as exc:
                stats['search_errors'] += 1
                store.event('source_error', {'day': day, 'url': feed, 'error': str(exc)})
        if stats['query_limit'] > 0:
            found, options = search(store, policy, day, stats)
            rows.extend(found)
    return [{**r, 'origins': [{**o, 'seen': day} for o in r['origins']]} for r in rows], options


def valid_origin(origin, policy, url, options, configured):
    kind = origin['type']
    if kind == 'configured':
        return url in configured
    if kind == 'rss':
        return origin.get('feed') in policy['rss_sources']
    if kind == 'search':
        if options is None:
            return origin.get('keyword') in (policy['topic'], *policy['keywords'])
        current = options.get(origin.get('query'))
        return current is not None and origin.get('keyword') in current.get('keywords', [current['keyword']])
    return False


def candidates(store, policy, day, stats, history, *, discover=True):
    fresh, options = discovered(store, policy, day, stats, discover)
    configured = {canonical_url(url) for url in policy['sources']}
    today = date.fromisoformat(day)
    rows = []
    for age in range(7):
        queue = load(store, queue_key(policy, (today - timedelta(days=age)).isoformat())) or {}
        rows.extend(queue.get('items', []))
    cutoff = (today - timedelta(days=6)).isoformat()
    urls = {}
    # Keep fresh metadata in preference to carried observations.
    for index, row in enumerate([*fresh, *rows, *history.values()]):
        try:
            url = canonical_url(row.get('url', ''))
        except ValueError:
            stats['invalid_urls'] += 1
            continue
        origins = [o for o in row.get('origins', []) if (o['seen'] >= cutoff or url in history)
                   and valid_origin(o, policy, url, options, configured)]
        if not origins:
            continue
        if url in urls:
            stats['duplicate_links'] += int(index < len(fresh))
            selected = urls[url]
            selected['origins'] = merge_origins([*selected['origins'], *origins])
            for field in ('feed_updated', 'author', 'published_at', 'title'):
                if row.get(field) and (not selected.get(field) or (field == 'title' and selected[field] == url)):
                    selected[field] = row[field]
        else:
            urls[url] = {k: row[k] for k in ('url', 'title', 'author', 'published_at', 'feed_updated', 'images') if k in row}
            urls[url]['origins'] = origins
    record_rediscoveries(store, policy['topic'], day, urls, history)
    save(store, 'collection_queue', queue_key(policy, day), {'day': day, 'scope_topic': policy['topic'], 'items': [
        r for r in urls.values() if any(o['seen'] == day for o in r['origins'])]})
    with store.connection() as db:
        db.execute("DELETE FROM objects WHERE kind='collection_queue' AND json_extract(data,'$.scope_topic')=? "
                   "AND json_extract(data,'$.day')<?", (policy['topic'], cutoff))
    return urls


def record_rediscoveries(store, topic, day, urls, history):
    from .store import encoded
    with store.connection() as db:
        for url, row in urls.items():
            prior = history.get(url)
            if not prior or prior['origins'] == row['origins']:
                continue
            origins = encoded(row['origins'])
            changed = db.execute('UPDATE collection_urls SET origins=? WHERE topic=? AND url=? AND source_id=?',
                                 (origins, topic, url, prior['source_id'])).rowcount
            if changed and prior['last_day'] == day:
                db.execute("UPDATE objects SET data=json_set(data,'$.origins',json(?)) WHERE id=? AND kind='source'",
                           (origins, prior['source_id']))
