"""Actual visual inspection, separate from factual review of the page copy."""
import base64
import logging
from io import BytesIO

from PIL import Image


def inspect(store, record):
    from .visual_sets import asset_bytes
    from .model import generate
    from .policy import local_day
    sheet = Image.new('RGB', (1080, 720 * ((len(record['pages']) + 1) // 2)), 'white')
    for index, page in enumerate(record['pages']):
        with Image.open(BytesIO(asset_bytes(store, page['asset_id']))) as image:
            image.thumbnail((540, 720))
            sheet.paste(image, ((index % 2) * 540, (index // 2) * 720))
    output = BytesIO()
    sheet.save(output, format='JPEG', quality=88)
    uri = 'data:image/jpeg;base64,' + base64.b64encode(output.getvalue()).decode()
    _, policy = store.policy()
    from .review_scores import instruction
    try:
        result = generate(store, policy, local_day(policy),
            '检查实际组图的视觉质量。目标为清爽杂志与信息图：封面缩略图主题清楚，中文无裁切遮挡，层次清晰，'
            '各页有明确重点和统一风格，插画与主题相关且没有伪造文字、界面或水印；避免大面积无意义空白与拥挤小字。'
            '必须根据图片判断，不仅根据文案。返回 {"pass":true或false,"reason":"说明","issues":["页码与问题"]}。'
            '有明显问题则不通过；这不是人工审核，也不验证事实来源。' + instruction('visual'),
            {'pages': record['plan']['pages'], 'reading_order': '从左到右，从上到下'},
            image_parts=[{'type': 'image_url', 'image_url': {'url': uri}}], manual=getattr(store, 'visual_manual', False))
        if type(result.get('pass')) is not bool or not isinstance(result.get('issues', []), list):
            raise ValueError('视觉检查未返回明确结论')
        if result.get('issues'):
            result['pass'] = False
        return result
    except Exception as exc:
        logging.getLogger(__name__).exception('Visual production interrupted')
        return {'pass': None, 'reason': '视觉检查不可用，需要人工核对：' + str(exc), 'issues': []}


def signature(ids):
    import hashlib
    from .store import encoded
    return hashlib.sha256(encoded(['magazine-review-scores-v1', ids]).encode()).hexdigest()


def record_result(store, record):
    from .policy import now_iso
    store.put('visual_review', {'signature': signature([page['asset_id'] for page in record['pages']]),
              'result': record['review'], 'at': now_iso(), 'visual_set_id': record['id']})


def for_assets(store, ids):
    import json
    with store.connection() as db:
        row = db.execute("SELECT data FROM objects WHERE kind='visual_review' AND json_extract(data,'$.signature')=? ORDER BY created DESC,id DESC LIMIT 1", (signature(ids),)).fetchone()
    return json.loads(row[0])['result'] if row else {'pass': None, 'reason': '当前图片组合尚未完成视觉检查', 'issues': []}


def for_content(store, content):
    import hashlib
    from .content_release import fingerprint
    from .store import encoded
    from .review_policy import get
    from .review_scores import score, VERSION
    version, _ = store.policy()
    key = hashlib.sha256(encoded([fingerprint(content), version, VERSION]).encode()).hexdigest()
    require_score = get(store)['mode'] == 'score'
    def usable(value):
        return type(value.get('pass')) is bool and (not require_score or score(value, 'visual') is not None)
    cached = next((r['result'] for r in store.objects('automatic_visual_review') if r['signature'] == key), {})
    if usable(cached):
        return cached
    record = matching_visual_set(store, content, version)
    if record and usable(record.get('review') or {}):
        result = record['review']
    else:
        record = {'pages': [{'asset_id': identity} for identity in content['asset_ids']],
                  'plan': {'pages': [{'title': content['title'], 'body': content['body']}]}}
        result = inspect(store, record)
    store.put('automatic_visual_review', {'signature': key, 'result': result})
    return result


def matching_visual_set(store, content, version):
    import json
    from .visual_plan import signature as content_signature
    with store.connection() as db:
        row = db.execute("SELECT data FROM objects WHERE kind='visual_set' AND id=?", (content.get('visual_set_id'),)).fetchone()
    record = json.loads(row[0]) if row else {}
    if (record.get('state') == 'completed' and record.get('policy_version') == version
            and record.get('input_signature') == content_signature(content)
            and [page.get('asset_id') for page in record.get('pages', [])] == content['asset_ids']):
        return record
    return None
