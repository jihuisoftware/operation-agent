"""Read-only lookup of an installed CJK font for local document rendering."""
from pathlib import Path
from functools import lru_cache


@lru_cache(maxsize=1)
def chinese_font():
    system_assets = Path('/System/Library/AssetsV2')
    installed = sorted(system_assets.glob('com_apple_MobileAsset_Font*/**/PingFang*.ttc'))
    candidates = (
        '/System/Library/Fonts/PingFang.ttc',
        *installed,
        '/System/Library/Fonts/STHeiti Medium.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    )
    return next((Path(path) for path in candidates if Path(path).is_file()), None)


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
