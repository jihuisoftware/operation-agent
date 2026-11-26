"""Topic-local receipts for cover previews. Admission precedes every paid dispatch."""
import base64
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
import hashlib
import json
import logging
import re

import psutil

from .content_release import fingerprint
from .policy import local_day, now_iso
from .store import encoded

_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='cover-designer')
KIND = 'designer_cover_job'


def read(db, key):
    row = db.execute('SELECT data FROM objects WHERE id=? AND kind=?', (key, KIND)).fetchone()
    if not row:
        raise ValueError('此主题中未找到封面任务')
    return json.loads(row[0])


def save(db, job):
    db.execute('UPDATE objects SET data=? WHERE id=? AND kind=?', (encoded(job), job['id'], KIND))


def origin(db, kind, identity):
    if kind == 'writing':
        from .writing_drafts import read as read_draft
        draft = read_draft(db, identity)
        if draft.get('archived'):
            raise ValueError('写作草稿已归档')
        return draft['revision'], draft
    if kind != 'content':
        raise ValueError('封面归属类型无效')
    row = db.execute("SELECT data FROM objects WHERE kind='content' AND id=?", (identity,)).fetchone()
    if not row:
        raise ValueError('此主题中未找到稿件')
    data = json.loads(row[0])
    return fingerprint(data), data


def current(db, job):
    version = db.execute('SELECT version FROM settings WHERE id=1').fetchone()[0]
    revision, draft = origin(db, job['kind'], job['origin_id'])
    if revision != job['revision'] or version != job['version']:
        raise ValueError('稿件或计划已变化，请用当前版本重新预览封面')
    return draft


def options(body):
    mode = body.get('mode')
    if mode not in ('upload', 'background', 'ai', 'reuse'):
        raise ValueError('封面方式无效')
    if mode == 'upload':
        return {}
    limits = {'title': 80, 'subtitle': 120, 'style': 400}
    spec = {key: body.get(key, '') for key in limits}
    if any(not isinstance(text, str) or len(text) > limits[key] for key, text in spec.items()):
        raise ValueError('标题、副标题或风格描述过长')
    if mode != 'upload' and not spec['title'].strip():
        raise ValueError('请填写封面标题')
    for axis in ('x', 'y'):
        coord = body.get(axis, 0.5)
        if type(coord) not in (int, float) or not 0 <= coord <= 1:
            raise ValueError('裁切位置无效')
        spec[axis] = coord
    return spec


def admit(store, body, automatic):
    key = body.get('request_id')
    if not isinstance(key, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', key):
        raise ValueError('生成请求标识无效')
    key = ('designer-auto:' if automatic else 'designer:') + key
    spec = options(body)
    digest = hashlib.sha256(encoded(body).encode()).hexdigest()
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM objects WHERE id=?', (key,)).fetchone():
            job = read(db, key)
            if job['digest'] != digest:
                raise ValueError('此生成请求已有不同参数')
            return job, False
        version, raw_policy = db.execute('SELECT version,data FROM settings WHERE id=1').fetchone()
        revision, draft = origin(db, body['kind'], body['origin_id'])
        if revision != body['revision'] or version != body['version']:
            raise ValueError('稿件或计划已变化，请重新打开')
        proc = psutil.Process()
        job = dict(id=key, kind=body['kind'], origin_id=body['origin_id'], revision=revision, version=version,
                   mode=body['mode'], spec=spec, digest=digest, state='queued', automatic=automatic, charged=False,
                   pid=proc.pid, process_started=proc.create_time(), day=local_day(json.loads(raw_policy)))
        if job['kind'] == 'content':
            from .content_release import load
            job['release_revision'] = (load(db, job['origin_id']) or {}).get('revision', 0)
        if job['mode'] == 'reuse':
            prior = read(db, body.get('previous'))
            if (prior['kind'], prior['origin_id']) != (job['kind'], job['origin_id']):
                # Automatic text revisions share the original manuscript's background.
                if not automatic or prior['origin_id'] != draft.get('revision_root_id'):
                    raise ValueError('底图不属于当前稿件')
            if not prior.get('background'):
                raise ValueError('没有可复用的底图')
            job['background'] = prior['background']
        db.execute('INSERT INTO objects(id,kind,data,created) VALUES(?,?,?,?)', (key, KIND, encoded(job), now_iso()))
    return job, True


def reserve_dispatch(store, job):
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        current(db, job)
        if job['automatic']:
            policy = json.loads(db.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])
            day = local_day(policy)
            if day != job['day'] or policy.get('paused') or not policy.get('enabled'):
                raise ValueError('运营日期已变化或计划已停用')
            used = db.execute("SELECT count(*) FROM objects WHERE kind=? AND json_extract(data,'$.automatic')=1 "
                              "AND json_extract(data,'$.charged')=1 AND json_extract(data,'$.day')=?", (KIND, day)).fetchone()[0]
            if used >= policy.get('designer_daily_limit', 1):
                raise ValueError('已达到本主题当日自动生图限额')
        job.update(charged=True, state='running')
        save(db, job)


