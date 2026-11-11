"""Select an approved scheduled manuscript, or an explicitly invoked debug candidate."""
from datetime import datetime, UTC

from .outcomes import StageSkipped, describe
from .policy import local_day
from .store import encoded


def choose(store, policy, day, content_id):
    from .debug_authorization import allowed
    from .content_release import manuscript
    if getattr(store, 'debug_id', None):
        if not allowed(store, policy, 'publish'):
            raise StageSkipped('本次调试发布尚未授权')
        drafts = [row for row in store.objects('content', day) if row.get('ready') and (content_id is None or row['id'] == content_id)]
        if not drafts:
            raise StageSkipped('没有完整可检查的图文，请先生成内容')
        return drafts[0], None
    due = [row for row in store.objects('content_release') if row['state'] == 'scheduled'
           and datetime.fromisoformat(row['publish_at']) <= (getattr(store, 'execution_now', None) or datetime.now(UTC))
           and (content_id is None or row['content_id'] == content_id)]
    if not due:
        raise StageSkipped('等待人工审核并设置发布时间；不会自动发布未审核稿件')
    release = min(due, key=lambda row: row['publish_at'])
    return manuscript(store, release['content_id']), release


def publish_due(store, now):
    version, policy = store.policy()
    if not policy['enabled'] or policy['paused'] or not policy['modules']['publish'] or not store.online():
        return False
    due = sorted((row for row in store.objects('content_release') if row['state'] == 'scheduled'
                  and datetime.fromisoformat(row['publish_at']) <= now), key=lambda row: row['publish_at'])
    if not due:
        return False
    release = due[0]
    from .workflow import publish
    from .execution_pause import ExecutionPaused
    run = store.start_run(local_day(policy, now), 'publish', f"content-release:{release['content_id']}:{release['revision']}", version)
    state, detail = 'needs_attention', '此前排期执行已开始，请先核对执行记录；不会自动重发'
    if run:
        try:
            from .execution_preflight import verify_for_start
            verify_for_start(store, version)
            result = publish(store, policy, local_day(policy, now), version, content_id=release['content_id'])
            state, detail = describe('publish', result)
        except ExecutionPaused as exc:
            state, detail = 'paused', str(exc)
        except (ValueError, StageSkipped) as exc:
            state, detail = 'needs_attention', str(exc)
        store.finish_run(run, state, detail)
    with store.connection() as db:
        release.update(state='published' if state == 'completed' else state, detail=detail, run_id=run)
        db.execute("UPDATE objects SET data=? WHERE id=? AND json_extract(data,'$.revision')=?",
                   (encoded(release), 'content-release:' + release['content_id'], release['revision']))
    return True
