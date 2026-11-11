"""Filter before paging; content lists carry summaries rather than source snapshots."""
import json
import time

from .content_release import fingerprint, load

STATES = {
    'all': (), 'in_progress': ('queued', 'executing'), 'needs_attention': ('submitted', 'unknown', 'blocked'),
    'published': ('published', 'confirmed'), 'failed': ('failed', 'cancelled', 'confirmed_not_published'),
}
JOIN = ("FROM objects c LEFT JOIN objects r ON r.id='content-release:'||c.id AND r.kind='content_release' "
        "LEFT JOIN actions a ON a.rowid=(SELECT max(x.rowid) FROM actions x WHERE x.kind='publish' "
        "AND json_extract(x.data,'$.content.id')=c.id) WHERE c.kind='content'")
FILTERS = {'drafts': "a.id IS NULL AND COALESCE(json_extract(r.data,'$.state'),'')!='scheduled'",
           'pending': "a.id IS NULL AND json_extract(r.data,'$.state')='scheduled'", '': '1=1'}


def summaries(rows):
    result = []
    for row in rows:
        value = dict(row)
        value.pop('cursor', None)
        value['asset_ids'] = json.loads(value.pop('assets') or '[]')
        value['release'] = json.loads(value.pop('release_json') or 'null')
        value['publication'] = json.loads(value.pop('publication_json', None) or 'null')
        result.append(value)
    return result


def listing(store, before=0, filter='', record='', status='all', compact=False):
    if filter not in {'', 'drafts', 'pending', 'published'} or status not in STATES:
        raise ValueError('内容筛选条件无效')
    size = 24 if compact else 100
    with store.connection() as db:
        counts = {key: db.execute('SELECT count(*) ' + JOIN + ' AND ' + condition).fetchone()[0] for key, condition in FILTERS.items() if key}
        counts['published'] = db.execute("SELECT count(*) FROM actions WHERE kind='publish'").fetchone()[0]
        if filter == 'published':
            return publications(db, before, record, status, size, compact, counts)
        condition = '1=1' if record else FILTERS[filter]
        fields = ("c.rowid AS cursor,c.id,c.created,json_extract(c.data,'$.title') AS title,"
                  "substr(json_extract(c.data,'$.body'),1,140) AS excerpt,json_extract(c.data,'$.asset_ids') AS assets,"
                  "json_extract(c.data,'$.day') AS basis_day,json_extract(c.data,'$.parent_content_id') AS parent_content_id,"
                  "json_extract(c.data,'$.manual_revision') AS manual_revision,a.id AS publication_action_id,a.state AS publication_state,"
                  "json_extract(c.data,'$.quality.pass') AS quality_pass,substr(json_extract(c.data,'$.quality.reason'),1,240) AS quality_reason,"
                  "CASE WHEN r.id IS NOT NULL THEN json_object('state',json_extract(r.data,'$.state'),'publish_at',json_extract(r.data,'$.publish_at'),"
                  "'account_id',json_extract(r.data,'$.account_id'),'detail',substr(json_extract(r.data,'$.detail'),1,300)) END AS release_json")
        rows = db.execute('SELECT ' + (fields if compact else 'c.rowid AS cursor,c.*') + ' ' + JOIN + ' AND ' + condition +
                          " AND (?='' OR c.id=?) AND (?=0 OR c.rowid<?) ORDER BY c.rowid DESC LIMIT ?",
                          (record, record, before, before, size + 1)).fetchall()
        page = rows[:size]
        result = {'actions': [], 'counts': counts, 'compact': compact, 'has_active': active(db),
                  'next': str(page[-1]['cursor']) if len(rows) > size else None}
        if compact:
            result['content'] = summaries(page)
            from .publication_waiting import annotate
            annotate(db, result['content'])
        else:
            from .dashboard.library_api import content_data
            result.update(content_data(db, page))
        return result


def active(db):
    return bool(db.execute("SELECT 1 FROM actions WHERE kind='publish' AND state IN ('queued','executing') LIMIT 1").fetchone()
                or db.execute("SELECT 1 FROM leases WHERE id='account' AND expires>?", (time.time(),)).fetchone()
                or db.execute("SELECT 1 FROM objects WHERE kind='publication_tracking' AND json_extract(data,'$.state') IN ('active','checking','queued') LIMIT 1").fetchone())


