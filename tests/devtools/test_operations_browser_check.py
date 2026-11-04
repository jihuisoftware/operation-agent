"""The real-window diagnostic route has only a read-only command path."""
from copy import deepcopy

from plugins.operations.policy import DEFAULT
from plugins.operations.store import Store


def test_browser_check_never_generates_or_submits(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text('development:\n  operations_debug: true\n')
    store = Store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='只读核对', goal='检查网页', account_id='me')
    policy['modules']['comments'] = True
    store.configure(policy, 0)
    calls = []
    def browser(_store, kind, payload):
        calls.append((kind, payload))
        return {'state': 'logged_in', 'account_id': 'me', 'items': [{'id': 'note'}], 'probe': 'account_and_search'}
    monkeypatch.setattr('plugins.operations.workflow.browser', browser)
    from devtools.operations_browser_check import check
    result = check({'request_id': 'read-only', 'version': 1})
    assert result['submitted'] is False and result['items'] == 1
    assert len(calls) == 1 and calls[0][0] == 'account'
    assert calls[0][1]['resume_probe'] is True
    assert calls[0][1]['readonly_inventory'] == 'comment'
    assert not store.snapshot()['actions']
    assert not store.objects('debug_action_grant')


def test_failed_account_diagnostic_does_not_confirm_login_from_a_partial_identity(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='只读诊断', goal='保留真实状态')
    policy['modules']['comments'] = True
    store.configure(policy, 0)
    command = store.enqueue('account', {})
    assert store.claim('desktop')['id'] == command
    observations = []
    monkeypatch.setattr('plugins.operations.workspace_execution.observe_account', lambda *args: observations.append(args))
    store.acknowledge(command, 'desktop', {'state': 'blocked', 'account_id': 'me', 'error': '候选读取失败',
                                         'error_code': 'BROWSER_UNAVAILABLE', 'submitted': False, 'dispatch_state': 'read_only'})
    assert observations == []