def status(store, key):
    with store.connection() as db:
        job = read(db, key)
        if job['state'] not in ('queued', 'running'):
            return job
        try:
            alive = psutil.Process(job['pid']).create_time() == job['process_started']
        except psutil.NoSuchProcess:
            alive = False
        if not alive:
            db.execute('BEGIN IMMEDIATE')
            job = read(db, key)
            if job['state'] in ('queued', 'running'):
                state = 'unknown' if job['charged'] else 'failed'
                job.update(state=state, error='执行进程已退出，请核对后手动重新生成')
                save(db, job)
    return job


def latest(store, kind, identity):
    with store.connection() as db:
        row = db.execute("SELECT id FROM objects WHERE kind=? AND json_extract(data,'$.kind')=? "
                         "AND json_extract(data,'$.origin_id')=? ORDER BY rowid DESC LIMIT 1", (KIND, kind, identity)).fetchone()
    return status(store, row[0]) if row else None


def execute(store, job, upload):
    from . import designer_render as engine
    try:
        engine.check_plugin()
        if job['mode'] == 'ai':
            from . import visual_provider
            if not visual_provider.available():
                raise ValueError('请先配置可用的生图模型')
            prompt = engine.background_prompt(job['spec'])
            reserve_dispatch(store, job)
            background = engine.generate_background(store, prompt)
        elif upload:
            background = store.add_asset(upload['name'], base64.b64decode(upload['data'], validate=True), True)
        else:
            background = job['background']
        job['background'] = background
        job['asset_id'] = engine.render(store, job)
        job['state'] = 'completed'
    except Exception as error:
        logging.getLogger(__name__).exception("Cover generation failed: %s", job["id"])
        job.update(state='unknown' if job['charged'] and not job.get('background') else 'failed', error=str(error)[:800])
    with store.connection() as db:
        save(db, job)
    return job


def start(store, body, *, automatic=False):
    upload = body.get('upload')
    if body.get('mode') in ('upload', 'background'):
        if not isinstance(upload, dict) or upload.get('authorized') is not True:
            raise ValueError('请确认上传图片的使用授权')
        if not isinstance(upload.get('data'), str) or len(upload['data']) > 27962028:
            raise ValueError('图片超过20 MB或数据无效')
    elif upload is not None:
        raise ValueError('此方式无需上传文件')
    job, fresh = admit(store, body, automatic)
    if not fresh:
        return status(store, job['id'])
    if automatic:
        return execute(store, job, upload)
    try:
        _POOL.submit(copy_context().run, execute, store, job.copy(), upload)
    except RuntimeError as error:
        job.update(state='failed', error=f'封面任务未启动：{error}')
        with store.connection() as db:
            save(db, job)
    return job
