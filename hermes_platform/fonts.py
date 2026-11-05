"""Read-only lookup of an installed CJK font for local document rendering."""
from pathlib import Path


def chinese_font():
    candidates = (
        '/System/Library/Fonts/STHeiti Medium.ttc',
        '/System/Library/Fonts/PingFang.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    )
    return next((Path(path) for path in candidates if Path(path).is_file()), None)
