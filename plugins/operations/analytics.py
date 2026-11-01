"""Persistent analytical snapshots and verifiable input lineage."""
import json

from .analysis_config import settings, window
from .analysis_data import sources_summary, business_summary, operational_metrics
from .business_store import datasets
from .policy import now_iso


def valid(store, report, policy, day):
    config = settings(store)
    if report['scope_topic'] != policy['topic'] or report['config_version'] != config['version'] or report['window'] != window(config['config'], day):
        return False
    active = {d['id']: d for d in datasets(store) if d['active'] and d['scope_topic'] == policy['topic']}
    expected = {d['id']: d['version'] for d in report['datasets']}
    return expected == {key: d['version'] for key, d in active.items()}


def analyze(store, policy, day, version):
    from .analysis_runs import guard
    guard(store, policy)
    config = settings(store)
    period = window(config['config'], day)
    store.progress('正在计算完整范围的来源与业务指标', period)
    sources, evidence = sources_summary(store, policy, period)
    metrics, batches, _ = business_summary(store, policy, period)
    report = {'day': day, 'scope_topic': policy['topic'], 'version': version, 'config_version': config['version'],
              'window': period, 'created': now_iso(), 'sources': sources, 'metrics': metrics,
              'operational_metrics': operational_metrics(store, period), 'datasets': batches,
              'evidence': evidence, 'model_calls': 0, 'state': 'completed',
              'detail': f"已统计 {sources['counts'].get('read', 0)} 条去重资料、{len(metrics)} 项业务指标；样本不代表行业规模"}
    if store.policy() != (version, policy) or not valid(store, report, policy, day):
        raise ValueError('分析期间配置或数据发生变化，请重新执行')
    guard(store, policy)
    identity = store.put('analytics_report', report)
    return {'report_id': identity, 'state': report['state'], 'detail': report['detail']}


def latest(store, kind, policy, day):
    config = settings(store)
    period = window(config['config'], day)
    with store.connection() as db:
        rows = db.execute("SELECT id,data FROM objects WHERE kind=? AND json_extract(data,'$.scope_topic')=? "
                          "AND json_extract(data,'$.config_version')=? AND json_extract(data,'$.window.start')=? "
                          "AND json_extract(data,'$.window.end')=? ORDER BY created DESC",
                          (kind, policy['topic'], config['version'], period['start'], period['end']))
        for row in rows:
            report = {**json.loads(row['data']), 'id': row['id']}
            if valid(store, report, policy, day):
                return report
    return None
