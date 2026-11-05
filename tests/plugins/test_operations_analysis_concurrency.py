"""Validation must release the report cursor before another connection needs to commit."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import sqlite3

import pytest

from plugins.operations import analytics
from plugins.operations.analysis_config import settings, window
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.workspaces import Workspaces


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Workspaces().store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='并发分析', goal='验证读写不会互等')
    policy['modules'].update(analytics=True, industry=True)
    store.configure(policy, 0)
    day = local_day(policy)
    config = settings(store)
    for kind in ('analytics_report', 'industry_report'):
        for index in range(3):
            store.put(kind, {'day': day, 'scope_topic': policy['topic'], 'config_version': config['version'],
                            'window': window(config['config'], day), 'datasets': [],
                            'created': f'{day}T00:00:0{index}+00:00'}, kind + str(index))
    return store, policy, day


def committed_write(store, change):
    db = sqlite3.connect(store.path, timeout=2)
    try:
        db.execute('ATTACH DATABASE ? AS directory', (str(store.workspace.path),))
        with db:
            db.execute('BEGIN IMMEDIATE')
            change(db)
    finally:
        db.close()


@pytest.mark.parametrize('kind', ['analytics_report', 'industry_report'])
def test_validation_allows_a_concurrent_writer_to_finish_before_nested_reads(prepared, monkeypatch, kind):
    store, policy, day = prepared
    original = analytics.valid
    with ThreadPoolExecutor(max_workers=1) as pool:
        def validate(*args):
            future = pool.submit(committed_write, store, lambda db: db.execute(
                "INSERT INTO events(at,kind,data) VALUES ('now','parallel_writer','{}')"))
            future.result(timeout=5)
            return original(*args)
        monkeypatch.setattr(analytics, 'valid', validate)
        report = analytics.latest(store, kind, policy, day)
    assert report['id'] == kind + '2'
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM events WHERE kind='parallel_writer'").fetchone()[0] == 1


def test_traceback_from_validator_does_not_keep_a_read_lock_during_error_logging(prepared, monkeypatch):
    store, policy, day = prepared
    connect = sqlite3.connect
    def bounded_connect(*args, **kwargs):
        return connect(*args, **{**kwargs, 'timeout': 2})
    monkeypatch.setattr(sqlite3, 'connect', bounded_connect)
    def invalid(*_):
        raise ValueError('模拟校验异常')
    monkeypatch.setattr(analytics, 'valid', invalid)
    with pytest.raises(ValueError, match='校验异常') as caught:
        analytics.latest(store, 'industry_report', policy, day)
    # Retain the exception and its traceback, as invoke() does while recording debug_exception.
    store.event('debug_exception', {'error': str(caught.value)})
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM events WHERE kind='debug_exception'").fetchone()[0] == 1


@pytest.mark.parametrize('change', ['config', 'dataset'])
def test_validation_still_rejects_reports_after_concurrent_inputs_change(prepared, monkeypatch, change):
    store, policy, day = prepared
    original = analytics.valid
    def config(db):
        db.execute("INSERT INTO objects VALUES ('analysis-new','analysis_config','{\"version\":1,\"config\":{\"period\":\"7\"}}','now')")
    def dataset(db):
        from plugins.operations.store import encoded
        db.execute('INSERT INTO business_datasets VALUES (?,?,?)', ('new-dataset', 1, encoded({'active': True, 'scope_topic': policy['topic']})))
    changes = {'config': config, 'dataset': dataset}
    changed = False
    with ThreadPoolExecutor(max_workers=1) as pool:
        def validate(*args):
            nonlocal changed
            if not changed:
                pool.submit(committed_write, store, changes[change]).result(timeout=5)
                changed = True
            return original(*args)
        monkeypatch.setattr(analytics, 'valid', validate)
        assert analytics.latest(store, 'industry_report', policy, day) is None
