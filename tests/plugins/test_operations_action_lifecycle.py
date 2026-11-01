"""Operator evidence, independent review deadlines, snapshots and retention contracts."""
from copy import deepcopy
from datetime import datetime, timedelta, UTC
from io import BytesIO
import json
import time
from PIL import Image
import pytest
from plugins.operations.store import Store, encoded
from plugins.operations.policy import DEFAULT
from plugins.operations import service
from plugins.operations.recovery import reconcile_pending
from plugins.operations.review_queue import request_check, load


def setup_store(tmp_path):
    store = Store(tmp_path / 'operations.db')
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='测试', goal='闭环核对', account_id='me')
    policy['modules']['publish'] = True
    policy['limits']['publish'] = 10
    store.configure(policy, 0)
    return store, policy


def submit(store, target='draft'):
    action = {'kind': 'publish', 'account_id': 'me', 'target': target,
              'content': {'title': '固定标题', 'body': '固定正文', 'asset_ids': [], 'source_ids': []}}
    identity = store.reserve_action(action, 1)
    command = store.claim('desktop')
    result = {'state': 'submitted', 'url': 'https://www.xiaohongshu.com/explore/new', 'evidence': '平台接收回执',
              'publication': {'execution': 'submitted', 'platform': 'unknown', 'content': 'unknown'}}
    store.acknowledge(command['id'], 'desktop', result)
    return identity, command, result


def test_manual_conclusion_preserves_evidence_and_wins_over_inflight_review(tmp_path):
    from plugins.operations.publication_status import complete
    from plugins.operations.action_details import detail
    store, _ = setup_store(tmp_path)
    identity, _, receipt = submit(store)
    verify = store.claim('desktop')
    service.resolve_action(store, identity, 'published', '人工看到作者、图文和已发布状态')
    store.acknowledge(verify['id'], 'desktop', {'state': 'unknown', 'error': '迟到的网页失败'})
    row = store.snapshot()['actions'][0]
    result = json.loads(row['result'])
    assert row['state'] == 'published' and complete(row)
    assert result['url'] == receipt['url'] and result['publication'] == receipt['publication']
    assert result['manual_verification']['evidence'] == '人工看到作者、图文和已发布状态'
    history = detail(store, identity)['manual_history']
    assert len(history) == 1 and history[0]['previous_result'] == receipt
    assert detail(store, identity)['tracking']['state'] == 'manual'


def test_receipt_is_atomic_with_independent_queue_and_duplicate_checks_are_idempotent(tmp_path):
    store, _ = setup_store(tmp_path)
    identity, command, receipt = submit(store)
    store.acknowledge(command['id'], 'desktop', receipt)
    first = request_check(Store(store.path), identity)['command_id']
    assert request_check(Store(store.path), identity)['command_id'] == first
    with store.connection() as db:
        db.execute('UPDATE commands SET expires=? WHERE id=?', (time.time() - 1, command['id']))
        queued = db.execute('SELECT * FROM commands WHERE id=?', (first,)).fetchone()
        assert queued['expires'] > time.time() and queued['kind'] == 'verify'
        assert db.execute("SELECT count(*) FROM commands WHERE kind='publish'").fetchone()[0] == 1
    assert Store(store.path).snapshot()['actions'][0]['state'] == 'submitted'
    assert store.claim('desktop')['id'] == first


def test_reviewing_continues_beyond_three_checks_and_rejection_stops_with_notice(tmp_path):
    store, policy = setup_store(tmp_path)
    identity, _, _ = submit(store)
    now = datetime.now(UTC)
    for attempt in range(5):
        command = store.claim('desktop')
        assert command and command['kind'] == 'verify'
        store.acknowledge(command['id'], 'desktop', {'state': 'submitted', 'evidence': '审核中',
            'publication': {'execution': 'verified', 'platform': 'reviewing', 'content': 'matched'}})
        with store.connection() as db:
            tracking = load(db, identity)
        assert tracking['state'] == 'active' and tracking['attempts'] == attempt + 1
        reconcile_pending(store, policy, '2026-11-01', now + timedelta(hours=attempt + 2))
    command = store.claim('desktop')
    store.acknowledge(command['id'], 'desktop', {'state': 'submitted', 'evidence': '审核未通过',
        'publication': {'execution': 'verified', 'platform': 'rejected', 'content': 'matched'}})
    reconcile_pending(store, policy, '2026-11-01', now + timedelta(days=1))
    assert store.claim('desktop') is None
    with store.connection() as db:
        assert load(db, identity)['state'] == 'needs_attention'
        notices = db.execute("SELECT data FROM events WHERE kind='publication_notice'").fetchall()
        assert len(notices) == 1 and json.loads(notices[0][0])['platform'] == 'rejected'


