"""Magazine output preserves provenance, paid-call limits and interrupted work."""
from copy import deepcopy
from io import BytesIO

import pytest
from PIL import Image

from plugins.operations import visual_jobs, visual_plan, visual_provider, visual_sets
from plugins.operations.policy import DEFAULT
from plugins.operations.store import Store, encoded


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='Agent 开发', goal='分享可复现方法')
    policy['modules']['content'] = True
    store.configure(policy, 0)
    pages = [
        {'kind': 'cover', 'title': '把 Agent 做成可靠工具', 'intro': '先明确边界，再验证执行结果', 'items': [{'label': '输入', 'text': ''}, {'label': '执行', 'text': ''}], 'art': 'A precise blue modular machine on ivory paper'},
        {'kind': 'steps', 'title': '先把任务拆清楚', 'intro': '从小范围可核对的动作开始', 'items': [{'label': '明确输入', 'text': '写下任务所需的信息与限制。'}, {'label': '核对结果', 'text': '保留执行记录，失败后核对再继续。'}], 'art': ''},
        {'kind': 'story', 'title': '让结果可以被验证', 'intro': '完成动作只是第一步', 'items': [{'label': '反馈', 'text': '将实际结果与预期逐项比较。'}], 'art': 'An orange magnifying glass over a blue geometric mechanism'},
    ]
    content = {'title': '把Agent做成可靠工具', 'body': '明确输入、限制和任务边界。保留执行记录，核对实际结果与预期。', 'source_ids': [], 'asset_ids': [], 'visual_plan': {'pages': pages}}
    content['id'] = store.put('content', content, 'draft')
    raw = BytesIO()
    Image.new('RGB', (1200, 800), '#b3c7f7').save(raw, format='PNG')
    calls = []
    monkeypatch.setattr(visual_provider, 'selection', lambda: {'provider': 'test', 'model': 'test-image'})
    monkeypatch.setattr(visual_provider, 'available', lambda: True)
    monkeypatch.setattr(visual_provider, 'generate', lambda prompt: calls.append(prompt) or {'image': 'fixture', 'success': True})
    monkeypatch.setattr(visual_provider, 'image_bytes', lambda _: raw.getvalue())
    from plugins.operations import visual_review
    monkeypatch.setattr(visual_review, 'inspect', lambda *_: {'pass': True, 'reason': '模拟视觉检查', 'issues': []})
    return store, content, calls


def test_set_composes_all_pages_and_reuses_paid_art(studio):
    store, content, calls = studio
    first = visual_jobs.automatic(store, content)
    assert len(first['asset_ids']) == 3 and len(calls) == 2
    for identity in first['asset_ids']:
        assert Image.open(BytesIO(visual_sets.asset_bytes(store, identity))).size == (1080, 1440)
    again = visual_jobs.automatic(store, content)
    assert again['asset_ids'] == first['asset_ids'] and len(calls) == 2
    assert not store.objects('content_release')
    row = next(row for row in store.objects('asset') if row['id'] == first['asset_ids'][1])
    assert row['visual_page']['items'][0]['text'] == '写下任务所需的信息与限制。'


def test_failed_second_art_only_retries_missing_work_and_never_exceeds_three_calls(studio, monkeypatch):
    store, content, calls = studio
    def generate(prompt):
        calls.append(prompt)
        if len(calls) > 1:
            raise ValueError('provider timeout')
        return {'image': 'fixture', 'success': True}
    monkeypatch.setattr(visual_provider, 'generate', generate)
    first = visual_jobs.automatic(store, content)
    assert first['visual_error'] and len(calls) == 2
    record = visual_sets.read(store, first['visual_set_id'])
    assert len(record['pages']) == 2
    visual_jobs.automatic(store, content)
    assert len(calls) == 2  # Scheduled reruns must not resend an uncertain paid request.
    from plugins.operations.content_release import fingerprint
    monkeypatch.setattr(visual_jobs._POOL, 'submit', lambda run, *args: run(*args))
    body = {'kind': 'content', 'id': content['id'], 'content_revision': fingerprint(content), 'retry': True}
    visual_jobs.start(store, {**body, 'request_id': 'retry-one'})
    assert len(calls) == 3
    visual_jobs.start(store, {**body, 'request_id': 'retry-two'})
    assert len(calls) == 3


def test_cancelled_late_result_cannot_attach_or_dispatch_another_image(studio, monkeypatch):
    store, content, calls = studio
    identity = visual_sets.create(store, content, {'kind': 'content', 'id': content['id']})['id']
    def generate(prompt):
        calls.append(prompt)
        visual_jobs.cancel(Store(store.path, workspace=store.workspace, scope=store.scope), identity)
        return {'image': 'fixture', 'success': True}
    monkeypatch.setattr(visual_provider, 'generate', generate)
    result = visual_jobs.automatic(store, content)
    assert result['visual_error'] and len(calls) == 1
    record = visual_sets.read(store, identity)
    assert record['state'] == 'cancelled' and not record['pages'] and not record['art']


def test_changed_manuscript_rejects_applying_old_visual_set(studio):
    store, content, _ = studio
    result = visual_jobs.automatic(store, content)
    with store.connection() as db:
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded({**content, 'body': '内容已经修改'}), content['id']))
    with pytest.raises(ValueError, match='稿件已变化'):
        visual_jobs.apply(store, result['visual_set_id'], {})


def test_missing_provider_keeps_draft_without_silent_basic_cover(studio, monkeypatch):
    store, content, calls = studio
    monkeypatch.setattr(visual_provider, 'available', lambda: False)
    result = visual_jobs.automatic(store, content)
    assert '配置' in result['visual_error'] and result['asset_ids'] == [] and not calls


