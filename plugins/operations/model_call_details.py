"""Local request evidence joined to the existing per-attempt usage ledger."""
import hashlib
import json
import logging
import math
import re

from agent.token_ledger import connection

_SECRET = re.compile(r'(^|_)(api_key|access_token|refresh_token|password|authorization|cookie|secret|headers)($|_)', re.IGNORECASE)


def sanitize(value):
    if hasattr(value, 'model_dump'):
        value = value.model_dump(mode='json')
    if isinstance(value, dict):
        return {str(key): '[已隐藏]' if _SECRET.search(str(key)) else sanitize(item)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        if value.startswith('data:') and ';base64,' in value:
            return {'media_type': value.split(';', 1)[0][5:], 'sha256': hashlib.sha256(value.encode()).hexdigest(),
                    'notice': '图片数据已省略，保留指纹'}
        if value.lstrip().startswith(('{', '[')):
            try:
                parsed = json.loads(value)
            except ValueError:
                return value
            cleaned = sanitize(parsed)
            return value if cleaned == parsed else json.dumps(cleaned, ensure_ascii=False)
        return value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS operations_model_calls ('
               'call_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, data TEXT NOT NULL)')
    db.execute('CREATE INDEX IF NOT EXISTS operations_model_trace ON operations_model_calls(trace_id)')


def field(value, key, default=None):
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def cost_receipt(usage):
    amount = field(usage, 'cost')
    if type(amount) in (int, float) and math.isfinite(amount) and amount >= 0:
        return {'amount': amount, 'currency': field(usage, 'currency'), 'source': 'provider_receipt'}
    return {'amount': None, 'currency': None, 'source': 'unknown'}


def record(event, *, trace_id, attempt, request, metadata, response=None, error=None, normalized=None):
    with connection(attempt.context['path']) as db:
        schema(db)
        if event == 'request':
            body = {key: value for key, value in request.items() if key not in {'timeout', 'http_client'}}
            value = {'request': sanitize(body), 'api_mode': metadata.get('api_mode'), 'state': 'running'}
            db.execute('INSERT INTO operations_model_calls VALUES (?,?,?)',
                       (attempt.id, trace_id, json.dumps(value, ensure_ascii=False)))
            return
        row = db.execute('SELECT data FROM operations_model_calls WHERE call_id=?', (attempt.id,)).fetchone()
        if not row:
            return
        choices = field(response, 'choices', []) or []
        message = normalized[0] if normalized else field(choices[0], 'message') if choices else None
        usage = field(response, 'usage')
        value = {**json.loads(row['data']), 'state': 'failed' if error else 'completed',
                 'raw_response': sanitize(field(message, 'content')), 'response': sanitize(message),
                 'usage': sanitize(usage), 'cost': cost_receipt(usage),
                 'error': str(error) if error else None,
                 'finish_reason': normalized[1] if normalized else field(choices[0], 'finish_reason') if choices else None}
        db.execute('UPDATE operations_model_calls SET data=? WHERE call_id=?',
                   (json.dumps(value, ensure_ascii=False), attempt.id))


def parsed(path, call_id, result=None, error=None):
    if not call_id:
        return
    try:
        _save_parsed(path, call_id, result, error)
    except Exception:
        logging.getLogger(__name__).exception('Could not save parsed model result')


def _save_parsed(path, call_id, result, error):
    with connection(path) as db:
        schema(db)
        row = db.execute('SELECT data FROM operations_model_calls WHERE call_id=?', (call_id,)).fetchone()
        if row:
            value = {**json.loads(row['data']), 'parsed_result': sanitize(result), 'parse_error': str(error) if error else None}
            db.execute('UPDATE operations_model_calls SET data=? WHERE call_id=?', (json.dumps(value, ensure_ascii=False), call_id))


def detail(query, identity):
    """Details retain scope filters but are reachable from historical execution records."""
    with connection(query.path) as db:
        row = db.execute('SELECT c.*,t.stage,t.task_name,t.run_id,t.business_id,t.topic_id '
                         'FROM token_usage_calls c JOIN token_usage_tasks t ON t.id=c.task_id '
                         'WHERE c.id=?' + query.detail_where, [identity, *query.detail_args]).fetchone()
        if not row:
            raise LookupError('调用不存在于当前 Profile 或筛选范围')
        schema(db)
        saved = db.execute('SELECT * FROM operations_model_calls WHERE call_id=?', (identity,)).fetchone()
        value = json.loads(saved['data']) if saved else None
        attempts = [dict(row)]
        if saved:
            attempts = [dict(item) for item in db.execute(
                'SELECT c.* FROM token_usage_calls c JOIN operations_model_calls d ON d.call_id=c.id '
                'WHERE d.trace_id=? AND c.task_id=? ORDER BY c.started,c.id', (saved['trace_id'], row['task_id']))]
    return {'call': dict(row), 'detail': value, 'attempts': attempts,
            'notice': '' if saved else '此请求未保存输入输出，历史原文无法补回。'}
