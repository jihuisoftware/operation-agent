"""Single-occurrence cancellation for jobs whose script/agent is one executable step."""
import hashlib
import json

from cron.task_history import PLAN_FIELDS, connection, declare, progress
from hermes_time import now


def stamp(job):
    return hashlib.sha256(json.dumps({k: job.get(k) for k in PLAN_FIELDS}, sort_keys=True).encode()).hexdigest()


def initialize(db):
    db.execute('''CREATE TABLE IF NOT EXISTS planned_job_steps (
        job_id TEXT NOT NULL, instant TEXT NOT NULL, plan TEXT NOT NULL, state TEXT NOT NULL,
        updated TEXT NOT NULL, execution_id TEXT, PRIMARY KEY(job_id, instant, plan))''')
    db.execute('''CREATE TRIGGER IF NOT EXISTS planned_job_steps_prune AFTER DELETE ON executions BEGIN
        DELETE FROM planned_job_steps WHERE execution_id=OLD.id; END''')


def managed(job_id):
    with connection() as db:
        row = db.execute('SELECT data FROM task_definitions WHERE job_id=?', (job_id,)).fetchone()
    return bool(row and json.loads(row[0]).get('managed_steps'))


def list_upcoming(jobs):
    from cron.occurrences import scheduled_instant
    result = []
    jobs = [job for job in jobs if job.get('enabled') and job.get('next_run_at') and not managed(job['id'])]
    with connection() as db:
        initialize(db)
        for job in jobs:
            instant = scheduled_instant(job['next_run_at'])
            plan = stamp(job)
            row = db.execute('SELECT state FROM planned_job_steps WHERE job_id=? AND instant=? AND plan=?',
                             (job['id'], instant, plan)).fetchone()
            result.append({'job_id': job['id'], 'name': job.get('name') or job['id'], 'instant': instant,
                           'plan': plan, 'state': row[0] if row else 'pending',
                           'intent': job.get('prompt') or job.get('script') or '',
                           'script': job.get('script'), 'no_agent': bool(job.get('no_agent'))})
    return sorted(result, key=lambda row: row['instant'])


def cancel(job, instant, plan):
    from cron.occurrences import scheduled_instant
    if managed(job['id']) or not job.get('enabled') or not instant or (
        scheduled_instant(job.get('next_run_at')) != instant or stamp(job) != plan
    ):
        raise ValueError('任务计划已变更，请刷新待执行列表')
    with connection() as db:
        initialize(db)
        db.execute('INSERT OR IGNORE INTO planned_job_steps VALUES (?,?,?,?,?,NULL)',
                   (job['id'], instant, plan, 'cancelled', now().isoformat()))
        row = db.execute('SELECT state FROM planned_job_steps WHERE job_id=? AND instant=? AND plan=?',
                         (job['id'], instant, plan)).fetchone()
        if row[0] != 'cancelled':
            raise ValueError('步骤已经开始，不能取消待执行步骤')
    return {'state': 'cancelled'}


def run_planned_job(job, run_job, **kwargs):
    from cron.executions import get_execution
    if managed(job['id']):
        return run_job(job, **kwargs)
    execution = get_execution(job['execution_id'])
    instant = execution.get('scheduled_instant') if execution else None
    state = 'claimed'
    if instant:
        with connection() as db:
            initialize(db)
            key = (job['id'], instant, stamp(job))
            db.execute('INSERT OR IGNORE INTO planned_job_steps VALUES (?,?,?,?,?,?)', (*key, 'claimed', now().isoformat(), job['execution_id']))
            state = db.execute('SELECT state FROM planned_job_steps WHERE job_id=? AND instant=? AND plan=?', key).fetchone()[0]
            db.execute('UPDATE planned_job_steps SET execution_id=? WHERE job_id=? AND instant=? AND plan=?', (job['execution_id'], *key))
    declare(job['execution_id'], [{'id': 'execute', 'title': '执行任务',
            'intent': job.get('prompt') or job.get('script') or '', 'state': 'pending'}], {})
    if state == 'cancelled':
        message = '人工取消本次步骤，未启动脚本或 Agent；后续排期保持不变。'
        progress(job['execution_id'], 'execute', state='cancelled', detail=message)
        return True, message, message, None
    progress(job['execution_id'], 'execute', state='running', detail='任务正在执行，工具调用过程可在实时状态中查看')
    result = run_job(job, **kwargs)
    progress(job['execution_id'], 'execute', state='completed' if result[0] else 'failed', detail=str(result[3] or result[2] or '执行结束'))
    return result
