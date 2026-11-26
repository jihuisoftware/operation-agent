"""Cover ownership on an unconfigured or missing external provider."""
import pytest

from plugins.operations import template_fallback
from plugins.operations.content_release import fingerprint
from plugins.operations.designer_apply import fill_missing
from plugins.operations.store import Store
from tests.plugins.operations_support import install_test_designer


def test_missing_plugin_can_fill_existing_draft_after_enablement(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    draft = {'title': '原创文章', 'body': '已保存的正文', 'source_ids': [], 'asset_ids': [],
             'authorship': {'kind': 'human_original', 'declared': True, 'draft_id': 'original'}}
    identity = store.put('content', draft)
    body = {'version': 0, 'content_revision': fingerprint(draft), 'expected_release_revision': 0}
    with pytest.raises(ValueError, match='插件'):
        fill_missing(store, identity, body)
    assert not store.objects('designer_cover_job') and not store.objects('content_release')
    install_test_designer(monkeypatch)
    monkeypatch.setattr(template_fallback, 'no_image_model', lambda: True)
    assert fill_missing(store, identity, body)['id'] == identity
    saved, = store.objects('content')
    assert saved['body'] == draft['body'] and len(saved['asset_ids']) == 1
    assert not store.objects('content_release')


def test_new_reviewer_accepts_nested_scores_and_sees_actual_single_image(tmp_path, monkeypatch):
    import base64
    from io import BytesIO
    from PIL import Image
    from plugins.operations import model, visual_review, review_scores
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    raw = BytesIO()
    Image.new('RGB', (1080, 1440), 'navy').save(raw, format='PNG')
    asset = store.add_asset('Manus.png', raw.getvalue(), True)

    def evaluate(*args, image_parts, **kwargs):
        data = image_parts[0]['image_url']['url'].split(',', 1)[1]
        with Image.open(BytesIO(base64.b64decode(data))) as im:
            assert im.size == (1080, 1440)
        return {'pass': True, 'issues': [], 'scores': {key: {'score': 85, 'basis': '可读'} for key in review_scores.VISUAL}}

    monkeypatch.setattr(model, 'generate', evaluate)
    result = visual_review.inspect(store, {'pages': [{'asset_id': asset}], 'plan': {'pages': []}})
    assert result['pass'] and review_scores.score(result, 'visual') == 85
