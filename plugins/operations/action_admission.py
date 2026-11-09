"""Pending receipts fence the original publication, not unrelated manuscripts."""
import json

from .outcomes import StageSkipped


class ActionDeferred(StageSkipped, ValueError):
    def __init__(self, row, *, scope=None, publication=False, completed=False):
        data = json.loads(row['data']) if row.get('data') else {}
        original = {key: row.get(key) for key in ('id', 'kind', 'state', 'created')}
        original.update({key: (scope or {}).get(key) or data.get(key) for key in ('business_id', 'topic_id')})
        original['batch_id'] = data.get('manual_run_id') or data.get('run_id')
        message = ('同一内容' if publication else '同类动作') + '仍有未核对结果，本次未执行；请核对原记录 ' + row['id']
        if completed:
            message = '相同内容已发布，本次未重复提交；原记录 ' + row['id']
        self.result = {'state': 'not_started', 'submitted': False, 'error_code': 'ALREADY_PUBLISHED' if completed else 'ACTION_PENDING',
                       'error': message, 'blocking_action': original}
        super().__init__(message)


def check_pending(db, action):
    row = db.execute("SELECT * FROM actions WHERE kind=? AND state IN ('unknown','submitted','executing','queued') "
                     "AND json_extract(data,'$.account_id')=? AND (?!='publish' OR json_extract(data,'$.target')=?) "
                     'ORDER BY created LIMIT 1',
                     (action['kind'], action['account_id'], action['kind'], action['target'])).fetchone()
    if row:
        raise ActionDeferred(dict(row), publication=action['kind'] == 'publish')


def shared_pending(db, account, action, scope, identity):
    row = db.execute("SELECT a.*,t.business_id FROM directory.account_actions a JOIN directory.topics t ON t.id=a.topic_id "
                     "WHERE a.account_id=? AND a.kind=? AND a.state IN ('queued','executing','submitted','unknown') "
                     "AND NOT (a.topic_id=? AND a.action_id=?) AND (?!='publish' OR EXISTS(SELECT 1 FROM directory.account_claims c "
                     "WHERE c.account_id=a.account_id AND c.kind=a.kind AND c.action_id=a.action_id AND c.topic_id=a.topic_id AND c.target=?)) LIMIT 1",
                     (account, action['kind'], scope['id'], identity, action['kind'], action['target'])).fetchone()
    if row:
        raise ActionDeferred({'id': row['action_id'], 'kind': row['kind'], 'state': row['state']},
                             scope=dict(row), publication=action['kind'] == 'publish')


def check_replay(store, db, action, identity):
    """Known-unsubmitted retries still respect another pending copy of the same post."""
    if action['kind'] == 'publish':
        from .publication_attempts import guard, unsubmitted
        from .publication_shared import history
        row = db.execute('SELECT * FROM actions WHERE id=?', (identity,)).fetchone()
        if not row or not unsubmitted(db, dict(row)):
            raise ValueError('原发布动作未结束或提交证据不明，请先核对')
        guard(db, action, skip=identity)
        history(store, db, action)
        return
    check_pending(db, action)
    if store.workspace:
        from .execution_pause import account_key
        shared_pending(db, account_key(store, db), action, store.scope, identity)


def check_resume(db, pause):
    key = pause['id']
    batch = key.removeprefix('manual:')
    pending = db.execute("SELECT id FROM actions WHERE state IN ('unknown','submitted','executing','queued') AND "
                         "(json_extract(data,'$.manual_run_id') IN (?,?) OR json_extract(data,'$.resume_key')=? "
                         "OR json_extract(data,'$.run_id') IN (?,?)) LIMIT 1",
                         (key, batch, key, key, pause.get('run_id'))).fetchone()
    if pending:
        raise ValueError('本批次仍有未完成或结果未知的外部动作，请先核对原动作 ' + pending['id'])
