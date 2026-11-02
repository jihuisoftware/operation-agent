"""Per-attempt receipts, ownership and lifecycle without live model requests."""
from types import SimpleNamespace
import pytest

from agent import token_ledger as ledger
from agent.token_tracking import run_tracked_turn, attempt
from agent.auxiliary_hooks import run_with_aux_hooks
from hermes_constants import set_hermes_home_override, reset_hermes_home_override


def response(prompt=100, output=20):
    return SimpleNamespace(model='served-model', usage=SimpleNamespace(
        prompt_tokens=prompt, completion_tokens=output,
        prompt_tokens_details=SimpleNamespace(cached_tokens=30),
        completion_tokens_details=SimpleNamespace(reasoning_tokens=5)))


def test_receipt_is_idempotent_and_does_not_add_cache_or_reasoning_twice(tmp_path):
    context = ledger.start_task('turn', path=tmp_path / 'state.db', session_id='session', turn_id='turn')
    with ledger.bind(context):
        first = ledger.Attempt(model='requested', provider='openai', purpose='chat', api_mode='chat_completions')
        first.finish(response())
        first.finish(response(900, 900))
        failed = ledger.Attempt(model='requested', purpose='compression')
        failed.finish(error=TimeoutError())
        zero = ledger.Attempt(purpose='vision')
        zero.finish(SimpleNamespace(usage={'prompt_tokens': 0, 'completion_tokens': 0}))
        unknown = ledger.Attempt(purpose='web_extract')
        unknown.finish(SimpleNamespace(usage=None))
    with ledger.connection(context['path']) as db:
        rows = {r['id']: dict(r) for r in db.execute('SELECT * FROM token_usage_calls')}
    assert rows[first.id]['total_tokens'] == 120
    assert rows[first.id]['input_tokens'] == 70
    assert rows[first.id]['cache_read_tokens'] == 30
    assert rows[first.id]['reasoning_tokens'] == 5
    assert rows[first.id]['model'] == 'served-model'
    assert rows[failed.id]['total_tokens'] is None
    assert rows[failed.id]['state'] == 'failed'
    assert rows[zero.id]['total_tokens'] == 0 and rows[zero.id]['state'] == 'confirmed'
    assert rows[unknown.id]['total_tokens'] is None and rows[unknown.id]['state'] == 'unknown'


def test_real_aux_boundary_and_main_turn_share_parent_without_double_count(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    agent = SimpleNamespace(session_id='session', _relay_pending_turn_id='turn')
    def turn(agent):
        with attempt(model='main', purpose='chat') as receipt:
            receipt.response = response()
        run_with_aux_hooks(lambda: response(50, 10), aux_task='compression', metadata={},
                           client=SimpleNamespace(), kwargs={}, provider='openai', model='aux', api_mode='chat_completions')
        return {'interrupted': False}
    run_tracked_turn(turn, agent)
    with ledger.connection() as db:
        task = dict(db.execute('SELECT * FROM token_usage_tasks').fetchone())
        assert db.execute('SELECT SUM(total_tokens),count(*) FROM token_usage_calls').fetchone()[:] == (180, 2)
    assert task['session_id'] == 'session' and task['turn_id'] == 'turn'
    assert task['state'] == 'completed'
    assert ledger.CONTEXT.get() is None


def test_profile_is_captured_at_start_and_late_receipt_cannot_move(tmp_path):
    one, two = tmp_path / 'one', tmp_path / 'two'
    token = set_hermes_home_override(one)
    try:
        record = ledger.Attempt(purpose='vision')
        switched = set_hermes_home_override(two)
        try:
            record.finish(response())
            with ledger.connection() as db:
                assert db.execute('SELECT count(*) FROM token_usage_calls').fetchone()[0] == 0
        finally:
            reset_hermes_home_override(switched)
        with ledger.connection() as db:
            assert db.execute('SELECT total_tokens FROM token_usage_calls').fetchone()[0] == 120
    finally:
        reset_hermes_home_override(token)


def test_interruption_and_dead_process_preserve_known_receipts(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    context = ledger.start_task('task')
    with ledger.bind(context):
        known = ledger.Attempt()
        known.finish(response())
        pending = ledger.Attempt()
    with ledger.connection() as db:
        db.execute('UPDATE token_usage_tasks SET process_started=0')
        ledger.recover(db)
        assert db.execute('SELECT state FROM token_usage_tasks').fetchone()[0] == 'interrupted'
        assert db.execute('SELECT total_tokens FROM token_usage_calls WHERE id=?', (known.id,)).fetchone()[0] == 120
        assert db.execute('SELECT state,total_tokens FROM token_usage_calls WHERE id=?', (pending.id,)).fetchone()[:] == ('interrupted', None)


def test_stream_receipt_is_only_finalized_after_consumption(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    stream = run_with_aux_hooks(lambda: iter([SimpleNamespace(usage=None), response()]),
                               aux_task='vision', metadata={}, client=SimpleNamespace(), kwargs={},
                               provider='openai', model='aux', api_mode='chat_completions', streaming=True)
    with ledger.connection() as db:
        assert db.execute('SELECT state FROM token_usage_calls').fetchone()[0] == 'running'
    assert len(list(stream)) == 2
    with ledger.connection() as db:
        assert db.execute('SELECT total_tokens,state FROM token_usage_calls').fetchone()[:] == (120, 'confirmed')


def test_existing_ledger_is_migrated_and_recovery_is_throttled(tmp_path):
    import sqlite3

    path = tmp_path / 'state.db'
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE token_usage_meta(id INTEGER PRIMARY KEY CHECK(id=1), since REAL NOT NULL)')
    db.execute('INSERT INTO token_usage_meta VALUES(1, 10)')
    db.commit(); db.close()

    with ledger.connection(path) as db:
        meta = dict(db.execute('SELECT * FROM token_usage_meta').fetchone())
        assert meta['schema_version'] == ledger.TOKEN_USAGE_SCHEMA_VERSION
        assert db.execute("SELECT name FROM sqlite_master WHERE name='token_usage_model'").fetchone()
        assert ledger.recover_if_due(db, now=100, interval=30)
        assert not ledger.recover_if_due(db, now=110, interval=30)
