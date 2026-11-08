"""Local cover candidates are reproducible, bounded, and preserve publication authority."""
from io import BytesIO

from PIL import Image
import pytest

from plugins.operations.cover_design import normalized, TEMPLATES
from plugins.operations.cover_renderer import render
from plugins.operations.content_cover import ensure_cover
from plugins.operations.store import Store
from tests.plugins import test_operations_content_review as support

cover_manuscript = support.manuscript


@pytest.mark.parametrize('template', list(TEMPLATES))
def test_layout_keeps_tool_names_and_chinese_phrases_intact_and_inside_canvas(template):
    from hermes_platform.fonts import chinese_font
    spec = normalized({'title': 'CodeGraph降本数据待核实', 'subtitle': '资料整理，结论待核实',
                       'keywords': ['预索引', '数据边界', '使用建议'], 'template': template}, '')
    raw, layout = render(spec, chinese_font())
    assert Image.open(BytesIO(raw)).size == (1080, 1440)
    lines = layout['title']['lines']
    assert 'CodeGraph' in lines and not any(line.endswith('数') for line in lines)
    assert ''.join(lines) == spec['title']
    x, y, width, height = layout['title']['box']
    assert x + width <= 1080 and y + height <= 1440
    assert layout['title']['used_height'] <= height
    assert layout['title']['font_size'] >= 36


def test_candidates_are_cached_without_model_calls_or_repeated_asset_creation(tmp_path, monkeypatch):
    from plugins.operations import cover_renderer, model
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    monkeypatch.setattr(model, 'generate', lambda *_args: pytest.fail('封面排版不能调用模型'))
    store = Store()
    calls = []
    renderer = cover_renderer.render
    def counted(*args):
        calls.append(True)
        return renderer(*args)
    monkeypatch.setattr(cover_renderer, 'render', counted)
    draft = {'title': 'Agent开发实践', 'asset_ids': [], 'cover': {'title': 'Agent开发实践', 'keywords': ['流程设计', '执行边界']}}
    first = ensure_cover(store, draft)
    second = ensure_cover(Store(), draft)
    assert len(first['cover_candidates']) == 3
    assert [row['asset_id'] for row in first['cover_candidates']] == [row['asset_id'] for row in second['cover_candidates']]
    assert len(calls) == 3 and len(store.objects('asset')) == 3
    assert all(row['generated_typography'] for row in store.objects('asset'))
    existing = {**draft, 'asset_ids': ['user-photo']}
    assert ensure_cover(store, existing) == existing


def test_optional_model_cover_fields_are_compatible_but_user_input_is_bounded():
    spec = normalized({'title': None, 'template': {}, 'palette': [], 'keywords': '工具、方法'}, '合法标题')
    assert spec['title'] == '合法标题' and spec['template'] == 'editorial'
    assert spec['keywords'] == ['工具', '方法']
    with pytest.raises(ValueError):
        normalized({'title': '标题' * 30}, '文章标题', strict=True)


def test_keyword_phrases_do_not_split_tool_names_or_override_explicit_line_breaks():
    from PIL import ImageDraw
    from hermes_platform.fonts import chinese_font
    from plugins.operations.cover_typography import tokens, fit
    assert 'Claude Code' in tokens('Claude Code 与 CodeGraph', ('Claude Code', 'Code'))
    assert 'CodeGraph' in tokens('Claude Code 与 CodeGraph', ('Claude Code', 'Code'))
    draw = ImageDraw.Draw(Image.new('RGB', (1080, 1440)))
    _, lines, _ = fit(draw, 'CodeGraph\n真的更省 Token？', chinese_font(), width=856, height=510, maximum=106)
    assert lines == ['CodeGraph', '真的更省 Token？']


def test_preview_api_is_local_scoped_and_does_not_change_the_manuscript(cover_manuscript):
    from starlette.testclient import TestClient
    from hermes_cli import web_server
    from plugins.operations.content_release import fingerprint, manuscript
    store, _, _, draft = cover_manuscript
    path = f"/api/plugins/operations/content/{draft['id']}/covers/preview"
    scope = {'business_id': store.scope['business_id'], 'topic_id': store.scope['id']}
    body = {'version': 1, 'content_revision': fingerprint(draft), 'cover': {'title': '自定义封面'}}
    original = manuscript(store, draft['id'])
    with TestClient(web_server.app) as client:
        assert client.post(path, params=scope, json=body).status_code in (401, 403)
        client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        response = client.post(path, params=scope, json=body)
        assert response.status_code == 200, response.text
        assert response.json()['model_calls'] == 0 and len(response.json()['candidates']) == 3
        assert client.post(path, params={**scope, 'topic_id': 'foreign'}, json=body).status_code == 404
    assert manuscript(store, draft['id']) == original


def test_preview_and_apply_keep_article_evidence_and_old_schedule(cover_manuscript):
    from plugins.operations.cover_studio import preview
    from plugins.operations.content_versions import create
    from plugins.operations.content_release import fingerprint, manuscript, load
    store, _, _, draft = cover_manuscript
    support.approve(store, draft)
    body = {'version': 1, 'content_revision': fingerprint(draft), 'cover': {'title': '封面独立标题', 'subtitle': '保留正文与依据', 'palette': 'mint'}}
    result = preview(store, draft['id'], body)
    assert preview(store, draft['id'], body)['set_id'] == result['set_id']
    selected = result['candidates'][1]
    changed = create(store, draft['id'], {'request_id': 'cover-choice', 'version': 1, 'content_revision': fingerprint(draft),
        'asset_ids': [selected['asset_id']], 'cover_set_id': result['set_id']})
    child = manuscript(store, changed['id'])
    assert child['title'] == draft['title'] and child['body'] == draft['body']
    assert child['cover']['title'] == '封面独立标题'
    assert child['organization_ids'] == draft['organization_ids']
    assert len(child['cover_candidates']) == 3
    with store.connection() as db:
        assert load(db, draft['id'])['state'] == 'scheduled'
        assert load(db, child['id']) is None
    assert manuscript(store, draft['id'])['asset_ids'] == draft['asset_ids']
    with pytest.raises(ValueError, match='候选'):
        create(store, draft['id'], {'request_id': 'wrong-choice', 'version': 1, 'content_revision': fingerprint(draft),
            'asset_ids': draft['asset_ids'], 'cover_set_id': result['set_id']})
