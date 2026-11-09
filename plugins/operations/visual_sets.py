"""Resumable, content-addressed visual sets with a durable three-attempt image allowance."""
import hashlib
import json
import logging
import uuid

from . import visual_plan, visual_provider, visual_render, visual_job_state
from .policy import now_iso, local_day
from .store import encoded


def read(store, identity):
    with store.connection() as db:
        row = db.execute("SELECT data FROM objects WHERE kind='visual_set' AND id=?", (identity,)).fetchone()
    if not row:
        raise ValueError('组图任务不存在于当前主题')
    return json.loads(row[0])


def save(store, record, *, resume=False):
    record['updated'] = now_iso()
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if not visual_job_state.owned(db, store, record['id']):
            return
        current = db.execute("SELECT data FROM objects WHERE kind='visual_set' AND id=?", (record['id'],)).fetchone()
        if current and json.loads(current[0]).get('cancelled') and not resume:
            record.update(cancelled=True, state='cancelled', detail='组图任务已取消，已完成素材保留')
        db.execute("UPDATE objects SET data=? WHERE kind='visual_set' AND id=?", (encoded(record), record['id']))


def create(store, content, origin):
    signature = visual_plan.signature(content)
    selection = visual_provider.selection()
    identity = 'visual-set:' + hashlib.sha256(encoded([signature, origin, selection, store.policy()[0], visual_plan.VERSION, visual_render.VERSION]).encode()).hexdigest()
    record = {'id': identity, 'input_signature': signature, 'origin': origin, 'selection': selection,
              'state': 'queued', 'detail': '等待设计组图', 'created': now_iso(), 'pages': [], 'art': {}, 'attempts': [],
              'allowance_key': origin['kind'] + ':' + (content.get('revision_root_id') or origin['id']), 'plan': None, 'policy_version': store.policy()[0]}
    store.put('visual_set', record, identity)
    return read(store, identity)


def check(store, record):
    from .batch_cancellation import check as cancelled
    cancelled(store)
    from .workspace_execution import check_running
    check_running(store)
    if store.policy()[1]['paused']:
        raise ValueError('运营已暂停，停止组图调用')
    with store.connection() as db:
        if not visual_job_state.owned(db, store, record['id']):
            raise ValueError('组图执行代次已变化，停止旧任务')
    current = read(store, record['id'])
    if current.get('cancelled'):
        raise ValueError('组图任务已取消，已完成图片仍保留')
    from .visual_jobs import origin_content
    content = origin_content(store, record['origin'])
    if visual_plan.signature(content) != record['input_signature'] or store.policy()[0] != record['policy_version']:
        raise ValueError('稿件或运营规则已变化，已生成素材保留，不能应用旧组图')
    if visual_provider.selection() != record['selection']:
        raise ValueError('生图配置已变化，请重新生成组图')


def reserve(store, record, index):
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if not visual_job_state.owned(db, store, record['id']):
            raise ValueError('组图任务已中断')
        records = [json.loads(row[0]) for row in db.execute("SELECT data FROM objects WHERE kind='visual_set' AND json_extract(data,'$.allowance_key')=?", (record['allowance_key'],))]
        used = sum(len(row['attempts']) for row in records)
        if used >= 3:
            raise ValueError('本稿已达到最多2张主视觉＋1次额外尝试；已完成图片保留，不再自动付费重试')
        if read_record := next((row for row in records if row['id'] == record['id']), None):
            record['attempts'] = read_record['attempts']
        attempt = {'id': uuid.uuid4().hex, 'page': index, 'state': 'dispatched', 'at': now_iso()}
        record['attempts'].append(attempt)
        record['detail'] = f'正在生成第 {index + 1} 页主视觉（本稿第 {used + 1}/3 次调用）'
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(record), record['id']))
    store.event('image_call', {'visual_set_id': record['id'], 'attempt_id': attempt['id'], 'day': local_day(store.policy()[1]), **record['selection']})
    return attempt


