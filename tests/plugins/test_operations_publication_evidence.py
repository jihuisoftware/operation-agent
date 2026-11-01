"""Publication facts and durable browser evidence survive restarts without duplicate sends."""
from copy import deepcopy
import json
import pytest
from plugins.operations.policy import DEFAULT
from plugins.operations.store import Store


def prepared(path):
    store = Store(path)
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='测试', goal='验证', account_id='me')
    policy['modules']['publish'] = True
    store.configure(policy, 0)
    store.manual_run_id = 'debug:test'
    action = {'kind': 'publish', 'account_id': 'me', 'target': 'draft', 'content': {'title': '测试', 'body': '正文', 'asset_ids': ['cover']}}
    identity = store.reserve_action(action, 1)
    return store, identity, store.claim('desktop')


def test_reviewing_receipt_does_not_become_published_or_completed(tmp_path):
    from plugins.operations.outcomes import describe
    store, identity, command = prepared(tmp_path / 'ledger.db')
    result = {'state': 'published', 'evidence': '标题正文匹配，但平台审核中', 'publication': {
        'execution': 'verified', 'platform': 'reviewing', 'content': 'matched'}}
    store.acknowledge(command['id'], 'desktop', result)
    row = Store(store.path).snapshot()['actions'][0]
    assert row['id'] == identity and row['state'] == 'submitted'
    assert json.loads(row['result'])['publication']['content'] == 'matched'
    assert describe('publish', result)[0] == 'needs_attention'


def test_step_journal_is_owned_idempotent_and_available_after_restart(tmp_path):
    from plugins.operations.browser_evidence import record_step, steps, baseline
    store, identity, command = prepared(tmp_path / 'ledger.db')
    event = {'sequence': 1, 'phase': 'completed', 'name': 'baseline', 'duration_ms': 20,
             'result': {'ids': ['old'], 'captured_at': '2026-11-01T00:00:00Z'},
             'url': 'https://www.xiaohongshu.com/user/profile/me?token=private', 'secret': 'not stored'}
    with pytest.raises(ValueError, match='执行者'):
        record_step(store, command['id'], 'someone', event)
    first = record_step(store, command['id'], 'desktop', event)
    assert record_step(store, command['id'], 'desktop', event) == first
    restarted = Store(store.path)
    rows = steps(restarted, identity)
    assert len(rows) == 1 and rows[0]['debug_id'] == 'debug:test'
    assert 'secret' not in rows[0] and '?' not in rows[0]['url']
    assert baseline(restarted, identity)['ids'] == ['old']
    with pytest.raises(ValueError, match='执行者'):
        record_step(Store(tmp_path / 'other.db'), command['id'], 'desktop', event)
    store.acknowledge(command['id'], 'desktop', {'state': 'unknown'})
    with pytest.raises(ValueError, match='结束'):
        record_step(store, command['id'], 'desktop', {**event, 'sequence': 2})


