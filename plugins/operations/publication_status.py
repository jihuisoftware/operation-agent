"""Publication delivery, platform review and content verification are independent facts."""
import json

EXECUTION = {'not_submitted', 'submitted', 'verified', 'unknown'}
PLATFORM = {'unknown', 'reviewing', 'published', 'rejected'}
CONTENT = {'unknown', 'matched', 'mismatch', 'incomplete'}


def normalize(result, previous=None):
    value = {**(previous or {}), **result}
    if 'publication' not in value:
        return value  # Legacy receipts remain evidence of their original, narrower check.
    status = value['publication']
    if not isinstance(status, dict):
        raise ValueError('发布状态格式错误')
    for key, allowed in [('execution', EXECUTION), ('platform', PLATFORM), ('content', CONTENT)]:
        if status.get(key) not in allowed:
            raise ValueError('发布状态字段无效：' + key)
    success = status['execution'] == 'verified' and status['platform'] == 'published' and status['content'] == 'matched'
    if value.get('state') in {'published', 'submitted', 'unknown'}:
        value['state'] = 'published' if success and value.get('evidence') else (
            'submitted' if status['execution'] in {'submitted', 'verified'} else 'unknown')
    return value


def complete(action):
    result = action.get('result', {})
    result = json.loads(result) if isinstance(result, str) else result
    manual = result.get('manual_verification', {})
    if manual.get('state') == action['state'] and manual.get('evidence'):
        return action['state'] in {'published', 'confirmed'}
    normalized = normalize({**result, 'state': action['state']})
    return normalized['state'] in {'published', 'confirmed'}


def display(action):
    result = action.get('result', {})
    result = json.loads(result) if isinstance(result, str) else result
    return result.get('publication') or {
        'execution': 'verified' if action['state'] == 'published' else 'submitted' if action['state'] == 'submitted' else 'unknown',
        'platform': 'unknown', 'content': 'unknown', 'legacy': True,
    }
