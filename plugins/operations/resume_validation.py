"""Previously generated artifacts remain reusable only while their evidence and permissions hold."""
from .execution_pause import identity


def check(store, pause):
    from .content import validate_content
    from .industry import check_public_context
    from .organization import material_id
    policy = store.policy()[1]
    store.resume_artifacts = dict(pause.get('artifacts') or {})
    if store.resume_artifacts.get('analytics_report_id'):
        from .industry import production_context
        production_context(store, policy, pause['day'])
    if store.resume_artifacts.get('brief_id'):
        from .topics import production_topic
        production_topic(store, policy, pause['day'])
    sources = {row['id']: row for row in store.objects('source')}
    assets = [row for row in store.objects('asset') if row.get('authorized') and not row.get('revoked')]
    for draft in store.objects('content', pause['day']):
        owner = draft.get('debug_id') or draft.get('manual_run_id')
        belongs = owner == store.manual_run_id if store.manual_run_id else draft.get('run_id') == pause['run_id']
        if not belongs:
            continue
        validate_content(draft, list(sources.values()), assets)
        check_public_context(store, draft, policy, pause['day'])
        for row in draft.get('organized_evidence', []):
            source = sources.get(row['id'])
            if source is None or material_id(policy, source) != row['organization_id']:
                raise ValueError('已完成草稿的来源发生变化，请发起新批次')
    from .topics import catalog
    selected = catalog(store, policy, pause['day']).get('selected')
    if selected and identity(store).startswith('debug:'):
        records = [row for row in store.objects('content', pause['day']) if row.get('debug_id') == identity(store)]
        if records and any((row.get('selected_topic') or {}).get('title') != selected['title'] for row in records):
            raise ValueError('已选择其他选题，请发起新批次')
