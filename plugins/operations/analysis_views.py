"""Small report catalogs, owner-local details and explicit internal/public exports."""
import csv
from io import StringIO
import json

from .analysis_config import settings
from .analytics import valid
from .business_store import datasets
from .business_validation import TEMPLATES, FIELDS
from .policy import local_day


def catalog(store):
    version, policy = store.policy()
    with store.connection() as db:
        rows = db.execute("SELECT id,kind,json_extract(data,'$.created') AS created,json_extract(data,'$.detail') AS detail, "
                          "json_extract(data,'$.state') AS state,json_extract(data,'$.window') AS window "
                          "FROM objects WHERE kind IN ('analytics_report','industry_report') AND json_extract(data,'$.scope_topic')=? "
                          "ORDER BY created DESC LIMIT 60", (policy['topic'],)).fetchall()
        runs = [dict(r) for r in db.execute("SELECT * FROM runs WHERE stage IN ('analytics','industry') ORDER BY started DESC LIMIT 30")]
        batches = [json.loads(r[0]) for r in db.execute('SELECT data FROM business_batches ORDER BY rowid DESC LIMIT 30')]
    return {'version': version, 'policy': policy, 'settings': settings(store), 'datasets': datasets(store), 'batches': batches,
            'reports': [{**dict(r), 'window': json.loads(r['window'])} for r in rows], 'runs': runs,
            'templates': {k: {**v, 'fields': {**FIELDS, **v['metrics']}} for k, v in TEMPLATES.items()}}


def detail(store, identity):
    with store.connection() as db:
        row = db.execute("SELECT data,kind FROM objects WHERE id=? AND kind IN ('analytics_report','industry_report')", (identity,)).fetchone()
    if not row:
        raise ValueError('分析报告不存在')
    report = {**json.loads(row['data']), 'id': identity, 'kind': row['kind']}
    _, policy = store.policy()
    referenced = {identity for f in report.get('findings', []) for identity in f['evidence_ids']}
    report['evidence'] = [e for e in report.get('evidence', []) if e['id'] in referenced]
    report['current'] = valid(store, report, policy, local_day(policy))
    return report


def export(store, identity, format, public=False):
    report = detail(store, identity)
    if public and not report['current']:
        raise ValueError('历史报告的范围或数据权限已变化，不能导出为公开材料')
    metrics = report.get('metrics', [])
    findings = report.get('findings', [])
    if public:
        metrics = [m for m in metrics if m['visibility'] == 'public']
        findings = [f for f in findings if f['visibility'] == 'public']
    if format == 'csv':
        stream = StringIO()
        writer = csv.writer(stream)
        writer.writerow(['指标', '数值', '单位', '口径', '日期', '范围'])
        for metric in metrics:
            for day, value in (metric.get('trend') or {report['window']['end']: metric.get('value')}).items():
                cells = [metric['name'], value, metric['unit'], metric['definition'], day, metric['visibility']]
                writer.writerow(["'" + str(c) if str(c).startswith(('=', '+', '-', '@')) else c for c in cells])
        for day, value in report.get('sources', {}).get('trend', {}).items():
            writer.writerow(['采集样本', value, '条', '去重来源数量，不代表市场规模', day, 'public'])
        return {'content': stream.getvalue(), 'name': identity + '.csv', 'mime': 'text/csv;charset=utf-8'}
    if format != 'markdown':
        raise ValueError('仅支持 Markdown 和 CSV')
    lines = ['# ' + ('数据分析' if report['kind'] == 'analytics_report' else '行业分析'),
             '用途：' + ('可公开材料' if public else '内部报告'), report['scope_topic'], str(report['window']), report['detail']]
    lines.extend(f"- {m['name']}：{m['value']} {m['unit']}；口径：{m['definition']}；{m['visibility']}" for m in metrics)
    for finding in findings:
        lines.extend([f"## {finding['title']} · {finding['visibility']}", finding['text'], '适用范围：' + finding['scope'],
                      '反向证据：' + finding['counter'], '待核实：' + finding['unknowns'], '证据：' + ', '.join(finding['evidence_ids'])])
    public_ids = {i for f in findings for i in f['evidence_ids']}
    lines.extend(f"- {e.get('title', e['id'])} {e.get('url', '')}" for e in report.get('evidence', []) if not public or e['id'] in public_ids)
    return {'content': '\n\n'.join(lines), 'name': identity + '.md', 'mime': 'text/markdown;charset=utf-8'}


def daily_lines(store, day):
    lines = ['', '## 数据与行业分析', '']
    for kind in ('analytics_report', 'industry_report'):
        for report in store.objects(kind, day):
            lines.append(f"- {report['id']}：{report['detail']}；范围 {report['window']['start']}～{report['window']['end']}；模型调用 {report['model_calls']} 次")
    with store.connection() as db:
        events = db.execute("SELECT kind,data FROM events WHERE kind IN ('analysis_fallback','business_import') AND json_extract(data,'$.day')=?", (day,))
        for event in events:
            value = json.loads(event['data'])
            lines.append('- ' + (value['reason'] if event['kind'] == 'analysis_fallback' else f"业务导入：有效 {value['inserted']}，重复 {value['duplicates']}，无效 {value['invalid']}"))
    return lines
