"""Mixed-language labels fit single-line slots without losing text or explicit breaks."""
from PIL import Image, ImageDraw
import pytest

from hermes_platform.fonts import chinese_font
from plugins.operations.cover_typography import fit


@pytest.mark.parametrize('value', ['Token成本', 'Agent工具', 'OpenAI模型'])
def test_single_line_labels_keep_english_and_chinese_together(value):
    draw = ImageDraw.Draw(Image.new('RGB', (1080, 1440)))
    face, lines, spacing = fit(draw, value, chinese_font(), width=530, height=44,
                               maximum=34, minimum=17, max_lines=1)
    assert lines == [value]
    assert draw.textlength(lines[0], font=face) <= 530 and spacing <= 44
    with pytest.raises(ValueError, match='无法完整排版'):
        fit(draw, value[:5] + '\n' + value[5:], chinese_font(), width=530, height=44,
            maximum=34, minimum=17, max_lines=1)
