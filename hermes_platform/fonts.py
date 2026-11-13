"""Read-only lookup of an installed CJK font for local document rendering."""
from pathlib import Path
from functools import lru_cache


@lru_cache(maxsize=1)
def chinese_font():
    from hermes_platform.host.facts import os_family
    if os_family() == 'windows':
        return next((path for path in windows_font_candidates() if path.is_file()), None)
    system_assets = Path('/System/Library/AssetsV2')
    installed = sorted(system_assets.glob('com_apple_MobileAsset_Font*/**/PingFang*.ttc'))
    candidates = (
        '/System/Library/Fonts/PingFang.ttc',
        *installed,
        '/System/Library/Fonts/STHeiti Medium.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    )
    return next((Path(path) for path in candidates if Path(path).is_file()), None)


def windows_font_candidates(system_directory=None, user_directory=None):
    """Resolve native Windows fonts; explicit directories support isolated lookup tests."""
    if system_directory is None:
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.windll.kernel32.GetWindowsDirectoryW(buffer, len(buffer))
        if not 0 < length < len(buffer):
            raise OSError('无法定位 Windows 系统字体目录')
        system_directory = Path(buffer.value) / 'Fonts'
    if user_directory is None:
        from os import environ
        local = environ.get('LOCALAPPDATA')
        user_directory = Path(local) / 'Microsoft/Windows/Fonts' if local else None
    names = ('msyh.ttc', 'msyhbd.ttc', 'simhei.ttf', 'simsun.ttc', 'NotoSansCJKsc-Regular.otf')
    return tuple(Path(directory) / name for directory in (system_directory, user_directory) if directory
                 for name in names)


@lru_cache(maxsize=8)
def chinese_font_index(path):
    """Prefer the Simplified Chinese face within an installed font collection."""
    from PIL import ImageFont
    choices = []
    for index in range(16):
        try:
            family, style = ImageFont.truetype(str(path), 16, index=index).getname()
        except OSError:
            break
        priority = (10 if ' SC' in family or family.endswith('SC') else 0) + (2 if style in {'Medium', 'Semibold', 'Bold'} else 0)
        choices.append((priority, -index, index))
    return max(choices)[2] if choices else 0
