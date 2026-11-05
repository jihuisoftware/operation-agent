"""Checkpoint complete long-document coverage before exposing one source-level summary."""
import hashlib
import re

from .collection_ledger import load
from .policy import now_iso
from .store import encoded

MAX_INPUT = 24_000
SEGMENT_SIZE = 6_000
PROTOCOL = 2


def source_input(source):
    return {'id': source['id'], 'title': str(source.get('title') or '')[:400], 'url': str(source.get('url') or '')[:1000],
            'published_at': source.get('published_at'), 'text': source['text'],
            'text_truncated': bool(source.get('truncated')), 'original_chars': source.get('original_chars', len(source['text']))}


def request_data(policy, sources, *, task='organize_sources'):
    from .organization import CATEGORIES
    return {'task': task, 'topic': policy['topic'], 'categories': CATEGORIES,
            'expected_source_ids': [source['id'] for source in sources], 'sources': [source_input(source) for source in sources]}


def fits(policy, sources):
    return len(encoded(request_data(policy, sources))) <= MAX_INPUT


def batches(policy, sources):
    group = []
    for source in sources:
        if group and (len(group) == 4 or not fits(policy, [*group, source])):
            yield group
            group = []
        group.append(source)
    if group:
        yield group


def segments(source):
    blocks, current = [], ''
    for block in re.split(r'(?=^#{1,6} )|\n\n', source['text'], flags=re.MULTILINE):
        if not block:
            continue
        if current and len(current) + len(block) + 2 > SEGMENT_SIZE:
            blocks.append(current)
            current = ''
        while len(block) > SEGMENT_SIZE:
            blocks.append(block[:SEGMENT_SIZE])
            block = block[SEGMENT_SIZE:]
        current = current + '\n\n' + block if current else block
    if current:
        blocks.append(current)
    signature = hashlib.sha256(encoded([PROTOCOL, source['id'], source['text']]).encode()).hexdigest()
    return [{**source, 'id': f"{source['id']}:part:{signature}:{index}", 'text': block,
             'truncated': False, 'original_chars': len(block)} for index, block in enumerate(blocks)]


def checkpoint_id(policy, item):
    return 'organization-part:' + hashlib.sha256(encoded([PROTOCOL, policy['topic'], item['id'], item['text']]).encode()).hexdigest()


def organize_long(store, policy, day, version, source, budget):
    from .organization import save_rows, INSTRUCTION
    from .organization_formats import request_rows
    pieces = segments(source)
    complete = {piece['id']: load(store, checkpoint_id(policy, piece)) for piece in pieces}
    calls = 0
    for group in batches(policy, [piece for piece in pieces if not complete[piece['id']]]):
        if calls >= budget:
            return False, calls
        calls += 1
        rows = request_rows(store, policy, day, INSTRUCTION + '每条是长文的一段；只整理该段，不把其他段未出现的内容断言为原文缺失。', request_data(policy, group), group, phase='segments')
        if store.policy() != (version, policy):
            raise ValueError('整理期间规则已变更，未保存本批结果')
        for row in rows:
            piece = next(item for item in group if item['id'] == row['source_id'])
            identity = checkpoint_id(policy, piece)
            store.put('organization_part', {**row, 'day': day, 'source_id': source['id'], 'segment_id': piece['id'],
                                            'created': now_iso()}, identity)
            complete[piece['id']] = row
    if not all(complete.values()) or calls >= budget:
        return False, calls
    summaries = [complete[piece['id']] for piece in pieces]
    merged, used = merge_summaries(store, policy, day, version, source, summaries, budget - calls)
    if merged:
        if any(row.get('format_incomplete') for row in summaries):
            merged.update(format_incomplete=True, format_warnings=['部分分段存在无法兼容的字段'])
            merged['uncertainties'].append('部分分段整理字段未完整识别，不能据此断言原文未提及相关内容。')
        save_rows(store, policy, day, version, [source], [{**merged, 'source_id': source['id']}], segments_total=len(pieces))
    return bool(merged), calls + used


def summary_source(source, rows):
    return {**source, 'text': encoded([{'part': index + 1, **{key: row[key] for key in ('summary', 'facts', 'opinions', 'uncertainties')}}
                                     for index, row in enumerate(rows)]), 'truncated': False}


def merge_groups(policy, source, rows):
    from .organization_formats import OrganizationCapacityError
    groups, current = [], []
    for row in rows:
        if current and not fits(policy, [summary_source(source, [*current, row])]):
            groups.append(current)
            current = []
        current.append(row)
        if not fits(policy, [summary_source(source, current)]):
            raise OrganizationCapacityError('单段摘要超过整理容量，原文和检查点已保存')
    if current:
        groups.append(current)
    return groups


def merge_summaries(store, policy, day, version, source, rows, budget):
    from .organization import INSTRUCTION, material_id
    from .organization_formats import request_rows, OrganizationCapacityError
    calls = 0
    incomplete = any(row.get('format_incomplete') for row in rows)
    while rows:
        try:
            groups = merge_groups(policy, source, rows)
            if len(rows) > 1 and len(groups) == len(rows):
                raise OrganizationCapacityError('长文分段摘要无法在单次容量内合并，检查点已保存')
        except OrganizationCapacityError as exc:
            store.event('organization_format', {'day': day, 'phase': 'merge', 'requested': [source['id']],
                        'issue_count': 1, 'issues': [{'action': 'skipped', 'reason': str(exc)}]})
            return None, calls
        reduced = []
        for group in groups:
            data = request_data(policy, [summary_source(source, group)], task='organize_merge')
            identity = 'organization-merge:' + hashlib.sha256(encoded([material_id(policy, source), data]).encode()).hexdigest()
            cached = load(store, identity)
            if cached:
                reduced.append(cached)
                continue
            if calls >= budget:
                return None, calls
            calls += 1
            values = request_rows(store, policy, day, INSTRUCTION + 'sources.text 是同一文档连续分段的摘要。合并全部提供段落，保留后半部分的重要事实；未提及不能当作原文缺失。', data, [source], phase='merge')
            if not values:
                return None, calls
            if store.policy() != (version, policy):
                raise ValueError('整理期间规则已变更，未保存合并结果')
            cached = values[0]
            store.put('organization_merge', {**cached, 'day': day, 'created': now_iso()}, identity)
            reduced.append(cached)
        if len(reduced) == 1:
            if incomplete:
                reduced[0] = {**reduced[0], 'format_incomplete': True, 'format_warnings': ['部分分段或中间摘要存在无法兼容的字段'],
                              'uncertainties': [*reduced[0]['uncertainties'], '部分分段或中间摘要的字段未完整识别，不能据此断言原文未提及相关内容。']}
            return reduced[0], calls
        incomplete = incomplete or any(row.get('format_incomplete') for row in reduced)
        rows = reduced
    return None, calls
