"""Retain individually verified candidates when a new planning request fails."""
from .analytics import valid
from .policy import now_iso
from .research import save_brief
from .topic_cache import guard


def verified_sources(brief, evidence):
    signatures = set(brief.get('result', {}).get('organization_ids', []))
    snapshots = brief.get('result', {}).get('organized_evidence')
    return {row['id'] for row in evidence if row['organization_id'] in signatures
            and (snapshots is None or row in snapshots)}


def verified_candidates(brief, usable):
    from .topics import candidates
    # Validate each candidate independently; an invalid sibling must not discard good work.
    rows = []
    for item in brief.get('result', {}).get('topics', [])[:12]:
        try:
            candidate = candidates({**brief, 'result': {'topics': [item]}})
        except ValueError:
            continue
        if candidate and candidate[0]['source_ids'] and set(candidate[0]['source_ids']) <= usable:
            rows.extend(candidate)
    return rows


def recover(store, policy, day, version, error):
    from .industry import production_context, preferred_sources
    from .organization import production_evidence
    from .model_inputs import evidence as project
    guard(store, version)
    context = production_context(store, policy, day)
    sources, evidence = production_evidence(store, policy, day, preferred_sources(context))
    evidence = project(evidence)
    for brief in store.objects('brief', day):
        if brief.get('scope_topic') != policy['topic'] or brief.get('version') != version:
            continue
        analysis = brief['result'].get('analysis_context')
        if analysis and (not context or not valid(store, analysis, policy, day)):
            continue
        usable = verified_sources(brief, evidence)
        if not preferred_sources(analysis) <= usable:
            continue
        candidates = verified_candidates(brief, usable)
        if candidates:
            return save_partial(store, policy, day, version, brief, candidates, sources, evidence, error)
    return None


def save_partial(store, policy, day, version, brief, candidates, sources, evidence, error):
    cited = {identity for item in candidates for identity in item['source_ids']}
    selected = [source for source in sources if source['id'] in cited]
    used = [row for row in evidence if row['id'] in cited]
    # Preserve provenance without pretending the failed request produced a full cache entry.
    result = {'topics': candidates, 'analysis_context': brief['result'].get('analysis_context'),
              'organization_ids': [row['organization_id'] for row in used], 'organized_evidence': used,
              'reused_from': brief['id'], 'origin_day': brief['day'], 'revalidated_at': now_iso(),
              'partial': True, 'error': str(error)}
    guard(store, version)
    identity = save_brief(store, day, result, selected, scope_topic=policy['topic'], version=version)
    outcome = {'brief_id': identity, 'usable': len(candidates), 'state': 'needs_attention',
               'detail': f'选题部分可用：已核对并保留 {len(candidates)} 个有效选题，可继续内容生产；本次新增选题未完成。{error}'}
    store.event('topics_partial', {**outcome, 'reused_from': brief['id']})
    return outcome
