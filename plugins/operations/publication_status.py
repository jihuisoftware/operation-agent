"""Publication delivery, platform review and content verification are independent facts."""
import json

EXECUTION = {'not_submitted', 'submitted', 'verified', 'unknown'}
PLATFORM = {'unknown', 'reviewing', 'published', 'rejected'}
CONTENT = {'unknown', 'matched', 'mismatch', 'incomplete'}


def summary(result):
    """Describe independent evidence without promoting a partial check to success."""
    status = result.get('publication', {})
    if not status:
        return '发布结果待核对；仅核对原动作，不重新发布'
    platform = {'published': '平台已发布', 'reviewing': '平台审核中', 'rejected': '平台审核未通过', 'unknown': '平台发布状态待确认'}
    content = {'matched': '内容核对一致', 'mismatch': '内容不一致，需人工核对', 'incomplete': '内容核对不完整，需继续核对', 'unknown': '内容尚未核对'}
    detail = platform.get(status.get('platform'), platform['unknown']) + '；' + content.get(status.get('content'), content['unknown'])
    if result.get('verification_stale'):
        detail += '（部分为历史核对结果，本次检查未完成）'
    return detail + '。仅核对原动作，不重新发布'


def normalize(result, previous=None):
    value = {**(previous or {}), **result}
    if 'publication' not in value:
        return value  # Non-publication commands have no publication fields.
    status = value['publication']
    if not isinstance(status, dict):
        raise ValueError('发布状态格式错误')
    for key, allowed in [('execution', EXECUTION), ('platform', PLATFORM), ('content', CONTENT)]:
        if status.get(key) not in allowed:
            raise ValueError('发布状态字段无效：' + key)
    success = (status['execution'] == 'verified' and status['platform'] == 'published' and status['content'] == 'matched'
               and not value.get('verification_stale'))
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
        'platform': 'unknown', 'content': 'unknown',
    }