def test_final_snapshot_survives_source_and_policy_edits(tmp_path):
    from plugins.operations.publication_snapshot import read, image
    store, policy = setup_store(tmp_path)
    raw = BytesIO()
    Image.new('RGB', (4, 4), 'white').save(raw, format='PNG')
    asset = store.add_asset('original.png', raw.getvalue(), True)
    store.put('source', {'title': '最初来源', 'url': 'https://example.org/source'}, 'source')
    content = {'title': '固定标题', 'body': '固定正文', 'asset_ids': [asset], 'source_ids': ['source']}
    identity = store.reserve_action({'kind': 'publish', 'account_id': 'me', 'target': 'draft', 'content': content}, 1)
    store.put('source', {'title': '后来来源', 'url': 'https://example.org/new'}, 'source')
    policy['topic'] = '后来主题'
    store.configure(policy, 1)
    snapshot = read(Store(store.path), identity)
    assert snapshot['content'] == content and snapshot['sources'][0]['title'] == '最初来源'
    assert snapshot['policy_version'] == 1 and snapshot['policy']['topic'] == '测试'
    assert image(store, identity, asset)['name'] == 'original.png'
    with pytest.raises(ValueError, match='不属于'):
        image(store, identity, 'unrelated')


def test_visual_similarity_is_reference_only_even_for_same_pixels(tmp_path, monkeypatch):
    from plugins.operations.publication_images import verify_images
    from plugins.operations import publication_images
    from plugins.operations.image_comparison import compare
    store, _ = setup_store(tmp_path)
    original, other = BytesIO(), BytesIO()
    picture = Image.new('RGB', (16, 16), 'white')
    picture.save(original, format='PNG', compress_level=0)
    picture.save(other, format='PNG', compress_level=9)
    asset = store.add_asset('cover.png', original.getvalue(), True)
    store.reserve_action({'kind': 'publish', 'account_id': 'me', 'target': 'draft', 'content': {'title': '图', 'body': '文', 'asset_ids': [asset]}}, 1)
    command = store.claim('desktop')
    monkeypatch.setattr(publication_images, 'download', lambda *_args, **_kw: other.getvalue())
    result = verify_images(store, command['id'], 'desktop', ['https://sns.xhscdn.com/cover.png'])
    assert result['state'] == 'incomplete'
    reference = result['comparisons'][0]
    assert reference['pixels_equal'] and reference['similarity'] == 1 and reference['reference_only']
    dark = BytesIO()
    Image.new('RGB', (16, 16), 'black').save(dark, format='PNG')
    assert compare(original.getvalue(), dark.getvalue())['similarity'] == 0


def test_retention_preserves_unresolved_and_exports_local_diagnostic(tmp_path):
    import base64
    from zipfile import ZipFile
    from plugins.operations.browser_evidence import record_step, steps
    from plugins.operations.evidence_storage import cleanup, configure, diagnostic
    store, _ = setup_store(tmp_path)
    identity = store.reserve_action({'kind': 'publish', 'account_id': 'me', 'target': 'draft', 'content': {'title': '测试', 'body': '正文'}}, 1)
    command = store.claim('desktop')
    record_step(store, command['id'], 'desktop', {'sequence': 1, 'name': 'submit', 'phase': 'failed', 'error': '提交断线'})
    store.acknowledge(command['id'], 'desktop', {'state': 'unknown', 'error': '提交断线'})
    with store.connection() as db:
        db.execute("UPDATE events SET at='2025-01-01T00:00:00+00:00' WHERE kind='browser_step'")
    configure(store, {'days': 7, 'automatic': True})
    assert cleanup(store)['steps_deleted'] == 0
    package = diagnostic(store, identity)
    with ZipFile(BytesIO(base64.b64decode(package['data']))) as archive:
        exported = json.loads(archive.read('diagnostic.json'))
        assert exported['action']['id'] == identity and len(exported['steps']) == 1
    service.resolve_action(store, identity, 'confirmed_not_published', '人工确认无新增笔记')
    assert cleanup(store)['steps_deleted'] == 1
    assert steps(store, identity) == []
    assert store.objects('publication_snapshot') and store.objects('manual_conclusion')


