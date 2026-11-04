"""Checkpoint each validated evidence batch before advancing to the next call."""
import hashlib
import json

from .analysis_runs import guard
from .analytics import valid
from .collection_ledger import load
from .policy import now_iso
from .model_errors import ModelServiceUnavailable

BATCH_SIZE = 20


def check_current(store, analytics, policy, day, version):
    guard(store, policy)
    if store.policy() != (version, policy) or not valid(store, analytics, policy, day):
        raise ValueError('分析配置或数据权限发生变化，本轮停止')


def analyze_batches(store, policy, day, version, analytics, config, groups, budget):
    from .industry import INSTRUCTION, generate, validate_findings
    findings, covered, errors, calls, reused = [], [], [], 0, 0
    service_failed = False
    total = sum(len(rows) for _, rows in groups)
    for visibility, rows in groups:
        ordered = sorted(rows, key=lambda row: row['id'])
        for start in range(0, len(ordered), BATCH_SIZE):
            check_current(store, analytics, policy, day, version)
            batch = ordered[start:start + BATCH_SIZE]
            ids = [row['id'] for row in batch]
            data = {'task': 'industry_analysis', 'topic': policy['topic'],
                    **{key: config['config'][key] for key in ('industry', 'region', 'focus')},
                    'window': analytics['window'], 'visibility': visibility, 'evidence': batch}
            fingerprint = json.dumps({'instruction': INSTRUCTION, 'input': data,
                                      'config_version': analytics['config_version'], 'datasets': analytics['datasets']},
                                     ensure_ascii=False, sort_keys=True)
            identity = 'industry-batch:' + hashlib.sha256(fingerprint.encode()).hexdigest()
            checkpoint = load(store, identity)
            if checkpoint:
                findings.extend(checkpoint['findings'])
                covered.extend(ids)
                reused += len(ids)
                continue
            if calls >= budget or service_failed:
                continue
            store.progress('正在分析行业证据', {'visibility': visibility, 'completed': len(covered), 'total': total})
            calls += 1
            try:
                result = generate(store, policy, day, INSTRUCTION, data)
                validated = validate_findings(result, set(ids), visibility)
            except (ValueError, TimeoutError, ModelServiceUnavailable) as exc:
                service_failed = isinstance(exc, ModelServiceUnavailable)
                errors.append(str(exc))
                store.event('industry_analysis_error', {'day': day, 'error': str(exc), 'evidence_ids': ids})
                continue
            check_current(store, analytics, policy, day, version)
            store.put('industry_batch', {'day': day, 'findings': validated, 'covered_ids': ids, 'created': now_iso()}, identity)
            findings.extend(validated)
            covered.extend(ids)
    return {'findings': findings, 'covered_ids': covered, 'errors': errors, 'model_calls': calls, 'reused': reused}
