"""Operator-facing reasons and suggested recovery actions from durable facts."""
import json
from .review_queue import load


def issue(row):
    result = json.loads(row['result']) if isinstance(row['result'], str) else row['result']
    status = result.get('publication', {})
    error = str(result.get('error', ''))
    if row['state'] in {'published', 'confirmed', 'cancelled', 'confirmed_not_published'}:
        return {'kind': 'resolved', 'title': '处理完成', 'help': '可查看最终稿、原始回执与人工核对历史。'}
    if status.get('content') == 'mismatch':
        return {'kind': 'mismatch', 'title': '内容不一致', 'help': '对比最终稿与页面核对结果，确认差异后再人工处理；不会自动重发。'}
    if status.get('platform') == 'rejected':
        return {'kind': 'rejected', 'title': '审核未通过', 'help': '查看平台原因；修改稿件会产生新版本，原笔记不会自动删除或重发。'}
    if status.get('platform') == 'reviewing':
        return {'kind': 'reviewing', 'title': '等待平台审核', 'help': '后台将继续只读检查，也可立即核对。'}
    if any(word in error for word in ('登录', '扫码', '账号', '验证')):
        return {'kind': 'login', 'title': '需要检查登录', 'help': '进入账号登录完成处理，再恢复运营规则并核对原动作。'}
    if 'upload' in error or '上传' in error:
        return {'kind': 'upload', 'title': '图片上传未完成', 'help': '检查素材与网络；先确认未提交成功，再选择重新执行。'}
    if status.get('content') == 'incomplete':
        return {'kind': 'images', 'title': '图片核对不完整', 'help': '可查看原图、平台图和相似度参考；参考相似度不代表精确一致。'}
    return {'kind': 'pending', 'title': '等待核对结果', 'help': '结果不明时只检查原动作，不重新发布。'}


def detail(store, identity):
    from .publication_snapshot import read
    with store.connection() as db:
        row = db.execute('SELECT * FROM actions WHERE id=?', (identity,)).fetchone()
        if not row:
            raise ValueError('动作不存在')
        history = [json.loads(r[0]) for r in db.execute("SELECT data FROM objects WHERE kind='manual_conclusion' AND json_extract(data,'$.action_id')=? ORDER BY created", (identity,))]
        tracking = load(db, identity)
    return {'issue': issue(dict(row)), 'tracking': tracking, 'snapshot': read(store, identity), 'manual_history': history}