def test_storyboard_rejects_overflow_instead_of_truncating():
    with pytest.raises(ValueError):
        visual_plan.validate({'pages': [{'title': '长标题' * 20}, {'title': '第二页', 'intro': '内容'}]})


def test_restart_and_request_replay_do_not_dispatch_again(studio, monkeypatch):
    from plugins.operations import visual_job_state
    from plugins.operations.content_release import fingerprint
    store, content, calls = studio
    pending = []
    monkeypatch.setattr(visual_jobs._POOL, 'submit', lambda *args: pending.append(args))
    body = {'kind': 'content', 'id': content['id'], 'content_revision': fingerprint(content), 'request_id': 'same-request'}
    first = visual_jobs.start(store, body)
    assert visual_jobs.start(store, body)['id'] == first['id'] and len(pending) == 1
    with pytest.raises(ValueError, match='同一组图请求'):
        visual_jobs.start(store, {**body, 'retry': True})
    monkeypatch.setattr(visual_job_state, 'SESSION', 'new-process')
    resumed = visual_job_state.status(store, first['id'])
    assert resumed['state'] == 'needs_attention' and not calls
    assert visual_jobs.start(store, body)['state'] == 'needs_attention' and len(pending) == 1
    visual_jobs.start(store, {**body, 'request_id': 'manual-resume', 'retry': True})
    assert len(pending) == 2


def test_auto_pipeline_uses_magazine_by_default_and_checks_all_page_copy(studio, monkeypatch):
    from plugins.operations import content as pipeline, topics, visual_review
    from plugins.operations.policy import local_day
    from tests.plugins.operations_support import prepare_materials
    store, sample, calls = studio
    version, policy = store.policy()
    day = local_day(policy)
    store.put('source', {'text': sample['body'], 'title': '可核对的开发方法', 'state': 'read', 'day': day, 'scope_topic': policy['topic'], 'url': 'https://example.org/guide'}, 'source')
    prepare_materials(store, policy, day, monkeypatch)
    monkeypatch.setattr(topics, 'production_topic', lambda *_: {'title': sample['title'], 'source_ids': ['source']})
    supplied = []
    def generate(*args):
        if '返回 {"pass"' in args[-2]:
            supplied.extend(args[-1]['assets'])
            return {'pass': True, 'reason': '文案符合来源', 'issues': []}
        return {**sample, 'source_ids': ['source']}
    monkeypatch.setattr(pipeline, 'generate', generate)
    result = pipeline.produce_content(store, policy, day, version)
    assert result['ready'] and len(calls) == 2
    assert supplied and all(asset.get('visual_page') for asset in supplied)
    saved = next(row for row in store.objects('content') if row['id'] == result['content_id'])
    assert saved['visual_required'] and len(saved['asset_ids']) == 3
    assert pipeline.produce_content(store, policy, day, version)['content_id'] == saved['id']
    assert len(calls) == 2


def test_provider_usage_is_scoped_and_reported_even_outside_chat(studio, monkeypatch):
    from plugins.image_gen._common import record_token_usage
    from plugins.operations.run_scope import ReportScope
    from plugins.operations.report_summary import consumption
    from plugins.operations.policy import local_day
    store, content, _ = studio
    def generate(_):
        record_token_usage({'input_tokens': 100, 'output_tokens': 200, 'total_tokens': 300}, model='test-image', provider='openai')
        return {'success': True, 'image': 'fixture'}
    monkeypatch.setattr(visual_provider, 'generate', generate)
    result = visual_jobs.automatic(store, content)
    assert not result['visual_error']
    scope = ReportScope(store, local_day(store.policy()[1]))
    from plugins.operations.run_scope import call_count
    assert call_count(scope.events) == 2
    lines = consumption(scope)
    assert any('图片生成' in line and '600' in line for line in lines)


def test_background_work_binds_owning_profile_after_request_returns(studio, monkeypatch, tmp_path):
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override, get_hermes_home
    from plugins.operations.content_release import fingerprint
    store, content, _ = studio
    pending, seen = [], []
    monkeypatch.setattr(visual_jobs._POOL, 'submit', lambda *args: pending.append(args))
    monkeypatch.setattr(visual_provider, 'generate', lambda _: seen.append(get_hermes_home()) or {'image': 'fixture', 'success': True})
    owner = get_hermes_home()
    visual_jobs.start(store, {'kind': 'content', 'id': content['id'], 'content_revision': fingerprint(content), 'request_id': 'profile-bound'})
    token = set_hermes_home_override(tmp_path / 'unrelated-profile')
    try:
        run, *args = pending[0]
        run(*args)
    finally:
        reset_hermes_home_override(token)
    assert seen == [owner, owner]


def test_private_visual_endpoints_require_auth_and_scope(studio):
    from starlette.testclient import TestClient
    from hermes_cli import web_server
    store, content, _ = studio
    result = visual_jobs.automatic(store, content)
    path = '/api/plugins/operations/visual-sets/' + result['visual_set_id']
    scope = {'business_id': store.scope['business_id'], 'topic_id': store.scope['id']}
    with TestClient(web_server.app) as client:
        assert client.get(path, params=scope).status_code == 401
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        response = client.get(path, params=scope)
        assert response.status_code == 200 and len(response.json()['pages']) == 3
        assert 'plan' not in response.json()
        assert client.get(path, params={**scope, 'topic_id': 'other'}).status_code == 404
