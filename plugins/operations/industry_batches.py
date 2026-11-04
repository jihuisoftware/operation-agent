"""Reuse stable evidence cohorts before spending calls on new or changed inputs."""
from .analysis_runs import guard
from .analytics import valid
from .model_errors import ModelServiceUnavailable

BATCH_SIZE = 20


def check_current(store, analytics, policy, day, version):
    guard(store, policy)
    if store.policy() != (version, policy) or not valid(store, analytics, policy, day):
        raise ValueError('分析配置或数据权限发生变化，本轮停止')


def _groups(groups):
    for visibility, rows in groups:
        for kind in ('source', 'business'):
            selected = [row for row in rows if ('organization_id' in row) == (kind == 'source')]
            if selected:
                yield visibility, kind, selected


def _generate(store, policy, day, analytics, config, visibility, kind, batch):
    from .industry import INSTRUCTION, generate, validate_findings
    from .industry_cache import SOURCE_SCOPE
    data = {'task': 'industry_analysis', 'topic': policy['topic'],
            **{key: config['config'][key] for key in ('industry', 'region', 'focus')},
            'visibility': visibility, 'evidence': batch}
    if kind == 'source':
        data['scope_kind'] = 'fixed_documents'
        data['evidence'] = [{key: value for key, value in row.items()
                             if key not in {'day', 'content_fingerprint', 'source_complete'}} for row in batch]
    else:
        data['window'] = analytics['window']
    result = generate(store, policy, day, INSTRUCTION + (SOURCE_SCOPE if kind == 'source' else ''), data)
    return validate_findings(result, {row['id'] for row in batch}, visibility)


def analyze_batches(store, policy, day, version, analytics, config, groups, budget):
    from .industry_cache import context, migrate, projection, reusable, save, signature
    check_current(store, analytics, policy, day, version)
    migrate(store, policy, config, analytics, groups)
    findings, covered, errors, pending = [], [], [], []
    total = sum(len(rows) for _, rows in groups)
    for visibility, rows in groups:
        key = context(policy, config, visibility, 'mixed', analytics)
        saved_findings, ids, _ = reusable(store, key, rows, analytics)
        findings.extend(saved_findings)
        covered.extend(ids)
    for visibility, kind, original_rows in _groups(groups):
        rows = [row for row in original_rows if row['id'] not in covered]
        key = context(policy, config, visibility, kind, analytics)
        saved_findings, ids, remaining = reusable(store, key, rows, analytics)
        findings.extend(saved_findings)
        covered.extend(ids)
        pending.extend((visibility, kind, key, remaining[start:start + BATCH_SIZE])
                       for start in range(0, len(remaining), BATCH_SIZE))
    reused, calls = len(covered), 0
    quick = bool((store.run_options or {}).get('quick'))
    maximum = min(budget, 1) if quick else budget
    for visibility, kind, key, batch in pending:
        check_current(store, analytics, policy, day, version)
        if calls >= maximum:
            break
        store.progress('正在分析新增或变化的行业证据', {'visibility': visibility, 'completed': len(covered), 'total': total, 'reused': reused})
        calls += 1
        try:
            validated = _generate(store, policy, day, analytics, config, visibility, kind, batch)
        except (ValueError, TimeoutError, ModelServiceUnavailable) as exc:
            errors.append(str(exc))
            store.event('industry_analysis_error', {'day': day, 'error': str(exc), 'evidence_ids': [row['id'] for row in batch]})
            if isinstance(exc, ModelServiceUnavailable):
                break
            continue
        check_current(store, analytics, policy, day, version)
        cached = save(store, key, batch, validated, analytics)
        projected, ids = projection(cached, {signature(row): row for row in batch}, analytics['window'])
        findings.extend(projected)
        covered.extend(ids)
    coverage = {'mode': 'sample' if quick else 'full', 'total': total, 'reused': reused,
                'newly_analyzed': len(covered) - reused, 'pending': total - len(covered),
                'new_batches': calls, 'max_new_batches': 1 if quick else None}
    return {'findings': findings, 'covered_ids': covered, 'errors': errors, 'model_calls': calls, 'reused': reused, 'coverage': coverage}
