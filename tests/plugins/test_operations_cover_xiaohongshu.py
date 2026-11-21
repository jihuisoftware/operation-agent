"""Social covers preserve user text and remain deterministic local assets."""
from io import BytesIO

from PIL import Image
import pytest

from hermes_platform.fonts import chinese_font
from plugins.operations.cover_design import normalized, variations, SOCIAL_STYLES
from plugins.operations.cover_renderer import render


@pytest.mark.parametrize('style', list(SOCIAL_STYLES))
@pytest.mark.parametrize('title', ['荷兰猪真可爱，真的好可爱啊', '有没有女主视角小说推荐', '这是一个用于验证长标题在小红书风格封面中能够完整排版而不被裁切的测试'])
def test_social_styles_keep_complete_title_within_safe_area(style, title):
    spec = normalized({'template': 'xiaohongshu', 'style': style, 'title': title}, '', strict=True)
    raw, layout = render(spec, chinese_font())
    assert Image.open(BytesIO(raw)).size == (1080, 1440)
    assert ''.join(layout['title']['lines']) == title
    x, y, w, h = layout['title']['box']
    assert x >= 0 and y >= 0 and x + w <= 1080 and y + h <= 1440
    assert layout['title']['used_height'] <= h
    assert render(spec, chinese_font())[0] == raw
    variants = variations(spec)
    assert variants[0] == spec
    assert all(item['template'] == 'xiaohongshu' and item['title'] == title for item in variants)
    assert len({(item['style'], item['variant']) for item in variants}) == 3


def test_social_preview_cache_and_invalid_style(tmp_path, monkeypatch):
    from plugins.operations.cover_assets import candidates
    from plugins.operations.store import Store
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    spec = normalized({'template': 'xiaohongshu', 'style': 'handwriting'}, '荷兰猪真可爱')
    first = candidates(store, spec)
    assert candidates(store, spec) == first
    assert len(store.objects('asset')) == 3
    assert first[0]['template_label'] == '小红书版 · 手写'
    with pytest.raises(ValueError, match='风格'):
        normalized({'template': 'xiaohongshu', 'style': 'unknown'}, '标题', strict=True)
