"""Automatic production may downgrade an unstarted image job, never an uncertain one."""
import pytest

from plugins.operations import content, content_recovery, visual_provider
from plugins.operations.content_release import manuscript as read_content
from plugins.operations.store import encoded
from tests.plugins import test_operations_content_review as support


_manuscript = support.manuscript
MISSING = '尚未配置可用的生图模型，请在模型能力设置中配置；文字草稿已保留'


@pytest.mark.parametrize('mode, legacy', [('magazine', True), ('magazine', False), ('designer', False)])
def test_automatic_review_uses_template_on_missing_image_model(_manuscript, monkeypatch, mode, legacy):
    store, policy, day, draft = _manuscript
    version = store.configure({**policy, 'image_mode': mode}, 1)
    policy = store.policy()[1]
    draft.update(version=version, ready=False, review_pending=True, visual_required=mode == 'magazine',
                 designer_required=mode == 'designer')
    if legacy:
        from plugins.operations import visual_sets
        job = visual_sets.create(store, draft, {'kind': 'content', 'id': draft['id']})
        job.update(state='needs_attention', detail=MISSING)
        visual_sets.save(store, job)
        draft.update(visual_set_id=job['id'], visual_error=MISSING)
    else:
        draft['asset_ids'] = []
    with store.connection() as db:
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(draft), draft['id']))
    monkeypatch.setattr(visual_provider, 'available', lambda: False)
    monkeypatch.setattr(visual_provider, 'generate', lambda *a, **kw: pytest.fail('意外调用生图服务'))
    checked = []
    def check(_store, _policy, _day, _version, candidate, _sources):
        checked.append(candidate['asset_ids'][0])
        return {'pass': True, 'reason': '文字检查通过'}
    monkeypatch.setattr(content, 'check_content', check)
    result = content_recovery.review(store, policy, day, version, draft, store.objects('source'))
    saved = read_content(store, draft['id'])
    assert result['ready'] and '模板封面' in result['reason']
    assert checked == saved['asset_ids'] and saved['cover_origin'] == 'generated_typography'
    if legacy:
        assert saved['asset_ids'] == draft['asset_ids']
        assert visual_sets.read(store, job['id'])['state'] == 'needs_attention'
    assert not saved['visual_required'] and not saved.get('designer_required')
    assert not saved.get('visual_error') and not saved.get('visual_review')
    assert not store.objects('content_release')


@pytest.mark.parametrize('block', ['configured', 'uncertain', 'cancelled'])
def test_template_does_not_mask_configured_provider_or_inflight_work(_manuscript, monkeypatch, block):
    from plugins.operations import template_fallback, visual_sets
    store, policy, _, draft = _manuscript
    version = store.configure({**policy, 'image_mode': 'magazine'}, 1)
    policy = store.policy()[1]
    draft.update(visual_required=True, version=version)
    with store.connection() as db:
        db.execute('UPDATE objects SET data=? WHERE id=?', (encoded(draft), draft['id']))
    monkeypatch.setattr(visual_provider, 'available', lambda: False)
    if block == 'configured':
        monkeypatch.setattr('hermes_cli.config.load_config_readonly', lambda: {'image_gen': {'model': 'chosen'}})
    else:
        job = visual_sets.create(store, draft, {'kind': 'content', 'id': draft['id']})
        job.update(state='needs_attention', detail=MISSING)
        if block == 'uncertain':
            job['attempts'] = [{'state': 'unknown'}]
        else:
            job['cancelled'] = True
        visual_sets.save(store, job)
    kept = template_fallback.apply_if_needed(store, draft, policy, version)
    assert kept['visual_required'] and not read_content(store, draft['id']).get('template_fallback')
