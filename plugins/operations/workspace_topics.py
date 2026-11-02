"""Metadata-only renames and explicit source references within one business."""
import json


def rename_topic(directory, scope, name):
    store = directory.store(scope['business_id'], scope['id'])
    if store.scope['archived'] or store.scope['business_archived']:
        return  # Archive labels may change; their historical rule snapshots remain immutable.
    version, policy = store.policy()
    store.configure({**policy, 'topic': name}, version)


def rename_metadata(db, old, name):
    # Keep immutable rule snapshots; update only lookup labels in the same save transaction.
    for row in db.execute("SELECT id,kind,data FROM objects WHERE kind!='policy'").fetchall():
        data = json.loads(row['data'])
        if row['kind'] == 'source':
            data.setdefault('original_topic_label', old)
        replace_label(data, old, name)
        db.execute('UPDATE objects SET data=? WHERE id=?', (json.dumps(data, ensure_ascii=False), row['id']))
    for row in db.execute('SELECT id,data FROM business_datasets').fetchall():
        data = json.loads(row['data'])
        replace_label(data, old, name)
        db.execute('UPDATE business_datasets SET data=? WHERE id=?', (json.dumps(data, ensure_ascii=False), row['id']))


def replace_label(value, old, name):
    if isinstance(value, dict):
        if value.get('scope_topic') == old:
            value.setdefault('original_topic_label', old)
            value['scope_topic'] = name
        for child in value.values():
            replace_label(child, old, name)
    elif isinstance(value, list):
        for child in value:
            replace_label(child, old, name)


def reference_source(store, source_topic, identity):
    """Copy a source snapshot with lineage; business data/derived reports are excluded."""
    original = store.workspace.store(store.scope['business_id'], source_topic)
    rows = [r for r in original.objects('source') if r['id'] == identity]
    if not rows:
        raise ValueError('来源不存在于当前业务')
    source = rows[0]
    if source.get('visibility', 'public') != 'public':
        raise ValueError('仅可引用公开来源，内部业务数据不可转为公开资料')
    policy = store.policy()[1]
    copied = {**source, 'scope_topic': policy['topic'], 'origin': {'business_id': original.scope['business_id'], 'topic_id': source_topic, 'source_id': identity}}
    image_ids = {image['id'] for image in source.get('images', []) if image.get('id')}
    for image in original.objects('source_image'):
        if image['id'] in image_ids:
            store.put('source_image', {**image, 'origin': copied['origin']}, image['id'])
    key = 'reference:' + source_topic + ':' + identity
    store.put('source', copied, key)
    from .source_library import reuse
    reuse(store, key, {'version': store.policy()[0], 'enabled': True})
    return {'id': key}


def new_policy(directory, name, business, category, copy_topic):
    from copy import deepcopy
    from .policy import DEFAULT, validate_policy
    policy = deepcopy(DEFAULT)
    if business:
        parent = next((b for b in directory.catalog()['businesses'] if b['id'] == business and not b['archived']), None)
        if not parent:
            raise ValueError('业务不存在或已归档')
        category = parent['category']
    from .business_themes import BUSINESS_THEMES
    preset = next((item for item in BUSINESS_THEMES if item['id'] == category), None)
    if preset:
        policy.update(preset['defaults'])
    policy['business_theme'] = category
    if business and not copy_topic:
        restrict_defaults(directory, policy, business)
    if copy_topic:
        original = next((t for t in directory.catalog()['topics'] if t['id'] == copy_topic), None)
        if not original:
            raise ValueError('复制来源不存在')
        policy = directory.store(original['business_id'], original['id']).policy()[1]
        if original['business_id'] != business:
            policy.update(account_id='', knowledge=[], brand='')
        if business:
            policy.update(business_theme=category, business_subtype='')
        else:
            category = policy['business_theme']
    policy.update(topic=name, enabled=False, paused=False)
    policy = validate_policy(policy)
    return policy, category


def restrict_defaults(directory, policy, business):
    for existing in directory.catalog()['topics']:
        if existing['business_id'] == business and not existing['archived']:
            saved = directory.store(business, existing['id']).policy()[1]
            policy['allowed'] = {key: value and saved['allowed'][key] for key, value in policy['allowed'].items()}
            policy['limits'] = {key: min(value, saved['limits'][key]) for key, value in policy['limits'].items()}
            policy['model_calls'] = min(policy['model_calls'], saved['model_calls'])
