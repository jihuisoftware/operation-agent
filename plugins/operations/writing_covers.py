"""Working-copy cover previews reuse local artwork without creating formal content."""
from .writing_drafts import read, check_revision
from .cover_design import normalized, options
from .cover_assets import candidates


def preview(store, identity, body):
    with store.connection() as db:
        draft = read(db, identity)
    check_revision(draft, body)
    spec = normalized(body.get('cover'), draft['title'], strict=True)
    return {'candidates': candidates(store, spec), 'set_id': '', 'revision': draft['revision'], 'model_calls': 0, **options()}
