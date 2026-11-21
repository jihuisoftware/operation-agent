"""Current report snapshot distinguishes review decisions from actual external publication."""
from .content_release import load


def summary(scope):
    automatic = manual = pending = 0
    with scope.store.connection() as db:
        for content in scope.objects('content'):
            release = load(db, content['id'])
            if release and release['state'] != 'cancelled':
                automatic += release.get('reviewer') == 'automatic'
                manual += release.get('reviewer', 'human') == 'human'
            elif content.get('automatic_review'):
                automatic += bool(content['automatic_review'].get('approved'))
                pending += not content['automatic_review'].get('approved')
    return ['', f'内容审核：人工通过 {manual} 篇，自动通过 {automatic} 篇，自动检查转人工 {pending} 篇；审核通过不代表已经发布。', '']
