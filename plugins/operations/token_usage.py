"""Token analytics over the runtime ledger, never over cumulative session totals."""
import base64
import csv
from datetime import datetime, timedelta, UTC
import io
import json
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agent.token_ledger import TOKENS, connection, recover_if_due
from .workspaces import Workspaces

DIMENSIONS = {'business': 't.business_id', 'topic': 't.topic_id', 'module': 't.stage',
              'model': 'c.model', 'provider': 'c.provider', 'purpose': 'c.purpose'}
SUMS = ','.join(f'COALESCE(SUM(c.{key}),0) AS {key}' for key in TOKENS)
COUNTS = ",COUNT(*) AS calls,SUM(c.state='running') AS running,SUM(c.state NOT IN ('confirmed','running')) AS unknown"


def window(period, tz, until=None):
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError('无效时区') from exc
    now = datetime.now(UTC)
    if until is not None:
        now = datetime.fromtimestamp(float(until), UTC)
        if now > datetime.now(UTC) + timedelta(seconds=5):
            raise ValueError('截止时间不能在未来')
    starts = {'hour': now - timedelta(hours=1), 'day': now.astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0),
              'week': now - timedelta(days=7), 'month': now - timedelta(days=30), 'live': now - timedelta(hours=1)}
    if period not in starts:
        raise ValueError('无效时间范围')
    return starts[period].timestamp(), now.timestamp(), zone


def filters(directory, values):
    catalog = directory.catalog()
    businesses = {b['id']: b['name'] for b in catalog['businesses']}
    topics = {t['id']: t for t in catalog['topics']}
    business, topic = values.get('business', ''), values.get('topic', '')
    if business and business != '__unassigned__' and business not in businesses:
        raise ValueError('业务不存在于当前 Profile')
    if topic and topic != '__unassigned__' and (topic not in topics or (business and topics[topic]['business_id'] != business)):
        raise ValueError('主题不属于当前业务或 Profile')
    clauses, args = [], []
    for key, value in values.items():
        if key not in DIMENSIONS:
            raise ValueError('不支持的统计维度')
        if value:
            clauses.append(f'{DIMENSIONS[key]}=?')
            args.append('' if value == '__unassigned__' else value)
    return clauses, args, businesses, topics


def cursor_encode(value):
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode()


def cursor_decode(value, count):
    try:
        result = json.loads(base64.urlsafe_b64decode(value))
        if not isinstance(result, list) or len(result) != count:
            raise ValueError()
        return result
    except (ValueError, TypeError) as exc:
        raise ValueError('分页游标无效') from exc


class UsageQuery:
    def __init__(self, *, period='day', tz='Asia/Shanghai', until=None, selected=None, directory=None, path=None):
        self.directory = directory or Workspaces()
        self.path = path
        self.start, self.end, self.zone = window(period, tz, until)
        self.period = period
        clauses, args, self.businesses, self.topics = filters(self.directory, selected or {})
        if period == 'live':
            clauses.append("t.state='running'")
        else:
            clauses.append('COALESCE(c.received,c.started)>=?')
            args.append(self.start)
        clauses.append('COALESCE(c.received,c.started)<=?')
        args.append(self.end)
        self.where, self.args = ' AND '.join(clauses), args
        self.source = ' FROM token_usage_calls c JOIN token_usage_tasks t ON t.id=c.task_id WHERE ' + self.where

    def label(self, kind, identity):
        if kind == 'business':
            return self.businesses.get(identity, '未关联业务')
        if kind == 'topic':
            return self.topics.get(identity, {}).get('name', '未关联主题')
        return identity or '未分类'

    def summary(self):
        with connection(self.path) as db:
            recover_if_due(db)
            db.create_function('usage_bucket', 1, self.bucket)
            total = dict(db.execute('SELECT ' + SUMS + COUNTS + self.source, self.args).fetchone())
            groups = {}
            for kind, field in DIMENSIONS.items():
                groups[kind] = [dict(row) for row in db.execute(f'SELECT {field} AS id,{SUMS}{COUNTS}' + self.source + f' GROUP BY {field} ORDER BY total_tokens DESC', self.args)]
                for row in groups[kind]:
                    row['label'] = self.label(kind, row['id'])
            trend = [dict(row) for row in db.execute('SELECT usage_bucket(c.received) AS at,' + SUMS + self.source + ' AND c.received IS NOT NULL AND c.received>=? GROUP BY at ORDER BY at', [*self.args, self.start])]
            since = db.execute('SELECT since FROM token_usage_meta WHERE id=1').fetchone()[0]
        return {'totals': total, 'groups': groups, 'trend': trend, 'since': since, 'start': self.start,
                'until': self.end, 'timezone': str(self.zone), 'period': self.period, 'partial_history': self.start < since}

    def bucket(self, value):
        date = datetime.fromtimestamp(value, self.zone)
        if self.period in {'live', 'hour'}:
            date = date.replace(second=0, microsecond=0)
        elif self.period == 'day':
            date = date.replace(minute=0, second=0, microsecond=0)
        else:
            date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        return date.isoformat()

    def tasks(self, cursor=None):
        sql = 'SELECT t.*,' + SUMS + COUNTS + self.source + ' GROUP BY t.id'
        args = list(self.args)
        if cursor:
            total, identity = cursor_decode(cursor, 2)
            sql += ' HAVING (COALESCE(SUM(c.total_tokens),0),t.id)<(?,?)'
            args.extend((total, identity))
        with connection(self.path) as db:
            recover_if_due(db)
            rows = [dict(r) for r in db.execute(sql + ' ORDER BY total_tokens DESC,t.id DESC LIMIT 51', args)]
        more = len(rows) > 50
        rows = rows[:50]
        for row in rows:
            row['business_name'] = self.label('business', row['business_id'])
            row['topic_name'] = self.label('topic', row['topic_id'])
            row.pop('pid', None)
            row.pop('process_started', None)
        return {'items': rows, 'cursor': cursor_encode([rows[-1]['total_tokens'], rows[-1]['id']]) if more else None, 'until': self.end}

    def calls(self, task, cursor=None):
        args = [*self.args, task]
        suffix = ' AND t.id=?'
        if cursor:
            stamp, identity = cursor_decode(cursor, 2)
            suffix += ' AND (c.started,c.id)>(?,?)'
            args.extend((stamp, identity))
        with connection(self.path) as db:
            rows = [dict(r) for r in db.execute('SELECT c.*' + self.source + suffix + ' ORDER BY c.started,c.id LIMIT 101', args)]
        more = len(rows) > 100
        rows = rows[:100]
        return {'items': rows, 'cursor': cursor_encode([rows[-1]['started'], rows[-1]['id']]) if more else None}

    def export(self):
        fields = ['id', 'task_id', 'business_id', 'topic_id', 'stage', 'session_id', 'turn_id', 'purpose', 'model', 'provider', 'started', 'received', 'state', *TOKENS]
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(fields)
        yield '\ufeff' + stream.getvalue()
        with connection(self.path) as db:
            rows = db.execute('SELECT c.*,t.business_id,t.topic_id,t.stage,t.session_id,t.turn_id' + self.source + ' ORDER BY c.started,c.id', self.args)
            for row in rows:
                stream.seek(0)
                stream.truncate()
                values = [row[key] for key in fields]
                writer.writerow(["'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@', '\t', '\r')) else v for v in values])
                yield stream.getvalue()
