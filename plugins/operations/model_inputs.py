"""Bound model-facing projections while keeping complete persisted evidence and permission lineage."""
import json

MAX_INPUT_CHARS = 80_000


def fields(row, keys):
    return {key: row[key] for key in keys if key in row}


def pack(rows, count, characters):
    selected, used = [], 0
    for row in rows:
        size = len(json.dumps(row, ensure_ascii=False))
        if len(selected) < count and used + size <= characters:
            selected.append(row)
            used += size
    return selected


def history(rows):
    return [fields(row, ('id', 'title', 'body', 'day', 'source_ids', 'publication_state', 'publication_recorded_at')) for row in rows[:15]]


def policy(value):
    return fields(value, ('topic', 'goal', 'audience', 'style', 'brand'))


def assets(rows):
    return [fields(row, ('id', 'name', 'authorized', 'revoked', 'generated_typography', 'cover_title', 'cover_spec', 'generated_magazine', 'visual_page')) for row in rows]


def evidence(rows, required_ids=()):
    if not set(required_ids) <= {row['id'] for row in rows}:
        raise ValueError('选题引用资料已不在当前可用范围，请重新选题')
    keys = ('id', 'title', 'url', 'day', 'published_at', 'summary', 'category', 'facts', 'opinions', 'uncertainties', 'keywords', 'organization_id', 'text_truncated')
    projected = []
    for row in rows:
        item = fields(row, keys)
        item['images'] = [fields(image, ('url', 'state', 'authorized')) for image in (row.get('images') or [])[:3]]
        projected.append(item)
    projected.sort(key=lambda row: row['id'] not in required_ids)
    selected = pack(projected, 40, 30_000)
    if not set(required_ids) <= {row['id'] for row in selected}:
        raise ValueError('选题引用资料超过本轮输入容量，请缩小引用范围或重新选题')
    if not selected:
        raise ValueError('资料内容超过本轮输入容量，请先精简整理结果')
    return selected


def analysis(context, sources):
    if not context:
        return None
    metrics = pack([fields(row, ('id', 'dataset_id', 'key', 'name', 'value', 'unit', 'previous', 'growth_percent', 'samples', 'missing', 'definition', 'semantics'))
                    for row in context['metrics']], 20, 6000)
    known = {row['id'] for row in sources} | {row['id'] for row in metrics}
    rows = [fields(row, ('view', 'dimension', 'title', 'text', 'evidence_ids', 'scope', 'counter', 'unknowns', 'origin_window', 'analyzed_at', 'analysis_origin'))
            for row in context['findings'] if set(row['evidence_ids']) <= known]
    findings = pack(rows, 12, 12_000)
    return {**fields(context, ('window', 'pending')), 'findings': findings, 'metrics': metrics,
            'coverage': {'findings_total': len(context['findings']), 'findings_used': len(findings),
                         'metrics_total': len(context['metrics']), 'metrics_used': len(metrics)}}


def selected_topic(value):
    return fields(value, ('title', 'reason', 'source_ids', 'origin')) if value else None


def tasks(rows):
    return [fields(row, ('id', 'text', 'state')) for row in rows]


def checked(store, task, data):
    size = len(json.dumps(data, ensure_ascii=False))
    if size > MAX_INPUT_CHARS:
        raise ValueError('运营输入过长，请缩短品牌描述、临时任务或引用范围后重试')
    coverage = (data.get('analysis') or {}).get('coverage', {})
    store.event('model_input', {'task': task, 'characters': size, 'sources_used': len(data.get('sources', [])),
                               'history_used': len(data.get('recent_content', data.get('history', []))), **coverage})
    return data
