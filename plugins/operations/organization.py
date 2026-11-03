"""Incremental, source-bound classification; original documents remain canonical."""
import hashlib
from collections import deque

from .model import generate
from .model_budget import remaining_calls
from .outcomes import StageSkipped
from .policy import now_iso
from .source_library import available_sources
from .store import encoded

BATCH_SIZE = 4
CATEGORIES = ('方法教程', '案例经验', '行业动态', '数据研究', '用户需求', '产品资料', '其他')


def material_id(policy, source):
    evidence = [source.get('original_topic_label', policy['topic']), source['id'], source['text'], source.get('url'), source.get('title'), source.get('published_at')]
    return 'organized:' + hashlib.sha256(encoded(evidence).encode()).hexdigest()


def materials(store, policy, day, *, include_history=False):
    sources = available_sources(store, policy, day, include_history=include_history)
    cached = {r['id']: r for r in store.objects('organized_source') if r['scope_topic'] == policy['topic']}
    return [(s, cached.get(material_id(policy, s))) for s in sources]


def _texts(value, name):
    if not isinstance(value, list) or len(value) > 8 or any(not isinstance(s, str) or len(s) > 800 for s in value):
        raise ValueError(f'整理结果 {name} 格式错误')
    return [s.strip() for s in value if s.strip()]


def validate(result, sources):
    rows = result.get('items')
    if not isinstance(rows, list):
        raise ValueError('整理结果缺少有效的 items 列表')
    known, seen, cleaned = {s['id'] for s in sources}, set(), []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('source_id'), str) or row['source_id'] not in known or row['source_id'] in seen:
            raise ValueError('整理结果引用未知或重复来源')
        seen.add(row['source_id'])
        if row.get('category') not in CATEGORIES or type(row.get('relevant')) is not bool:
            raise ValueError('整理分类或相关性格式错误')
        if not isinstance(row.get('summary'), str) or not 1 <= len(row['summary'].strip()) <= 1500:
            raise ValueError('整理摘要为空或过长')
        cleaned.append({**{k: row[k] for k in ('source_id', 'category', 'relevant', 'summary')},
                        **{k: _texts(row.get(k, []), k) for k in ('facts', 'opinions', 'uncertainties', 'keywords')}})
    return cleaned


def _batch(store, policy, day, version, sources, *, retry=False):
    result = generate(store, policy, day,
        '逐条整理并归类资料，不生成选题或文章。每个 source_id 必须且仅返回一条。'
        '将 sources 中每条的 id 原样复制到 source_id，必须覆盖 expected_source_ids；不要合并多条来源。'
        '返回 {"items":[{"source_id":"","category":"分类","relevant":true,"summary":"摘要",'
        '"facts":["原文事实陈述"],"opinions":["作者观点"],"uncertainties":["待核实或适用限制"],"keywords":["关键词"]}]}。'
        '只使用提供的正文；事实陈述不等于已独立核实。事实、观点不得混用，资料不足必须写明。'
        '每类提取最多3条、每条不超过60字，摘要不超过120字；无关资料标记 relevant=false。图片没有进行视觉分析。',
        {'task': 'organize_sources', 'topic': policy['topic'], 'categories': CATEGORIES,
         'expected_source_ids': [s['id'] for s in sources],
         'sources': [{k: s.get(k) for k in ('id', 'title', 'url', 'published_at')} | {'text': s['text'][:6000]} for s in sources]})
    requested = [s['id'] for s in sources]
    try:
        rows = validate(result, sources)
    except ValueError as exc:
        store.event('organization_validation_error', {'day': day, 'requested': requested,
                    'result_keys': list(result)[:20], 'error': str(exc), 'retry': retry})
        if isinstance(result.get('items'), list):
            raise
        # A missing list contains no usable results; try each requested source once.
        # Invalid references inside an actual list still reject the batch above.
        rows = []
    by_id = {s['id']: s for s in sources}
    if store.policy() != (version, policy):
        raise ValueError('整理期间规则已变更，未保存本批结果')
    for row in rows:
        source = by_id[row['source_id']]
        identity = material_id(policy, source)
        store.put('organized_source', {**row, 'day': day, 'scope_topic': policy['topic'], 'version': version,
                  'created': now_iso(), 'source_signature': identity, 'text_truncated': len(source['text']) > 6000}, identity)
    returned = {row['source_id'] for row in rows}
    missing = [source for source in sources if source['id'] not in returned]
    store.event('organization_batch', {'day': day, 'requested': requested, 'returned': len(rows),
                'missing': [source['id'] for source in missing], 'retry': retry})
    return missing


