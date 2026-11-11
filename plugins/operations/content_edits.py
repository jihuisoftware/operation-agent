"""Update the current manuscript in place, retaining old text and action snapshots for audit."""

from .content_release import load
from .policy import now_iso
from .store import encoded


def action_match(action='a', content='c'):
    return (f"COALESCE(json_extract({action}.data,'$.content.edit_revision'),0)="
            f"COALESCE(json_extract({content}.data,'$.edit_revision'),0)")


def latest_action(db, identity, content):
    return db.execute("SELECT * FROM actions WHERE kind='publish' AND json_extract(data,'$.content.id')=? "
                      "AND COALESCE(json_extract(data,'$.content.edit_revision'),0)=? ORDER BY rowid DESC LIMIT 1",
                      (identity, content.get('edit_revision', 0))).fetchone()


def write(db, identity, current, value):
    active = db.execute("SELECT 1 FROM actions WHERE kind='publish' AND json_extract(data,'$.content.id')=? "
                        "AND state IN ('queued','executing') LIMIT 1", (identity,)).fetchone()
    if active:
        raise ValueError('这篇内容正在发布，请等待当前执行结束后再编辑')
    revision = current.get('edit_revision', 0) + 1
    release = load(db, identity)
    stamp = now_iso()
    db.execute("INSERT INTO objects VALUES (?,'content_edit_history',?,?)",
               (f'content-edit:{identity}:{revision}', encoded({'content_id': identity, 'content': current,
                'release': release, 'replaced_at': stamp}), stamp))
    if release and release['state'] != 'cancelled':
        release.update(state='cancelled', revision=release['revision'] + 1,
                       detail='内容已修改，原审核与排期已失效；请重新审核并设置发布时间')
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(release), 'content-release:' + identity))
    value.pop('parent_content_id', None)
    if current.get('parent_content_id'):
        value['parent_content_id'] = current['parent_content_id']
    value.update(edit_revision=revision, revision_root_id=current.get('revision_root_id') or identity,
                 created=current.get('created', stamp), updated=stamp)
    db.execute("UPDATE objects SET data=? WHERE id=? AND kind='content'", (encoded(value), identity))