def publications(db, before, record, status, size, compact, counts):
    states = STATES[status]
    state_filter = '1=1' if not states or record else 'a.state IN (' + ','.join('?' for _ in states) + ')'
    params = list(states) if states and not record else []
    fields = ("a.rowid AS cursor,a.id,a.created,a.state AS publication_state,a.id AS publication_action_id,"
              "json_extract(a.data,'$.content.id') AS content_id,json_extract(a.data,'$.content.title') AS title,"
              "substr(json_extract(a.data,'$.content.body'),1,140) AS excerpt,json_extract(a.data,'$.content.asset_ids') AS assets,"
              "json_extract(a.result,'$.verified_at') AS checked_at,json_extract(a.result,'$.verification_stale') AS verification_stale,"
              "json_extract(a.result,'$.publication') AS publication_json,NULL AS release_json")
    rows = db.execute('SELECT ' + (fields if compact else 'a.rowid AS cursor,a.*') + " FROM actions a WHERE kind='publish' AND " + state_filter +
                      " AND (?='' OR id=?) AND (?=0 OR a.rowid<?) ORDER BY a.rowid DESC LIMIT ?",
                      (*params, record, record, before, before, size + 1)).fetchall()
    page = rows[:size]
    return {'actions': summaries(page) if compact else [dict(r) for r in page], 'counts': counts, 'compact': compact,
            'has_active': active(db), 'next': str(page[-1]['cursor']) if len(rows) > size else None}


def detail(store, identity, *, publication=False):
    with store.connection() as db:
        action = db.execute("SELECT * FROM actions WHERE id=? AND kind='publish'", (identity,)).fetchone() if publication else None
        if publication and not action:
            raise ValueError('发布记录不存在')
        if action:
            content = json.loads(action['data']).get('content', {})
            identity = content.get('id') or ''
        else:
            row = db.execute("SELECT data FROM objects WHERE kind='content' AND id=?", (identity,)).fetchone()
            if not row:
                raise ValueError('稿件不存在')
            content = json.loads(row[0])
        settings = db.execute('SELECT version,data FROM settings WHERE id=1').fetchone()
        version, policy = settings['version'], json.loads(settings['data'])
        target_account = policy['account_id']
        if not target_account and store.workspace:
            target_account = db.execute('SELECT a.identity FROM directory.accounts a JOIN directory.businesses b ON b.account=a.id WHERE b.id=?', (store.scope['business_id'],)).fetchone()[0]
        if not action:
            action = db.execute("SELECT * FROM actions WHERE kind='publish' AND json_extract(data,'$.content.id')=? ORDER BY rowid DESC LIMIT 1", (identity,)).fetchone()
        content = {**content, 'id': identity, 'content_revision': fingerprint(content), 'policy_version': version,
                   'release': load(db, identity), 'publication_state': action['state'] if action else None,
                   'publication_action_id': action['id'] if action else None}
        content['target_account'] = json.loads(action['data']).get('account_id') if action else target_account
        from .publication_waiting import annotate
        annotate(db, [content])
        options = editor_options(db, content)
    return {'content': content, **options, 'action': dict(action) if action else None}


def editor_options(db, content):
    sources = [dict(r) for r in db.execute("SELECT id,json_extract(data,'$.title') AS title,json_extract(data,'$.url') AS url,json_extract(data,'$.state') AS state "
                    "FROM objects WHERE kind='source' AND (id IN (SELECT value FROM json_each(?)) OR rowid IN "
                    "(SELECT rowid FROM objects WHERE kind='source' ORDER BY rowid DESC LIMIT 100))", (json.dumps(content.get('source_ids', [])),))]
    assets = [dict(r) for r in db.execute("SELECT id,json_extract(data,'$.name') AS name,json_extract(data,'$.revoked') AS revoked "
                    "FROM objects WHERE kind='asset' AND json_extract(data,'$.authorized')=1 AND (id IN (SELECT value FROM json_each(?)) OR rowid IN "
                    "(SELECT rowid FROM objects WHERE kind='asset' ORDER BY rowid DESC LIMIT 100))", (json.dumps(content.get('asset_ids', [])),))]
    return {'sources': sources, 'assets': assets}
