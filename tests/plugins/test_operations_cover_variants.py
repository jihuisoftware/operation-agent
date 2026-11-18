"""Candidate priority is the selected design family and palette, not unrelated styles."""
from io import BytesIO

import pytest
from PIL import Image

from plugins.operations.cover_design import normalized, variations
from plugins.operations.cover_variants import SOCIAL_VARIANTS, cover_font
from plugins.operations.cover_renderer import render


@pytest.mark.parametrize('style', SOCIAL_VARIANTS)
def test_same_style_variants_precede_fallback_and_keep_palette(style):
    for selected in SOCIAL_VARIANTS[style]:
        spec = normalized({'template': 'xiaohongshu', 'style': style, 'variant': selected, 'palette': 'blue'}, '荷兰猪真可爱')
        results = variations(spec)
        same_count = min(3, len(SOCIAL_VARIANTS[style]))
        assert results[0] == spec
        assert all(row['style'] == style for row in results[:same_count])
        assert all(row['style'] != style for row in results[same_count:])
        assert all(row['palette'] == 'blue' and row['title'] == spec['title'] for row in results)
        assert len(results) == len({(row['style'], row['variant']) for row in results}) == 3


@pytest.mark.parametrize('style,variant', [(s, v) for s, variants in SOCIAL_VARIANTS.items() for v in variants])
def test_all_variants_render_distinct_images_and_keep_long_text(style, variant):
    title = '这是一个用于验证长标题在小红书风格封面中能够完整排版而不被裁切的测试'
    spec = normalized({'template': 'xiaohongshu', 'style': style, 'variant': variant}, title, strict=True)
    raw, layout = render(spec, cover_font(spec))
    assert Image.open(BytesIO(raw)).size == (1080, 1440)
    assert ''.join(layout['title']['lines']) == title
    assert layout['title']['used_height'] <= layout['title']['box'][3]
    images = [render(other, cover_font(other))[0] for other in variations(spec)]
    assert len(set(images)) == 3
    assert render(spec, cover_font(spec))[0] == raw


def test_invalid_variant_is_rejected_and_old_specs_get_a_default():
    with pytest.raises(ValueError, match='款式'):
        normalized({'template': 'xiaohongshu', 'style': 'soft', 'variant': 'collage'}, '标题', strict=True)
    assert normalized({'template': 'xiaohongshu', 'style': 'handwriting'}, '标题')['variant'] == 'notebook'
