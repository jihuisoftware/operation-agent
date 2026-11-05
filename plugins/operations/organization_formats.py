"""Normalize unambiguous model shapes; reject bad rows without discarding good siblings."""
from collections import Counter
import json
import re


class OrganizationCapacityError(ValueError):
    """Model-produced summaries cannot be merged within the existing input budget."""


def text_value(value, *, keyword=False):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict) and not {'source_id', 'source_ids'} & value.keys():
        keys = ('text', 'keyword', 'name') if keyword else ('text',)
        texts = {value[key].strip() for key in keys if isinstance(value.get(key), str) and value[key].strip()}
        if len(texts) == 1:
            return texts.pop()
    return None


def texts(value, name):
    original = value
    dropped = False
    if isinstance(value, str) and value.strip().startswith(('[', '{')):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return [], True, True
    if value is None:
        value = []
    elif isinstance(value, str):
        value = re.split(r'[,，、;；\n]+', value) if name == 'keywords' else [value]
    elif isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return [], True, True
    cleaned = []
    for item in value:
        text = text_value(item, keyword=name == 'keywords')
        if text is None or len(text) > 800:
            dropped = True
        elif text and text not in cleaned:
            if len(cleaned) < 8:
                cleaned.append(text)
            else:
                dropped = True
    return cleaned, cleaned != original, dropped


def relevance(value):
    if type(value) is bool:
        return value
    if type(value) is int and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        return {'true': True, 'false': False, '1': True, '0': False,
                'yes': True, 'no': False, '是': True, '否': False}.get(value.strip().lower())
    return None


def normalize_row(row):
    from .organization import CATEGORIES
    category = row.get('category')
    category = category.strip() if isinstance(category, str) else None
    relevant = relevance(row.get('relevant'))
    summary = text_value(row.get('summary'))
    if category not in CATEGORIES or relevant is None:
        raise ValueError('分类或相关性无法识别')
    if not summary or len(summary) > 1500:
        raise ValueError('摘要为空、过长或无法识别')
    result = {'source_id': row['source_id'], 'category': category, 'relevant': relevant, 'summary': summary}
    warnings, dropped_fields = [], []
    for name in ('facts', 'opinions', 'uncertainties', 'keywords'):
        result[name], changed, dropped = texts(row.get(name, []), name)
        if changed:
            warnings.append(f'{name}：' + ('已跳过无法使用或超出容量的元素' if dropped else '已兼容为文本列表'))
        if dropped:
            dropped_fields.append(name)
    if dropped_fields:
        result['uncertainties'].append('部分整理字段（' + '、'.join(dropped_fields) + '）无法完整识别；不能据此断言原文没有相关内容。')
    if warnings:
        result.update(format_warnings=warnings, format_incomplete=bool(dropped_fields))
    return result


def response_rows(result):
    value = result.get('items') if isinstance(result, dict) else None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if isinstance(value, dict) and 'source_id' in value:
        return [value]
    return value if isinstance(value, list) else []


def normalize(result, sources):
    rows = response_rows(result)
    known = {source['id'] for source in sources}
    counts = Counter(row['source_id'] for row in rows if isinstance(row, dict) and isinstance(row.get('source_id'), str))
    cleaned, issues = [], []
    if not rows:
        issues.append({'reason': '未返回有效items条目', 'action': 'skipped'})
    for index, row in enumerate(rows):
        identity = row.get('source_id') if isinstance(row, dict) else None
        issue = {'index': index, 'source_id': identity if isinstance(identity, str) and identity in known else None}
        if not isinstance(identity, str) or identity not in known or counts[identity] > 1:
            issues.append({**issue, 'reason': '来源未知、缺失或重复', 'action': 'skipped'})
            continue
        try:
            value = normalize_row(row)
        except ValueError as exc:
            issues.append({**issue, 'reason': str(exc), 'action': 'skipped'})
            continue
        cleaned.append(value)
        if value.get('format_warnings'):
            issues.append({**issue, 'reason': '；'.join(value['format_warnings']), 'action': 'normalized'})
    return cleaned, issues


def request_rows(store, policy, day, instruction, data, sources, *, phase, retry=False):
    from .organization import generate
    from .model_errors import ModelOutputError
    try:
        result = generate(store, policy, day, instruction, data)
    except ModelOutputError as exc:
        store.event('organization_format', {'day': day, 'phase': phase, 'retry': retry,
                    'requested': [source['id'] for source in sources], 'issue_count': 1,
                    'issues': [{'action': 'skipped', 'reason': str(exc)}]})
        return []
    rows, issues = normalize(result, sources)
    if issues:
        store.event('organization_format', {'day': day, 'phase': phase, 'retry': retry,
                    'requested': [source['id'] for source in sources], 'issue_count': len(issues), 'issues': issues[:30]})
    return rows
