"""Explicit local cover previews bound to an immutable manuscript revision."""
import hashlib

from .content_release import manuscript, fingerprint
from .cover_design import normalized, options, RENDER_VERSION
from .cover_assets import candidates
from .store import encoded


def preview(store, identity, body):
    content = manuscript(store, identity)
    version = store.policy()[0]
    if body.get('version') != version or body.get('content_revision') != fingerprint(content):
        raise ValueError('稿件或规则已变化，请刷新后生成候选封面')
    spec = normalized(body.get('cover'), content['title'], strict=True)
    choices = candidates(store, spec)
    record = {'content_id': identity, 'content_revision': fingerprint(content), 'version': version,
              'candidates': choices, 'renderer': RENDER_VERSION}
    key = 'cover-set:' + hashlib.sha256(encoded(record).encode()).hexdigest()
    store.put('cover_set', record, key)
    return {'set_id': key, 'candidates': choices, **options(), 'model_calls': 0}