def test_private_management_routes_are_authenticated_and_profile_local(tmp_path, monkeypatch):
    from pathlib import Path
    from starlette.testclient import TestClient
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    from hermes_cli import web_server
    home = tmp_path / 'home'
    other = home / 'profiles' / 'other'
    other.mkdir(parents=True)
    for directory in (home, other):
        (directory / 'config.yaml').write_text('{}')
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setenv('HERMES_HOME', str(home))
    token = set_hermes_home_override(str(home))
    try:
        store = Store()
        policy = deepcopy(DEFAULT)
        policy.update(enabled=True, topic='测试', goal='核对', account_id='me')
        policy['modules']['publish'] = True
        store.configure(policy, 0)
        identity, _, _ = submit(store)
        with TestClient(web_server.app) as client:
            path = '/api/plugins/operations'
            for route in (f'/actions/{identity}/detail', f'/actions/{identity}/diagnostic', '/evidence-storage'):
                assert client.get(path + route).status_code in (401, 403)
            client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
            detail = client.get(f'{path}/actions/{identity}/detail')
            assert detail.status_code == 200, detail.text
            assert detail.json()['snapshot']['content']['title'] == '固定标题'
            command = client.post(f'{path}/actions/{identity}/check').json()['command_id']
            assert client.post(f'{path}/actions/{identity}/check').json()['command_id'] == command
            assert client.get(f'{path}/actions/{identity}/detail?profile=other').status_code == 400
            assert client.post(f'{path}/actions/{identity}/check?profile=other').status_code == 400
            assert client.get(f'{path}/actions/{identity}/diagnostic?profile=other').status_code == 400
            assert client.put(path + '/evidence-storage', json={'days': 7, 'automatic': True}).status_code == 200
            assert client.get(path + '/evidence-storage?profile=other').json()['settings'] == {'days': 30, 'automatic': False}
            assert client.get(f'{path}/actions/{identity}/diagnostic').status_code == 200
    finally:
        reset_hermes_home_override(token)


def test_late_publish_receipt_is_recorded_but_never_overrides_a_new_attempt(tmp_path):
    from plugins.operations.browser_evidence import record_step, steps
    store, _ = setup_store(tmp_path)
    identity = store.reserve_action({'kind': 'publish', 'account_id': 'me', 'target': 'draft', 'content': {'title': '图', 'body': '文'}}, 1)
    command = store.claim('desktop')
    event = {'sequence': 1, 'name': 'receipt', 'phase': 'started'}
    record_step(store, command['id'], 'desktop', event)
    with store.connection() as db:
        db.execute('UPDATE commands SET expires=? WHERE id=?', (time.time() - 1, command['id']))
    assert store.command(command['id'])['state'] == 'unknown'
    record_step(store, command['id'], 'desktop', {**event, 'phase': 'completed', 'result': {'state': 'submitted'}})
    store.acknowledge(command['id'], 'desktop', {'state': 'submitted', 'evidence': '迟到的平台回执'})
    store.acknowledge(command['id'], 'desktop', {'state': 'submitted', 'evidence': '迟到的平台回执'})
    assert json.loads(store.snapshot()['actions'][0]['result'])['late_receipt'] is True
    assert steps(store, identity)[-1]['late_evidence'] is True
    assert store.claim('desktop')['kind'] == 'verify'
    with pytest.raises(ValueError, match='结束'):
        record_step(store, command['id'], 'desktop', {**event, 'sequence': 2})
    service.resolve_action(store, identity, 'confirmed_not_published', '人工确认仅草稿')
    with pytest.raises(ValueError, match='过期|匹配'):
        store.acknowledge(command['id'], 'desktop', {'state': 'published', 'evidence': '另一条旧回执'})


def test_concurrent_manual_checks_share_one_readonly_command(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    store, _ = setup_store(tmp_path)
    identity, _, _ = submit(store)
    def check(_):
        return request_check(Store(store.path), identity)['command_id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(check, range(2)))
    assert ids[0] == ids[1]
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM commands WHERE kind='verify'").fetchone()[0] == 1
