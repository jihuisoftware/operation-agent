"""Versioned analysis settings, separate from external-action authorization."""
from copy import deepcopy
from datetime import date, timedelta
import json

from .store import encoded
from .policy import now_iso

DEFAULT = {'period': '7', 'start': '', 'end': '', 'industry': '', 'region': '', 'focus': []}


def settings(store):
    rows = store.objects('analysis_config')
    return rows[0] if rows else {'version': 0, 'config': deepcopy(DEFAULT)}


def configure(store, body):
    value = {**DEFAULT, **body['config']}
    if set(value) != set(DEFAULT) or value['period'] not in ('1', '7', '30', 'custom'):
        raise ValueError('分析周期配置无效')
    if any(not isinstance(value[k], str) or len(value[k]) > 200 for k in ('start', 'end', 'industry', 'region')):
        raise ValueError('分析范围格式无效')
    if not isinstance(value['focus'], list) or len(value['focus']) > 30 or any(not isinstance(x, str) or len(x) > 100 for x in value['focus']):
        raise ValueError('关注对象最多 30 个，每项不超过 100 字')
    window(value, date.today().isoformat())
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT data FROM objects WHERE kind='analysis_config' ORDER BY created DESC LIMIT 1").fetchone()
        current = json.loads(row[0])['version'] if row else 0
        if current != body['version']:
            raise ValueError('分析配置已变化，请刷新')
        data = {'version': current + 1, 'config': value, 'created': now_iso()}
        db.execute("INSERT INTO objects VALUES (?, 'analysis_config', ?, ?)", ('analysis-config:' + str(current + 1), encoded(data), now_iso()))
    return data


def window(config, day):
    end = date.fromisoformat(config['end']) if config['period'] == 'custom' else date.fromisoformat(day)
    start = date.fromisoformat(config['start']) if config['period'] == 'custom' else end - timedelta(days=int(config['period']) - 1)
    length = (end - start).days + 1
    if not 1 <= length <= 366:
        raise ValueError('日期范围需为 1～366 天')
    return {'start': start.isoformat(), 'end': end.isoformat(), 'previous_start': (start - timedelta(days=length)).isoformat(),
            'previous_end': (start - timedelta(days=1)).isoformat()}
