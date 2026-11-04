"""Freeze the artifacts of an interrupted batch instead of silently taking a newer producer's output."""
import json

FIELDS = {'brief': 'brief_id', 'industry_report': 'industry_report_id', 'analytics_report': 'analytics_report_id'}


def capture(store, db, day, policy, previous=None, *, batch=None):
    result = dict(previous or {})
    for kind, field in FIELDS.items():
        rows = db.execute("SELECT id,data FROM objects WHERE kind=? AND json_extract(data,'$.day')=? "
                          "AND json_extract(data,'$.scope_topic')=? ORDER BY created DESC,rowid DESC", (kind, day, policy['topic'])).fetchall()
        for row in rows:
            data = json.loads(row['data'])
            owner = batch or store.manual_run_id
            if owner and data.get('manual_run_id') != owner:
                continue
            result[field] = row['id']
            break
    selected = db.execute("SELECT id,data FROM objects WHERE kind='topic_selection' AND json_extract(data,'$.day')=? "
                          "AND json_extract(data,'$.scope_topic')=? ORDER BY created DESC,rowid DESC LIMIT 1", (day, policy['topic'])).fetchone()
    result.setdefault('selected_topic_snapshot', {**json.loads(selected['data']), 'id': selected['id']} if selected else None)
    return result


def produced(store, stage, result):
    frozen = getattr(store, 'resume_artifacts', None)
    if frozen is None:
        return
    if stage in {'analytics', 'industry'} and isinstance(result, dict) and result.get('report_id'):
        frozen[FIELDS['analytics_report' if stage == 'analytics' else 'industry_report']] = result['report_id']
    if stage == 'topics':
        with store.connection() as db:
            row = db.execute("SELECT id FROM objects WHERE kind='brief' AND json_extract(data,'$.run_id')=? "
                             'ORDER BY created DESC,rowid DESC LIMIT 1', (store.current_run_id,)).fetchone()
        if row:
            frozen['brief_id'] = row['id']
