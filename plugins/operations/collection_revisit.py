"""Per-topic URL history and fair scheduling of first reads and due revisits."""
from collections import deque
from datetime import date, timedelta
from urllib.parse import urlsplit
import json

from .collection_validation import canonical_url, fingerprint
from .store import encoded

INTERVALS = (1, 3, 7, 14)


def _bootstrap(db, topic):
    from hashlib import sha256
    from .policy import now_iso
    key = 'collection-index-v1:' + sha256(topic.encode()).hexdigest()
    if db.execute("SELECT 1 FROM objects WHERE id=?", (key,)).fetchone():
        return
    db.execute('BEGIN IMMEDIATE')
    if not db.execute("INSERT OR IGNORE INTO objects VALUES (?,'collection_index','{}',?)", (key, now_iso())).rowcount:
        return
    # Stream legacy snapshots only once, newest first. Earlier reads establish fingerprint history,
    # but cannot prove a streak of unchanged observations.
    for row in db.execute("SELECT id,data FROM objects WHERE kind='source' "
                          "AND coalesce(json_extract(data,'$.scope_topic'),?)=? ORDER BY created DESC,rowid DESC", (topic, topic)):
        r = json.loads(row['data'])
        if not r.get('text') or not r.get('day') or not r.get('url'):
            continue
        url = canonical_url(r['url'])
        digest = r.get('fingerprint') or fingerprint(r['text'])
        next_day = (date.fromisoformat(r['day']) + timedelta(days=1)).isoformat()
        db.execute('INSERT OR IGNORE INTO collection_fingerprints VALUES (?,?,?)', (topic, digest, row['id']))
        db.execute('INSERT OR IGNORE INTO collection_urls VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                   (topic, url, r['day'], next_day, digest, 0, row['id'], r.get('feed_updated'), encoded(r.get('origins', [])),
                    r.get('title'), r.get('author'), r.get('published_at')))


def snapshot(store, topic, day):
    with store.connection() as db:
        _bootstrap(db, topic)
        history = {r['url']: {**dict(r), 'origins': json.loads(r['origins'])} for r in db.execute(
            'SELECT * FROM collection_urls WHERE topic=?', (topic,))}
        fingerprints = dict(db.execute('SELECT digest,source_id FROM collection_fingerprints WHERE topic=?', (topic,)))
        previous = {}
        for r in db.execute("SELECT id,json_extract(data,'$.url') AS url,length(json_extract(data,'$.text')) AS text,"
                            "coalesce(json_extract(data,'$.attempts'),0) AS attempts FROM objects WHERE kind='source' "
                            "AND json_extract(data,'$.day')=? AND coalesce(json_extract(data,'$.scope_topic'),?)=? "
                            "ORDER BY created,rowid", (day, topic, topic)):
            previous[canonical_url(r['url'])] = dict(r)
    return history, previous, fingerprints


def observation(prior, current):
    if not prior:
        return 'new_read', 0
    if prior['digest'] != current:
        return 'changed', 0
    return 'unchanged', min(prior['unchanged'] + 1, len(INTERVALS) - 1)


def save_observation(db, record, identity, unchanged):
    day = date.fromisoformat(record['day'])
    next_day = (day + timedelta(days=INTERVALS[unchanged])).isoformat()
    db.execute('INSERT OR IGNORE INTO collection_fingerprints VALUES (?,?,?)',
               (record['scope_topic'], record['fingerprint'], identity))
    db.execute('INSERT OR REPLACE INTO collection_urls VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
               (record['scope_topic'], record['url'], record['day'], next_day, record['fingerprint'], unchanged,
                identity, record.get('feed_updated'), encoded(record['origins']),
                record['title'], record.get('author'), record.get('published_at')))


def priority(row):
    types = {o['type'] for o in row['origins']}
    if 'configured' in types:
        return 0
    return 1 if 'rss' in types else 2


def primary_candidate(item):
    url, row = item
    if not any(o.get('language') == 'en' for o in row['origins']):
        return False
    parts = urlsplit(url)
    host = parts.hostname or ''
    return (host in {'arxiv.org', 'doi.org', 'openreview.net'} or host.startswith('docs.')
            or (host == 'github.com' and '/releases' in parts.path)
            or any(segment in {'docs', 'papers', 'release-notes'} for segment in parts.path.split('/')))


def new_order(items, offset):
    groups = {}
    for item in sorted(items, key=lambda it: not primary_candidate(it)):
        bucket = next((o['query'] for o in item[1]['origins'] if o['type'] == 'search'), '')
        groups.setdefault(bucket, deque()).append(item)
    keys = list(groups)
    start = offset % len(keys)
    keys = keys[start:] + keys[:start]
    while keys:
        for key in keys:
            group = groups[key]
            yield group.popleft()
        keys = [key for key in keys if groups[key]]


def ordered(urls, history, previous, day, stats, used, prior_rechecks):
    fresh, revisits = [], []
    for url, row in sorted(urls.items(), key=lambda it: previous.get(it[0], {}).get('attempts', 0)):
        prior = history.get(url)
        updated = row.get('feed_updated')
        signalled = bool(prior and updated and updated != prior['feed_updated'])
        if previous.get(url, {}).get('text') and not signalled:
            stats['already_read'] += 1
        elif not prior:
            fresh.append((url, row))
        elif signalled or prior['next_day'] <= day or (priority(row) == 0 and prior['last_day'] < day):
            revisits.append((url, row))
        else:
            stats['deferred_rechecks'] += 1
    # A failed previously unseen URL yields to fresh work, even if it was manually configured.
    fresh.sort(key=lambda it: (previous.get(it[0], {}).get('attempts', 0), priority(it[1])))
    from itertools import groupby
    fresh = deque(item for _, group in groupby(fresh, key=lambda it: (previous.get(it[0], {}).get('attempts', 0), priority(it[1])))
                  for item in new_order(group, used - prior_rechecks))
    revisits.sort(key=lambda it: (not bool(it[1].get('feed_updated') and it[1]['feed_updated'] != history[it[0]]['feed_updated']),
                                  priority(it[1]), history[it[0]]['last_day']))
    revisits = deque(revisits)
    while fresh or revisits:
        due = bool(revisits and (not fresh or prior_rechecks + stats['rechecks'] < 1 + (used + stats['attempted']) // 5))
        yield (revisits if due else fresh).popleft()
