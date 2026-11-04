"""Stable evidence cohorts, with verified upgrades of immutable legacy checkpoints."""
from copy import deepcopy
import hashlib
import json

from .policy import now_iso
from .store import encoded

SCHEMA = 2
SOURCE_SCOPE = ('本轮仅解释所列固定文档，不把采集日期当作发布时间，不宣称覆盖今日或整个统计窗口的趋势。'
                '结论的适用范围只能是明确引用的文档；保留原始发布时期和证据局限。')
LEGACY_EXTRA_FIELDS = {'published_at', 'content_fingerprint', 'source_complete'}


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def signature(row):
    if 'organization_id' not in row:
        return digest(row)
    value = {key: item for key, item in row.items() if key not in {'id', 'day', 'organization_id'}}
    if not row.get('source_complete') or not row.get('content_fingerprint'):
        value.update(id=row['id'], organization_id=row['organization_id'])
    return digest(value)


def context(policy, config, visibility, kind, analytics):
    from .industry import INSTRUCTION
    value = {'schema': SCHEMA, 'topic': policy['topic'], 'visibility': visibility, 'kind': kind,
             'instruction': INSTRUCTION + (SOURCE_SCOPE if kind == 'source' else ''),
             **{key: config['config'][key] for key in ('industry', 'region', 'focus')}}
    if kind != 'source':
        value.update(window=analytics['window'], config_version=analytics['config_version'], datasets=analytics['datasets'])
    return digest(value)


def save(store, key, rows, findings, analytics, *, legacy=None, analyzed_at=None):
    members = {row['id']: signature(row) for row in rows}
    identity = 'industry-cache:' + digest({'context': key, 'members': sorted(members.values()), 'legacy': legacy})
    value = {'schema': SCHEMA, 'context': key, 'members': members, 'findings': findings,
             'origin_window': analytics['window'], 'created': now_iso(), 'analyzed_at': analyzed_at or now_iso(), 'legacy_id': legacy}
    store.put('industry_cache', value, identity)
    return {**value, 'id': identity}


def projection(cached, by_signature, current_window):
    aliases = {identity: by_signature[value]['id'] for identity, value in cached['members'].items()}
    historical = bool(cached.get('legacy_id') and cached['origin_window'] != current_window)
    result = []
    for finding in cached['findings']:
        result.append({**deepcopy(finding), 'evidence_ids': [aliases[identity] for identity in finding['evidence_ids']],
                       'origin_evidence_ids': finding['evidence_ids'], 'origin_window': cached['origin_window'],
                       'analyzed_at': cached.get('analyzed_at', cached['created']), 'analysis_origin': 'historical' if historical else 'evidence'})
    return result, list(aliases.values())


def reusable(store, key, rows, analytics):
    by_signature = {signature(row): row for row in rows}
    available = set(by_signature)
    findings, covered = [], []
    candidates = [row for row in store.objects('industry_cache') if row.get('schema') == SCHEMA and row['context'] == key]
    candidates.sort(key=lambda row: (len(row['members']), row['created']), reverse=True)
    for cached in candidates:
        members = set(cached['members'].values())
        if not members or not members <= available:
            continue
        projected, ids = projection(cached, by_signature, analytics['window'])
        findings.extend(projected)
        covered.extend(ids)
        available -= members
    return findings, covered, [by_signature[value] for value in sorted(available)]


def _config(store, version):
    from .analysis_config import DEFAULT
    if version == 0:
        return {'version': 0, 'config': DEFAULT}
    return next((row for row in store.objects('analysis_config') if row['version'] == version), None)


def _verified_input(batch, report, config, policy):
    from .industry import INSTRUCTION
    known = {row['id']: row for row in report.get('evidence', [])}
    if not set(batch['covered_ids']) <= set(known):
        return None
    original = sorted((known[identity] for identity in batch['covered_ids']), key=lambda row: row['id'])
    visibilities = [batch['findings'][0]['visibility']] if batch['findings'] else ['public', 'internal']
    for visibility in visibilities:
        data = {'task': 'industry_analysis', 'topic': policy['topic'],
                **{key: config['config'][key] for key in ('industry', 'region', 'focus')},
                'window': report['window'], 'visibility': visibility, 'evidence': original}
        expected = 'industry-batch:' + hashlib.sha256(json.dumps({'instruction': INSTRUCTION, 'input': data,
            'config_version': report['config_version'], 'datasets': report['datasets']}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if expected == batch['id']:
            return original, visibility
    return None


def _current_rows(store, original, current):
    from .organization import material_id
    sources = {row['id']: row for row in store.objects('source')}
    resolved = []
    for row in original:
        live = current.get(row['id'])
        if live is None:
            return None
        if 'organization_id' in row:
            source = sources.get(row['id'])
            if not source or material_id({'topic': source.get('scope_topic', '')}, source) != row['organization_id']:
                return None
            if any(live.get(key) != value for key, value in row.items() if key not in LEGACY_EXTRA_FIELDS):
                return None
        elif live != row:
            return None
        resolved.append(live)
    return resolved


def migrate(store, policy, config, analytics, groups):
    from .industry import validate_findings
    current = {row['id']: row for _, rows in groups for row in rows}
    migrated = {row['legacy_id'] for row in store.objects('industry_cache') if row.get('legacy_id')}
    batches = [row for row in store.objects('industry_batch') if row['id'] not in migrated and set(row['covered_ids']) <= set(current)]
    if not batches:
        return
    reports = [row for row in store.objects('industry_report') if row.get('scope_topic') == policy['topic']]
    for batch in batches:
        for report in reports:
            old_config = _config(store, report['config_version'])
            if not old_config or any(old_config['config'][key] != config['config'][key] for key in ('industry', 'region', 'focus')):
                continue
            verified = _verified_input(batch, report, old_config, policy)
            if not verified:
                continue
            original, visibility = verified
            kinds = {'source' if 'organization_id' in row else 'business' for row in original}
            kind = next(iter(kinds)) if len(kinds) == 1 else 'mixed'
            if kind != 'source' and any(report[key] != analytics[key] for key in ('window', 'datasets', 'config_version')):
                continue
            resolved = _current_rows(store, original, current)
            if not resolved:
                continue
            findings = validate_findings({'findings': batch['findings']}, set(batch['covered_ids']), visibility)
            key = context(policy, config, visibility, kind, analytics)
            saved = save(store, key, resolved, findings, report, legacy=batch['id'], analyzed_at=batch.get('created', report['created']))
            store.event('industry_cache_migrated', {'legacy_id': batch['id'], 'cache_id': saved['id']})
            break
