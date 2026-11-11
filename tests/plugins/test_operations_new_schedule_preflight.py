"""An independent scheduled publication rechecks a stale account block, not its old batch."""
from datetime import UTC, datetime, timedelta

from plugins.operations import execution_pause, publication_plan, workflow
from plugins.operations.policy import local_day
from tests.plugins import test_operations_content_review as support

manuscript = support.manuscript


def test_new_scheduled_post_probes_account_and_leaves_old_batch_paused(manuscript, monkeypatch):
    store, policy, _, draft = manuscript
    old_run = store.start_run(local_day(policy), 'publish', 'old-failed-post', 1)
    old = execution_pause.pause(store, {'error_code': 'BROWSER_UNAVAILABLE', 'error': '旧网页中断', 'submitted': False})
    store.finish_run(old_run, 'paused', '旧网页中断')
    due, _, _ = support.approve(store, draft)
    store.claim('desktop', busy=True)
    seen = []
    original = workflow.browser
    def browser(owner, kind, payload, action_id=None):
        seen.append(kind)
        if kind == 'account':
            assert payload['resume_probe']
            return {'state': 'logged_in', 'account_id': 'me'}
        return original(owner, kind, payload, action_id)
    calls = support.desktop(store, monkeypatch)
    monkeypatch.setattr(workflow, 'browser', browser)
    store.execution_now = due + timedelta(seconds=1)
    assert publication_plan.publish_due(store, store.execution_now)
    assert seen == ['account', 'publish'] and len(calls) == 1
    assert execution_pause.load(store, old['id'])['state'] == 'paused'
    assert execution_pause.block(store) is None
    assert not publication_plan.publish_due(store, datetime.now(UTC) + timedelta(hours=1))


def test_account_history_does_not_stop_independent_analysis_but_own_pause_still_does(manuscript):
    import pytest
    store, policy, _, _ = manuscript
    old_run = store.start_run(local_day(policy), 'publish', 'failed-web', 1)
    execution_pause.pause(store, {'error_code': 'BROWSER_UNAVAILABLE', 'error': '旧网页中断'})
    store.finish_run(old_run, 'paused', '旧网页中断')
    store.start_run(local_day(policy), 'analytics', 'independent', 1)
    store.account_required = True
    execution_pause.guard(store)
    assert execution_pause.block(store)
    store.current_run_id = old_run
    with pytest.raises(execution_pause.ExecutionPaused):
        execution_pause.guard(store)