def _run_batches(store, policy, day, version, pairs, pending, budget):
    queue = deque((pending[start:start + BATCH_SIZE], False) for start in range(0, len(pending), BATCH_SIZE))
    added, calls = 0, 0
    while queue and calls < budget:
        batch, retry = queue.popleft()
        store.progress('正在补试缺失来源' if retry else '正在整理来源',
                       {'completed': len(pairs) - len(pending) + added, 'total': len(pairs), 'batch_size': len(batch)})
        missing = _batch(store, policy, day, version, batch, retry=retry)
        calls += 1
        added += len(batch) - len(missing)
        if not retry:
            for source in reversed(missing):
                queue.appendleft(([source], True))
    return added, bool(queue)


def organize(store, policy, day, version):
    pairs = materials(store, policy, day, include_history=True)
    if not pairs:
        raise StageSkipped('没有可整理的来源，请先执行信息采集或选择历史素材')
    pending = [s for s, row in pairs if row is None]
    # Leave the configured downstream modules a chance to consume the partial collection.
    reserved = sum(cost for stage, cost in (('industry', 2), ('topics', 1), ('content', 2), ('publish', 1)) if policy['modules'][stage])
    batches = max(0, remaining_calls(store, policy, day) - reserved)
    added, budget_exhausted = _run_batches(store, policy, day, version, pairs, pending, batches)
    current = materials(store, policy, day, include_history=True)
    result = {'total': len(current), 'added': added, 'organized': sum(row is not None for _, row in current),
              'usable': sum(bool(row and row['relevant']) for _, row in current), 'pending': sum(row is None for _, row in current)}
    remaining = ('本轮模型额度已用完或已为后续步骤预留，下次从未整理资料继续。' if budget_exhausted
                 else '部分来源仍未返回有效整理结果，单条补试已结束；有效结果已保存，剩余来源下次继续。')
    result['detail'] = (f"新增整理 {added} 条；已整理 {result['organized']}/{result['total']} 条，相关资料 {result['usable']} 条，"
                        f"待整理 {result['pending']} 条。" + (remaining if result['pending'] else ''))
    store.put('organization', {**result, 'day': day, 'scope_topic': policy['topic'], 'version': version, 'created': now_iso(),
                               **({'debug_id': store.debug_id} if getattr(store, 'debug_id', None) else {})})
    return result


def production_evidence(store, policy, day, preferred_ids=()):
    pairs = [(source, row) for source, row in materials(store, policy, day) if row and row['relevant']]
    pairs.extend(_analysis_history(store, policy, preferred_ids, {s['id'] for s, _ in pairs}))
    selected = sorted(pairs, key=lambda pair: pair[0]['id'] not in preferred_ids)[:40]
    if not selected:
        raise StageSkipped('没有当前主题可用的整理资料，请先执行“资料整理与归类”；不会直接用未整理原文生产')
    sources, evidence = [], []
    for source, row in selected:
        sources.append(source)
        evidence.append({**{k: source.get(k) for k in ('id', 'title', 'url', 'day', 'published_at', 'collected_at', 'images')},
                         **{k: row[k] for k in ('summary', 'category', 'facts', 'opinions', 'uncertainties', 'keywords')},
                         'organization_id': row['id'], 'text_truncated': row['text_truncated']})
    return sources, evidence


def _analysis_history(store, policy, preferred_ids, existing):
    # An analysis explicitly scopes historical evidence; it need not be manually pinned again.
    if not preferred_ids:
        return []
    cached = {r['id']: r for r in store.objects('organized_source') if r['scope_topic'] == policy['topic']}
    pairs = []
    for source in store.objects('source'):
        if source['id'] not in preferred_ids or source['id'] in existing or source.get('scope_topic') != policy['topic'] or not source.get('text'):
            continue
        row = cached.get(material_id(policy, source))
        if row and row['relevant']:
            pairs.append((source, row))
    return pairs
