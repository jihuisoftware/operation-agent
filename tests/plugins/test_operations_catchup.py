"""Missed slots coalesce before execution, cancellation and journal projection."""
from datetime import datetime, UTC

import pytest

from plugins.operations import workflow
from plugins.operations.progress import planned_steps
from plugins.operations.runtime import tick
from plugins.operations.store import Store
from plugins.operations.upcoming import upcoming, cancel


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path / 'operations.db')
    _, policy = store.policy()
    policy.update(enabled=True, topic='步行', goal='路线资料')
    policy['modules'] = {stage: stage in {'research', 'report'} for stage in policy['modules']}
    policy['times']['research'] = ['09:00', '11:00', '15:00']
    store.configure(policy, 0)
    with store.connection() as db:
        db.execute("UPDATE events SET at='2026-10-01T00:00:00+00:00' WHERE kind='policy'")
    return store


@pytest.mark.parametrize('cancel_latest', [False, True])
def test_only_latest_due_is_visible_claimed_and_recorded(store, monkeypatch, cancel_latest):
    now = datetime(2026, 11, 1, 10, tzinfo=UTC)  # Shanghai 18:00
    calls = []
    monkeypatch.setattr(workflow, 'research', lambda *args: calls.append(args[2]) or '资料已保存')
    view = upcoming(store, now)
    overdue = [s for s in view['steps'] if s['stage'] == 'research' and s['day'] <= '2026-11-01']
    assert [s['slot'] for s in overdue] == ['15:00']
    steps = planned_steps(store, store.policy()[1], now, None)
    assert [s['id'] for s in steps if s['id'].startswith('research:')] == ['research:15:00']
    if cancel_latest:
        cancel(store, {**overdue[0], 'version': view['version']}, now)
    tick(store, now)
    tick(Store(store.path), now)
    assert calls == ([] if cancel_latest else ['2026-11-01'])
    rows = [r for r in store.snapshot()['runs'] if r['stage'] == 'research']
    assert [(r['day'], r['slot']) for r in rows] == [('2026-11-01', '15:00')]
    assert rows[0]['state'] == ('cancelled' if cancel_latest else 'completed')
    assert not any(r['state'] == 'missed' for r in store.snapshot()['runs'])


def test_long_outage_only_recovers_latest_day_and_uses_actual_day_for_work(store, monkeypatch):
    now = datetime(2026, 11, 1, 0, tzinfo=UTC)  # Before today's first slot
    calls = []
    monkeypatch.setattr(workflow, 'research', lambda *args: calls.append(args[2]) or '资料已保存')
    tick(store, now)
    tick(Store(store.path), now)
    assert calls == ['2026-11-01']
    assert {(r['day'], r['stage'], r['slot']) for r in store.snapshot()['runs']} == {
        ('2026-10-31', 'research', '15:00'), ('2026-10-31', 'report', '21:00')}
    reports = store.objects('report')
    assert [r['day'] for r in reports] == ['2026-10-31']
    assert '延迟补生成：是' in reports[0]['markdown']


def test_offline_slot_is_superseded_without_history_when_desktop_returns(store, monkeypatch):
    version, policy = store.policy()
    policy['modules'] = {stage: stage == 'comments' for stage in policy['modules']}
    store.configure(policy, version)
    calls = []
    monkeypatch.setattr(workflow, 'interact', lambda *args, **kwargs: calls.append(args[2]) or '已检查')
    tick(store, datetime(2026, 11, 1, 8, tzinfo=UTC))  # 16:00, desktop offline
    assert not store.snapshot()['runs']
    store.claim('simulated-desktop', busy=True)
    tick(store, datetime(2026, 11, 1, 12, tzinfo=UTC))  # 20:00, 19:00 supersedes 15:00
    tick(store, datetime(2026, 11, 1, 12, 1, tzinfo=UTC))
    assert calls == ['2026-11-01']
    assert [(r['stage'], r['slot']) for r in store.snapshot()['runs']] == [('comments', '19:00')]
