"""Read captured continuation inputs without replacing them with unrelated newer artifacts."""
import json

from .store import encoded


def captured(store, key):
    return key in (getattr(store, 'resume_artifacts', None) or {})


def record(store, key, kind):
    identity = store.resume_artifacts[key]
    if identity is None:
        return None
    with store.connection() as db:
        row = db.execute('SELECT id,data FROM objects WHERE kind=? AND id=?', (kind, identity)).fetchone()
    if not row:
        raise ValueError('原批次的冻结产物不存在，请发起新批次；不会替换为最新结果')
    return {**json.loads(row['data']), 'id': row['id']}


def _sources(store, policy, expected):
    if not expected:
        return
    from .organization import material_id
    with store.connection() as db:
        for identity, signatures in expected.items():
            row = db.execute("SELECT data FROM objects WHERE kind='source' AND id=?", (identity,)).fetchone()
            source = {**json.loads(row[0]), 'id': identity} if row else None
            if not source or material_id(policy, source) not in signatures:
                raise ValueError('原批次的来源或整理依据已变化，请发起新批次')


def analysis(store, kind, policy, day):
    from .analytics import latest, valid
    key = 'analytics_report_id' if kind == 'analytics_report' else 'industry_report_id'
    if not captured(store, key):
        return latest(store, kind, policy, day)
    value = record(store, key, kind)
    if value is None:
        return None
    if not valid(store, value, policy, day) or value.get('version') != store.policy()[0]:
        raise ValueError('原批次的分析权限、规则或范围已变化，请发起新批次')
    _sources(store, policy, {row['id']: {row['organization_id']} for row in value.get('evidence', []) if row.get('organization_id')})
    return value


def topic(store, policy, day):
    from .topics import candidates
    if not captured(store, 'selected_topic_snapshot'):
        raise ValueError('原批次的选题快照缺失，请发起新批次')
    with store.connection() as db:
        row = db.execute("SELECT id,data FROM objects WHERE kind='topic_selection' AND json_extract(data,'$.day')=? "
                         "AND json_extract(data,'$.scope_topic')=? ORDER BY created DESC,rowid DESC LIMIT 1", (day, policy['topic'])).fetchone()
    selected = {**json.loads(row['data']), 'id': row['id']} if row else None
    if encoded(selected) != encoded(store.resume_artifacts['selected_topic_snapshot']):
        raise ValueError('手动选题已变化，请发起新批次；不会用新选择替换原批次')
    brief = record(store, 'brief_id', 'brief')
    if brief:
        if brief.get('day') != day or brief.get('scope_topic') != policy['topic'] or brief.get('version') != store.policy()[0]:
            raise ValueError('原批次的选题日期、主题或规则已变化，请发起新批次')
        signatures = set(brief.get('result', {}).get('organization_ids', []))
        _sources(store, policy, {identity: signatures for identity in brief.get('source_ids', [])})
    return {'brief_id': brief['id'] if brief else None, 'candidates': candidates(brief) if brief else [], 'selected': selected}, brief
