"""Request a revision-bound cover from the optional designer, retaining an editable draft on failure."""
from .content_release import fingerprint
from .designer_workflow import candidate


def with_candidate(store, content, owner, *, kind='content', automatic=False, replace=False):
    if content.get('asset_ids') and not replace:
        return content
    revision = owner['revision'] if kind == 'writing' else fingerprint(owner)
    try:
        job = candidate(store, kind, owner['id'], revision, content['title'], automatic=automatic,
                        manuscript_body=content.get('body', ''))
    except ValueError as exc:
        return {**content, 'ready': False, 'state': 'needs_material', 'cover_error': str(exc)}
    inner = content.get('asset_ids', [])[1:] if replace else content.get('asset_ids', [])
    return {**content, 'asset_ids': list(dict.fromkeys([job['asset_id'], *inner])), 'cover_origin': 'designer',
            'designer_applied_title': content['title'], 'designer_background_job': job['id'], 'cover_error': ''}
