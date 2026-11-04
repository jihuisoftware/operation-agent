"""Deterministic statistics over complete selected windows, never LLM arithmetic."""
from collections import Counter
from decimal import Decimal
import json
from urllib.parse import urlsplit

from .business_store import datasets, model_sample
from .business_validation import TEMPLATES, MONEY, fingerprint
from .organization import material_id


def source_rows(store, policy, window):
    from .analysis_runs import guard
    cursor = 0
    while True:
        guard(store, policy)
        with store.connection() as db:
            rows = db.execute("SELECT rowid,id,data FROM objects WHERE rowid>? AND kind='source' AND json_extract(data,'$.scope_topic')=? "
                              "AND json_extract(data,'$.day') BETWEEN ? AND ? ORDER BY rowid LIMIT 250",
                              (cursor, policy['topic'], window['previous_start'], window['end'])).fetchall()
            pairs = []
            for row in rows:
                source = {**json.loads(row['data']), 'id': row['id']}
                organized = db.execute("SELECT id,data FROM objects WHERE kind='organized_source' AND id=?", (material_id(policy, source),)).fetchone() if source.get('text') else None
                pairs.append((source, {**json.loads(organized['data']), 'id': organized['id']} if organized else None))
        if not rows:
            return
        cursor = rows[-1]['rowid']
        yield from pairs


def sources_summary(store, policy, window):
    counts, previous, categories, keywords, platforms, trend = Counter(), Counter(), Counter(), Counter(), Counter(), Counter()
    evidence = []
    seen = set()
    for source, organized in source_rows(store, policy, window):
        period = counts if source['day'] >= window['start'] else previous
        period['collected'] += 1
        if not source.get('text'):
            period['failed'] += 1
            continue
        signature = (source['day'] >= window['start'], fingerprint(source['text']))
        if signature in seen:
            continue
        seen.add(signature)
        period['read'] += 1
        if organized:
            period['organized'] += 1
        if source['day'] < window['start']:
            continue
        trend[source['day']] += 1
        platforms[urlsplit(source.get('url', '')).hostname or '未知'] += 1
        if not organized or not organized['relevant']:
            continue
        categories[organized['category']] += 1
        keywords.update(set(organized['keywords']))
        evidence.append({'id': source['id'], 'organization_id': organized['id'], 'title': source.get('title', ''),
                         'url': source.get('url', ''), 'day': source['day'], 'published_at': source.get('published_at'),
                         'content_fingerprint': fingerprint(source['text']), 'source_complete': not source.get('truncated', False),
                         'category': organized['category'],
                         'summary': organized['summary'], 'facts': organized['facts'], 'opinions': organized['opinions'],
                         'uncertainties': organized['uncertainties'], 'text_truncated': organized['text_truncated']})
    return {'counts': dict(counts), 'previous': dict(previous), 'categories': dict(categories), 'keywords': dict(keywords.most_common(30)),
            'platforms': dict(platforms), 'trend': dict(sorted(trend.items())), 'source_ids': [e['id'] for e in evidence]}, evidence


def _value(rows, key, semantics):
    valid = [r for r in rows if r.get(key) is not None]
    if not valid:
        return None
    if semantics == 'snapshot':
        latest = {}
        for row in sorted(valid, key=lambda r: r['day']):
            group = tuple(row.get(k, '') for k in ('product', 'channel', 'platform'))
            latest[group] = Decimal(row[key])
        return str(sum(latest.values(), Decimal(0)))
    return str(sum((Decimal(r[key]) for r in valid), Decimal(0)))


def _metric(item, rows, key, label, window):
    config = item['config']
    current = [r for r in rows if r['day'] >= window['start']]
    previous = [r for r in rows if r['day'] < window['start']]
    value, base = (_value(group, key, config['semantics']) for group in (current, previous))
    growth = str((Decimal(value) - Decimal(base)) / abs(Decimal(base)) * 100) if value is not None and base is not None and Decimal(base) != 0 else None
    return {'id': item['id'] + ':' + key, 'dataset_id': item['id'], 'key': key, 'name': label, 'value': value,
            'previous': base, 'growth_percent': growth, 'samples': len(current), 'missing': sum(r.get(key) is None for r in current),
            'unit': config['currency'] if key in MONEY else '次' if key != 'quantity' else '件',
            'definition': config['definition'], 'semantics': config['semantics'], 'visibility': 'public' if key in item['sharing']['public_metrics'] else 'internal',
            'model_allowed': item['sharing']['model_mode'] != 'local',
            'trend': {day: _value([r for r in current if r['day'] == day], key, config['semantics']) for day in sorted({r['day'] for r in current})}}


def business_summary(store, policy, window):
    metrics, versions, details = [], [], []
    for item in datasets(store):
        if not item['active'] or item['scope_topic'] != policy['topic']:
            continue
        with store.connection() as db:
            rows = [json.loads(row['data']) for row in db.execute(
                'SELECT data,batch_id FROM business_rows WHERE dataset_id=? AND day BETWEEN ? AND ?',
                (item['id'], window['previous_start'], window['end'])) if row['batch_id'] in item['batches']]
        versions.append({'id': item['id'], 'version': item['version'], 'batches': item['batches']})
        for key, label in TEMPLATES[item['config']['template']]['metrics'].items():
            if key in item['config']['mapping']:
                metrics.append(_metric(item, rows, key, label, window))
        eligible = [r for r in rows if r['day'] >= window['start']]
        details.append({'dataset_id': item['id'], 'rows': model_sample(eligible[:100], item['sharing']),
                        'total': len(eligible), 'omitted': max(0, len(eligible) - 100) if item['sharing']['model_mode'] == 'details' else len(eligible)})
    return metrics, versions, details


def operational_metrics(store, window):
    result = []
    for row in store.objects('metric'):
        if not window['start'] <= row.get('day', '') <= window['end']:
            continue
        result.append({'id': row['id'], 'name': row.get('name'), 'value': row.get('value'), 'unit': row.get('unit', '未提供'),
                       'definition': row.get('definition'), 'source': row.get('source'), 'day': row['day'],
                       'observed_at': row.get('observed_at'), 'visibility': 'internal', 'model_allowed': False})
    return result
