"""An original typeset cover makes a text draft a complete image/text manuscript."""
from io import BytesIO


def ensure_cover(store, content):
    if content.get('asset_ids'):
        return content
    from hermes_platform.fonts import chinese_font
    from PIL import Image, ImageDraw, ImageFont
    font = chinese_font()
    if font is None:
        raise ValueError('无法生成中文封面：服务器缺少中文字体，请上传图片或安装中文字体')
    image = Image.new('RGB', (1080, 1440), '#f6f3ec')
    draw = ImageDraw.Draw(image)
    draw.rectangle((80, 110, 190, 126), fill='#d46b38')
    title_font = ImageFont.truetype(str(font), 96)
    small_font = ImageFont.truetype(str(font), 32)
    title = content['title']
    lines, line = [], ''
    for character in title:
        if draw.textlength(line + character, font=title_font) > 900:
            lines.append(line)
            line = ''
        line += character
    lines.append(line)
    for index, line in enumerate(lines):
        draw.text((80, 360 + index * 145), line, font=title_font, fill='#252c35')
    draw.line((80, 1200, 1000, 1200), fill='#c8c3b9', width=2)
    draw.text((80, 1250), '方法 · 实践 · 分享', font=small_font, fill='#555c64')
    output = BytesIO()
    image.save(output, format='PNG')
    identity = store.add_asset('自动文字封面.png', output.getvalue(), True)
    from .store import encoded
    import json
    with store.connection() as db:
        row = db.execute("SELECT data FROM objects WHERE kind='asset' AND id=?", (identity,)).fetchone()
        db.execute("UPDATE objects SET data=? WHERE id=?", (encoded({**json.loads(row[0]), 'generated_typography': True, 'cover_title': content['title']}), identity))
    from .workspace_resources import save_asset
    save_asset(store, identity)
    return {**content, 'asset_ids': [identity], 'cover_origin': 'generated_typography'}
