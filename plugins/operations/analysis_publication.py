"""Recheck data permissions at the durable reservation and browser submit boundaries."""
import json

from .analysis_config import DEFAULT, window
from .policy import local_day


def check(db, action, policy, day=None):
    context = action.get('content', {}).get('analysis_context') if action.get('kind') == 'publish' else None
    if not context:
        return
    row = db.execute("SELECT data FROM objects WHERE kind='analysis_config' ORDER BY created DESC LIMIT 1").fetchone()
    config = json.loads(row[0]) if row else {'version': 0, 'config': DEFAULT}
    active = {}
    for row in db.execute('SELECT * FROM business_datasets'):
        dataset = json.loads(row['data'])
        if dataset['active'] and dataset['scope_topic'] == policy['topic']:
            active[row['id']] = row['version']
    expected = {d['id']: d['version'] for d in context['datasets']}
    if (context['scope_topic'] != policy['topic'] or context['config_version'] != config['version'] or active != expected
            or context['window'] != window(config['config'], action['content']['day'] if action.get('human_review') else day or local_day(policy))):
        raise ValueError('分析依据或公开权限已变化，禁止提交旧稿件；请重新生产并检查')


def check_step(db, command, phase):
    if command['kind'] != 'publish' or phase != 'started':
        return
    policy = json.loads(db.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])
    check(db, json.loads(command['payload']), policy)
