"""Plans and progress survive readers, profile switches and failed execution owners."""
import sqlite3

import pytest


def test_snapshot_live_progress_and_output_survive_reopen_and_rule_edits(tmp_path, monkeypatch):
    from cron import executions, jobs, task_history as journal
    from cron.execution_identity import enter_cron_execution, exit_cron_execution

    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    job = jobs.create_job(prompt='原始任务', schedule='every 1h')
    journal.define(job['id'], {'goal': '原始目标'})
    attempt = executions.create_execution(job['id'], source='manual')
    running = executions.mark_execution_running(attempt['id'])
    journal.declare(attempt['id'], [dict(id='collect', title='采集', intent='读取来源'),
                                    dict(id='report', title='日报', intent='汇总记录')], {'version': 1})
    journal.progress(attempt['id'], 'collect', state='running', detail='已读取第一个来源', data={'url': 'https://example.com'})
    # Another connection reads committed progress before completion, not a process-local cache.
    assert journal.detail(job)['steps'][0]['detail'] == '已读取第一个来源'
    journal.define(job['id'], {'goal': '修改后的目标'})
    edited = jobs.update_job(job['id'], {'prompt': '修改后的任务'})
    data = journal.detail(edited)
    assert data['plan']['prompt'] == '修改后的任务'
    assert data['snapshot']['prompt'] == '原始任务'
    assert data['snapshot']['definition']['goal'] == '原始目标'
    token = enter_cron_execution(job, attempt['id'], running)
    try:
        output_path = jobs.save_job_output(job['id'], '完整成果\n' * 500)
    finally:
        exit_cron_execution(token)
    output_path.unlink()
    executions.finish_execution(attempt['id'], success=False, error='模拟中断')
    journal.progress(attempt['id'], 'collect', state='completed', detail='迟到的错误成功消息')
    persisted = journal.detail(edited)
    assert persisted['output'] == '完整成果\n' * 500
    assert [s['state'] for s in persisted['steps']] == ['interrupted', 'not_run']
    assert persisted['events'][0]['data']['url'] == 'https://example.com'
    with sqlite3.connect(tmp_path / 'cron' / 'executions.db') as db:
        assert db.execute('SELECT state FROM task_steps WHERE id=?', ('collect',)).fetchone()[0] == 'interrupted'


def test_profile_boundary_execution_boundary_and_retention(tmp_path, monkeypatch):
    from cron import executions, jobs, task_history as journal
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override

    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    job = jobs.create_job(prompt='profile A', schedule='every 1h')
    attempt = executions.create_execution(job['id'], source='manual')
    journal.declare(attempt['id'], [dict(id='one', title='one', intent='test')], {})
    journal.progress(attempt['id'], 'one', state='running', detail='A data')
    other = jobs.create_job(prompt='other', schedule='every 1h')
    with pytest.raises(LookupError):
        journal.detail(other, attempt['id'])
    token = set_hermes_home_override(str(tmp_path / 'other'))
    try:
        assert journal.detail(job)['attempts'] == []
        with pytest.raises(LookupError):
            journal.detail(job, attempt['id'])
    finally:
        reset_hermes_home_override(token)
    monkeypatch.setattr(executions, 'MAX_TERMINAL_EXECUTIONS', 0)
    executions.finish_execution(attempt['id'], success=True)
    with journal.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM task_events').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM task_runs').fetchone()[0] == 0