def art(store, record, page, index):
    key = str(index)
    if key in record['art']:
        return asset_bytes(store, record['art'][key])
    check(store, record)
    cache_key = 'visual-art:' + hashlib.sha256(encoded([record['selection'], visual_plan.art_prompt(page), record.get('art_revision', {}).get(key, 0)]).encode()).hexdigest()
    with store.connection() as db:
        cached = db.execute("SELECT data FROM objects WHERE kind='visual_art' AND id=?", (cache_key,)).fetchone()
    if cached:
        identity = json.loads(cached[0])['asset_id']
        raw = asset_bytes(store, identity)
        record['art'][key] = identity
        save(store, record)
        return raw
    attempt = reserve(store, record, index)
    try:
        from .visual_usage import call
        result = call(store, record, attempt, lambda: visual_provider.generate(visual_plan.art_prompt(page)))
        check(store, record)
        raw = visual_provider.image_bytes(result)
        identity = store.add_asset(f'组图主视觉-{index + 1}.png', raw, True)
        with store.connection() as db:
            data = json.loads(db.execute('SELECT data FROM objects WHERE id=?', (identity,)).fetchone()[0])
            data['generated_visual_art'] = True
            db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(data), identity))
        record['art'][key] = identity
        attempt.update(state='completed', asset_id=identity)
        asset_bytes(store, identity)
        store.put('visual_art', {'asset_id': identity}, cache_key)
        save(store, record)
        return raw
    except Exception:
        attempt['state'] = 'failed_or_unknown'
        save(store, record)
        raise


def asset_bytes(store, identity):
    from .publication_snapshot import asset_bytes as load
    with store.connection() as db:
        row = db.execute("SELECT data FROM objects WHERE id=? AND kind='asset'", (identity,)).fetchone()
    data = json.loads(row[0]) if row else {}
    if not data.get('authorized') or data.get('revoked'):
        raise ValueError('组图素材已撤回，请重新选择')
    return load({**data, 'id': identity})


def run(store, identity, content):
    record = read(store, identity)
    try:
        check(store, record)
        if record['input_signature'] != visual_plan.signature(content):
            raise ValueError('稿件已变化，本次组图不能应用到新版本')
        if not visual_provider.available():
            raise ValueError('尚未配置可用的生图模型，请在模型能力设置中配置；文字草稿已保留')
        record.update(state='running', detail='正在设计分页与视觉重点')
        save(store, record)
        if not record['plan']:
            record['plan'] = visual_plan.plan(store, content)
            save(store, record)
        if not record['pages']:
            from io import BytesIO
            from PIL import Image
            placeholder = BytesIO()
            Image.new('RGB', (1200, 800), '#F7F5EF').save(placeholder, format='PNG')
            for index, page in enumerate(record['plan']['pages']):
                visual_render.render(page, index, len(record['plan']['pages']), placeholder.getvalue() if page['art'] else None)
        for index, page in enumerate(record['plan']['pages']):
            check(store, record)
            if index < len(record['pages']):
                asset_bytes(store, record['pages'][index]['asset_id'])
                continue
            raw = art(store, record, page, index) if page['art'] else None
            check(store, record)
            rendered = visual_render.render(page, index, len(record['plan']['pages']), raw)
            asset_id = store.add_asset(f'杂志组图-{index + 1}.png', rendered, True)
            asset_bytes(store, asset_id)
            with store.connection() as db:
                data = json.loads(db.execute('SELECT data FROM objects WHERE id=?', (asset_id,)).fetchone()[0])
                data.update(generated_magazine=True, visual_page=page, visual_set_id=identity, visual_renderer=visual_render.VERSION)
                db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(data), asset_id))
            record['pages'].append({'asset_id': asset_id, 'title': page['title'], 'kind': page['kind'], 'has_art': bool(page['art'])})
            record['detail'] = f'已完成 {index + 1}/{len(record["plan"]["pages"])} 页'
            save(store, record)
            store.progress(record['detail'], {'visual_set_id': identity})
        check(store, record)
        from .visual_review import inspect, record_result, for_assets
        if (record.get('review') or {}).get('pass') is not True:
            record['detail'] = '正在检查整组视觉质量'
            save(store, record)
            cached = for_assets(store, [page['asset_id'] for page in record['pages']])
            record['review'] = cached if cached.get('pass') is True else inspect(store, record)
            record_result(store, record)
        check(store, record)
        record.update(state='completed', detail='组图已生成，请检查整组文字、插画与顺序；尚未发布', visual_review='checked' if record['review']['pass'] is True else 'human_required')
    except Exception as exc:
        logging.getLogger(__name__).exception('Visual production interrupted')
        record.update(state='needs_attention', detail=str(exc))
    save(store, record)
    return record
