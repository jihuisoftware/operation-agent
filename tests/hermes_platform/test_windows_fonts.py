"""System and per-user Windows fonts are searched without relying on the drive letter."""
import pytest

from hermes_platform.fonts import windows_font_candidates, chinese_font, chinese_font_index


def test_windows_font_candidates_respect_selected_directories(tmp_path):
    system = tmp_path / '系统字体'
    user = tmp_path / 'User Fonts'
    candidates = windows_font_candidates(system, user)
    assert system / 'msyh.ttc' in candidates
    assert user / 'NotoSansCJKsc-Regular.otf' in candidates
    assert all(path.parent in (system, user) for path in candidates)


@pytest.mark.platforms('windows')
def test_native_windows_chinese_cover_font_can_be_loaded():
    from PIL import ImageFont
    selected = chinese_font()
    assert selected is not None, 'Windows test host needs the Simplified Chinese font pack'
    face = ImageFont.truetype(str(selected), 40, index=chinese_font_index(selected))
    assert face.getlength('营运智能体') > 0
