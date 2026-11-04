"""Readable report projection; full immutable evidence is loaded only on request."""
from collections import Counter
import json

from .model_budget_ledger import known_tokens
from .manual import LABELS


def _budget_receipts(scope, identities):
    from .model_budget_ledger import prefix, topic_id
    with scope.store.connection() as db:
        rows = db.execute(f"SELECT id,state,tokens FROM {prefix(scope.store)}model_budget_usage "
                          "WHERE topic_id=? AND id IN (SELECT value FROM json_each(?))",
                          (topic_id(scope.store), json.dumps(list(identities)))).fetchall()
    return {row['id']: row for row in rows}


def _group(groups, stage):
    return groups.setdefault(stage, {'calls': 0, 'receipts': 0, 'tokens': 0, 'unknown': 0})


def consumption(scope):
    stages = {row['id']: row['stage'] for row in scope.runs}
    groups, budgets = {}, {}
    for event in scope.events:
        if event['kind'] not in {'model_call', 'usage'}:
            continue
        data = json.loads(event['data'])
        stage = stages.get(data.get('run_id'), '其他')
        if data.get('budget_id'):
            item = budgets.setdefault(data['budget_id'], {'stage': stage, 'usage': None})
            if event['kind'] == 'usage':
                item['usage'] = data.get('tokens')
            continue
        group = _group(groups, stage)
        if event['kind'] == 'model_call':
            group['calls'] += 1
            continue
        group['receipts'] += 1
        tokens = known_tokens(data.get('tokens'))
        group['unknown'] += int(tokens is None)
        group['tokens'] += tokens or 0
    receipts = _budget_receipts(scope, budgets)
    for identity, data in budgets.items():
        group = _group(groups, data['stage'])
        receipt = receipts.get(identity)
        tokens = receipt['tokens'] if receipt is not None else known_tokens(data['usage'])
        unknown = receipt['state'] != 'confirmed' if receipt is not None else tokens is None
        group['calls'] += 1
        group['receipts'] += 1
        group['tokens'] += tokens or 0
        group['unknown'] += int(unknown)
    rows = []
    for stage, group in groups.items():
        missing = group['unknown'] + max(0, group['calls'] - group['receipts'])
        rows.append(f"- {LABELS.get(stage, stage)}：调用 {max(group['calls'], group['receipts'])} 次，已知 Token {group['tokens']:,}" +
                    (f"，另有 {missing} 次用量待核对" if missing else ''))
    total = sum(row['tokens'] for row in groups.values())
    return [f'已知 Token 合计：{total:,}；缺失回执不按零用量处理。', *rows]


def findings(scope):
    reports = scope.objects('industry_report')
    rows = [row for report in reports for row in report.get('findings', [])]
    if not rows:
        rows = [row for brief in scope.objects('brief') for row in (brief.get('result', {}).get('analysis_context') or {}).get('findings', [])]
    lines = []
    for row in rows[:5]:
        historical = row.get('origin_window') if row.get('analysis_origin') == 'historical' else None
        origin = f"（复用 {historical['start']}～{historical['end']} 的分析）" if historical else ''
        lines.append(f"- {str(row.get('title', '结论'))[:120]}{origin}：{str(row.get('text', ''))[:350]}")
        if row.get('scope') or row.get('unknowns'):
            lines.append(f"  范围：{str(row.get('scope', '未提供'))[:120]}；待核实：{str(row.get('unknowns', '未提供'))[:160]}")
    if len(rows) > 5:
        lines.append(f'其余 {len(rows) - 5} 条结论与完整依据请查看详细记录。')
    return lines


def summarize(scope, markdown, *, execution=None):
    from .report_execution import snapshot
    execution = execution if execution is not None else snapshot(scope)
    output, counts = [], Counter()
    section = ''
    omitted = False
    for line in markdown.splitlines():
        if line.startswith('## '):
            section = line
        if section == '## 暂停依据与登录观察':
            continue
        if line.startswith('{') or line.startswith('- 模型用量回执：') or line.startswith('- 已知单次费用：'):
            continue
        if line.startswith('结论与待核实信息'):
            output.extend(['## 主要结论', '', *findings(scope), ''])
            continue
        if line.startswith('- '):
            counts[section] += 1
            if counts[section] > 12:
                omitted = True
                continue
        output.append(line[:600])
    lines = ['## Token 用量', '', *consumption(scope), '']
    location = next((i for i, value in enumerate(output) if value == '## 异常与明日建议'), len(output))
    output[location:location] = lines
    blockers = [row for row in execution['runs'] if row['state'] in {'failed', 'paused', 'interrupted', 'needs_attention'}
                and not row.get('historical_pause')]
    blocker_lines = (['', '## 当前阻塞', *[f"- {row.get('title', LABELS.get(row['stage'], row['stage']))}：{row['detail'][:350]}"
                                       for row in blockers[:12]]] if blockers else [])
    # Reserve space for every selected business step, even when evidence lists are large.
    budget = max(3000, 11000 - sum(len(line) + 1 for line in blocker_lines))
    compact, size = [], 0
    for line in output:
        if size + len(line) > budget:
            omitted = True
            break
        compact.append(line)
        size += len(line) + 1
    compact.extend(blocker_lines)
    if omitted:
        compact.append('\n更多来源、任务和原始回执见完整详情。')
    return '\n'.join(compact) + '\n'