def test_recovery_uses_durable_baseline_and_updates_review_without_resubmission(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, UTC
    from plugins.operations.browser_evidence import record_step
    from plugins.operations.recovery import reconcile_pending
    from plugins.operations.report import daily_report
    from plugins.operations.policy import local_day
    store, identity, command = prepared(tmp_path / 'recovery.db')
    record_step(store, command['id'], 'desktop', {'sequence': 1, 'phase': 'completed', 'name': 'baseline',
        'result': {'ids': ['old'], 'account_id': 'me', 'captured_at': '2026-11-01T00:00:00Z'}})
    store.acknowledge(command['id'], 'desktop', {'state': 'unknown', 'error': '提交后断线'})
    restarted = Store(store.path)
    policy = restarted.policy()[1]
    day = local_day(policy)
    now = datetime.now(UTC)
    reconcile_pending(restarted, policy, day, now)
    first = restarted.claim('desktop')
    assert first['kind'] == 'verify' and first['payload']['baseline']['ids'] == ['old']
    result = {'state': 'published', 'evidence': '页面及图片核对', 'url': 'https://www.xiaohongshu.com/explore/new',
              'publication': {'execution': 'verified', 'platform': 'reviewing', 'content': 'matched'}}
    restarted.acknowledge(first['id'], 'desktop', result)
    assert restarted.snapshot()['actions'][0]['state'] == 'submitted'
    assert '已核对成功 0 次' in daily_report(restarted, day)['markdown']
    reconcile_pending(restarted, policy, day, now + timedelta(minutes=31))
    second = restarted.claim('desktop')
    assert second['kind'] == 'verify' and second['payload']['verification_action_id'] == identity
    result['publication']['platform'] = 'published'
    restarted.acknowledge(second['id'], 'desktop', result)
    assert restarted.snapshot()['actions'][0]['state'] == 'published'
    with restarted.connection() as db:
        assert db.execute("SELECT count(*) FROM commands WHERE kind='publish'").fetchone()[0] == 1


def test_image_verification_requires_owned_command_and_exact_authorized_bytes(tmp_path, monkeypatch):
    import hashlib
    from contextvars import ContextVar
    from plugins.operations import publication_images
    store, _, command = prepared(tmp_path / 'images.db')
    raw = b'authorized image bytes'
    digest = hashlib.sha256(raw).hexdigest()
    store.put('asset', {'authorized': True}, digest)
    with store.connection() as db:
        payload = json.loads(db.execute('SELECT payload FROM commands WHERE id=?', (command['id'],)).fetchone()[0])
        payload['content']['asset_ids'] = [digest]
        db.execute('UPDATE commands SET payload=? WHERE id=?', (json.dumps(payload), command['id']))
    profile = ContextVar('image_test_profile', default='wrong')
    token = profile.set('owned')
    downloads = []
    def download(url, **_kwargs):
        downloads.append((url, profile.get()))
        return raw
    monkeypatch.setattr(publication_images, 'download', download)
    urls = ['https://sns.xhscdn.com/cover.png']
    try:
        with pytest.raises(ValueError, match='执行者'):
            publication_images.verify_images(store, command['id'], 'other', [])
        assert publication_images.verify_images(store, command['id'], 'desktop', urls)['state'] == 'matched'
        assert downloads == [(urls[0], 'owned')]
        assert publication_images.verify_images(store, command['id'], 'desktop', ['https://127.0.0.1/private'])['state'] == 'incomplete'
        assert len(downloads) == 1
        monkeypatch.setattr(publication_images, 'download', lambda *_a, **_kw: b'transcoded')
        assert publication_images.verify_images(store, command['id'], 'desktop', urls)['state'] == 'incomplete'
        store.put('asset', {'authorized': True, 'revoked': True}, digest)
        assert publication_images.verify_images(store, command['id'], 'desktop', urls)['state'] == 'incomplete'
    finally:
        profile.reset(token)


def test_private_step_and_screenshot_api_preserves_profile_authentication(tmp_path, monkeypatch):
    import base64
    from io import BytesIO
    from PIL import Image
    from starlette.testclient import TestClient
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    from hermes_cli import web_server
    home = tmp_path / 'home'
    secondary = home / 'profiles' / 'other'
    secondary.mkdir(parents=True)
    for directory in (home, secondary):
        (directory / 'config.yaml').write_text('{}')
    monkeypatch.setenv('HERMES_HOME', str(home))
    token = set_hermes_home_override(str(home))
    try:
        _store, identity, command = prepared(None)
        raw = BytesIO()
        Image.new('RGB', (3, 3), 'white').save(raw, format='PNG')
        image = 'data:image/png;base64,' + base64.b64encode(raw.getvalue()).decode()
        body = {'command_id': command['id'], 'worker': 'desktop', 'sequence': 1,
                'phase': 'failed', 'name': 'receipt', 'error': '结果不明', 'screenshot': image}
        with TestClient(web_server.app) as client:
            path = '/api/plugins/operations'
            assert client.post(path + '/worker/steps', json=body).status_code in (401, 403)
            client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
            response = client.post(path + '/worker/steps', json=body)
            assert response.status_code == 200, response.text
            evidence_id = response.json()['evidence_id']
            assert client.post(path + '/worker/steps', json=body).json() == response.json()
            assert len(client.get(f'{path}/actions/{identity}/steps').json()['steps']) == 1
            assert client.get(f'{path}/browser-evidence/{evidence_id}').json()['image'] == image
            assert client.get(f'{path}/browser-evidence/{evidence_id}?profile=other').status_code == 404
            assert client.post(path + '/worker/steps?profile=other', json=body).status_code == 400
            assert client.get(f'{path}/actions/{identity}/steps?profile=other').status_code == 400
    finally:
        reset_hermes_home_override(token)
