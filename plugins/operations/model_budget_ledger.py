"""Durable token receipts and in-flight reservations across all topics in a Profile."""
from datetime import datetime
import json
import sqlite3
from zoneinfo import ZoneInfo

SCHEMA = '''
CREATE TABLE IF NOT EXISTS {prefix}model_budget_usage (
 id TEXT PRIMARY KEY, topic_id TEXT NOT NULL, day TEXT NOT NULL, profile_day TEXT NOT NULL,
 state TEXT NOT NULL, tokens INTEGER NOT NULL DEFAULT 0, exempt INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS {prefix}model_budget_day ON model_budget_usage(profile_day,topic_id,day);
CREATE TABLE IF NOT EXISTS {prefix}model_budget_imports (topic_id TEXT PRIMARY KEY);
'''


def prefix(store):
    return 'directory.' if store.workspace else ''


def topic_id(store):
    return store.scope['id'] if store.scope else ''


def known_tokens(usage):
    if hasattr(usage, 'model_dump'):
        usage = usage.model_dump()
    if not isinstance(usage, dict):
        return None
    for input_key, output_key in (('prompt_tokens', 'completion_tokens'), ('input_tokens', 'output_tokens')):
        if all(type(usage.get(key)) is int and usage[key] >= 0 for key in (input_key, output_key)):
            total = usage[input_key] + usage[output_key]
            if input_key == 'input_tokens':
                cached = [usage.get(key, 0) for key in ('cache_read_input_tokens', 'cache_creation_input_tokens')]
                if any(type(value) is not int or value < 0 for value in cached):
                    return None
                total += sum(cached)
            return total
    total = usage.get('total_tokens')
    return total if type(total) is int and total >= 0 else None


def initialize(store):
    name = prefix(store)
    with store.connection() as db:
        from .storage_schema import ready
        from .model_budget_recovery import OWNER_SCHEMA
        schema = (SCHEMA + OWNER_SCHEMA).format(prefix=name)
        if not ready(db, schema, 'directory' if store.workspace else 'main'):
            db.executescript(schema)
        imported = {row[0] for row in db.execute(f'SELECT topic_id FROM {name}model_budget_imports')}
        timezone = json.loads(db.execute("SELECT data FROM directory.preferences WHERE id='limits'").fetchone()[0]).get('_timezone', 'Asia/Shanghai') if store.workspace else store.policy()[1]['timezone']
        topics = [(topic_id(store), store.path)]
        if store.workspace:
            topics = [(row['id'], store.workspace.root / row['file']) for row in db.execute('SELECT id,file FROM directory.topics')]
    for identity, path in topics:
        if identity in imported or not path or not path.exists():
            continue
        rows = legacy_rows(path, identity, timezone)
        with store.connection() as db:
            db.executemany(f'INSERT OR IGNORE INTO {name}model_budget_usage VALUES (?,?,?,?,?,?,?)', rows)
            db.execute(f'INSERT OR IGNORE INTO {name}model_budget_imports VALUES (?)', (identity,))

    from .model_budget_recovery import recover
    recover(store)


def legacy_rows(path, identity, timezone):
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        events = db.execute("SELECT id,at,kind,data FROM events WHERE kind IN ('model_call','usage') ORDER BY id").fetchall()
    finally:
        db.close()
    groups = {}
    for event_id, at, kind, raw in events:
        data = json.loads(raw)
        if data.get('budget_id') or data.get('quota_exempt'):
            continue
        group = groups.setdefault((data.get('day'), data.get('run_id')), {'model_call': [], 'usage': []})
        group[kind].append((event_id, at, data))
    rows = []
    for (day, _), group in groups.items():
        usages = [known_tokens(item[2].get('tokens')) for item in group['usage']]
        matched = len(usages) == len(group['model_call']) and all(value is not None for value in usages)
        for index, (event_id, at, _) in enumerate(group['model_call']):
            try:
                shared_day = datetime.fromisoformat(at).astimezone(ZoneInfo(timezone)).date().isoformat()
            except ValueError:
                shared_day = day
            tokens = usages[index] if matched else sum(value or 0 for value in usages) if index == 0 else 0
            rows.append((f'legacy:{identity}:{event_id}', identity, day, shared_day, 'confirmed' if matched else 'unknown', tokens, 0))
    return rows


def totals(store, db, day, *, profile=False):
    where, args = ('profile_day=?', [day]) if profile else ('topic_id=? AND day=?', [topic_id(store), day])
    row = db.execute(f"SELECT coalesce(sum(tokens),0),coalesce(sum(state='pending'),0),coalesce(sum(state='unknown'),0) FROM {prefix(store)}model_budget_usage WHERE exempt=0 AND {where}", args).fetchone()
    return {'tokens': row[0], 'pending': row[1], 'unknown': row[2]}


def check(used, limit, label):
    if used['unknown']:
        raise ValueError(f'{label}存在未确认的 Token 用量，请核对用量或改用次数预算')
    if used['pending']:
        raise ValueError(f'{label}有模型调用尚未返回 Token 用量，请等待完成')
    if used['tokens'] >= limit:
        raise ValueError(f'达到{label}每日 Token 预算（{used["tokens"]}/{limit}）')


def reserve(store, db, policy, day, identity, exempt):
    from .model_budget_settings import profile_config, topic_config
    from .policy import local_day
    shared_day = day
    if not exempt and topic_config(policy)['mode'] == 'tokens':
        check(totals(store, db, day), topic_config(policy)['tokens'], '当前主题')
    if store.workspace:
        limits = json.loads(db.execute("SELECT data FROM directory.preferences WHERE id='limits'").fetchone()[0])
        shared_day = local_day({'timezone': limits.get('_timezone', 'Asia/Shanghai')}, getattr(store, 'execution_now', None))
        shared = profile_config(limits)
        if not exempt and shared['mode'] == 'tokens':
            check(totals(store, db, shared_day, profile=True), shared['tokens'], '全部主题共享')
    db.execute(f'INSERT INTO {prefix(store)}model_budget_usage VALUES (?,?,?,?,?,0,?)',
               (identity, topic_id(store), day, shared_day, 'pending', int(exempt)))
    from .model_budget_recovery import own
    own(db, prefix(store), identity)


def marker(context):
    if not context:
        return 0
    from agent.token_ledger import connection
    with connection(context['path']) as db:
        return db.execute('SELECT coalesce(max(rowid),0) FROM token_usage_calls WHERE task_id=?', (context['task_id'],)).fetchone()[0]


def settle(store, identity, response, context, after):
    rows = []
    if context:
        from agent.token_ledger import connection
        with connection(context['path']) as db:
            rows = db.execute('SELECT state,total_tokens FROM token_usage_calls WHERE task_id=? AND rowid>?', (context['task_id'], after)).fetchall()
    if rows:
        confirmed = all(row['state'] == 'confirmed' and row['total_tokens'] is not None for row in rows)
        tokens = sum(row['total_tokens'] or 0 for row in rows)
    else:
        tokens = known_tokens(getattr(response, 'usage', None))
        confirmed = tokens is not None
    with store.connection() as db:
        db.execute(f'UPDATE {prefix(store)}model_budget_usage SET state=?,tokens=? WHERE id=?',
                   ('confirmed' if confirmed else 'unknown', tokens or 0, identity))
