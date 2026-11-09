"""Editorial composition: AI artwork, measured Chinese typography and real information hierarchy."""
from io import BytesIO
import re
from PIL import Image, ImageDraw, ImageOps

from .cover_typography import fit, font_at

WIDTH, HEIGHT = 1080, 1440
PAPER, INK, BLUE, ORANGE, SOFT = '#F7F5EF', '#16202E', '#1748CA', '#EF6B3F', '#E4E9F4'
VERSION = 1


def text(draw, value, font, box, size, color=INK, lines=4):
    if not value:
        return
    x, y, width, height = box
    face, wrapped, spacing = fit(draw, value, font, width=width, height=height, maximum=size,
                                 minimum=size if size <= 40 else max(42, round(size * .78)), max_lines=lines)
    for index, line in enumerate(wrapped):
        draw.text((x, y + index * spacing), line, font=face, fill=color, anchor='lt')


def art(image, raw, box):
    x, y, width, height = box
    with Image.open(BytesIO(raw)) as source:
        picture = ImageOps.fit(source.convert('RGB'), (width, height), method=Image.Resampling.LANCZOS)
    image.paste(picture, (x, y))


def folio(draw, font, index, count):
    draw.line((72, 1342, 1008, 1342), fill='#C6C9CB', width=2)
    draw.text((72, 1370), '知识与实践  /  KNOWLEDGE NOTES', font=font_at(font, 22), fill=INK)
    draw.text((902, 1362), f'{index + 1:02d} / {count:02d}', font=font_at(font, 30), fill=BLUE)


def cover(image, draw, page, font, raw):
    text(draw, 'IDEAS INTO PRACTICE', font, (76, 64, 900, 40), 26, BLUE, 1)
    draw.rectangle((76, 126, 152, 137), fill=ORANGE)
    headline = page['title']
    if '\n' not in headline:
        headline = re.sub(r'([A-Za-z][A-Za-z0-9 ._+/-]*)(?=[\u4e00-\u9fff])', r'\1\n', headline, count=1)
    text(draw, headline, font, (72, 177, 936, 330), 100, INK, 3)
    if page['intro']:
        text(draw, page['intro'], font, (78, 520, 906, 164), 40, lines=3)
    art(image, raw, (0, 716, 1080, 490))
    draw.rectangle((72, 1180, 1008, 1298), fill=BLUE)
    labels = [item['label'] for item in page['items'] if item['label']][:3]
    value = '  /  '.join(labels) or '拆解思路 · 方法 · 实践'
    text(draw, value, font, (106, 1205, 868, 86), 32, '#FFFFFF', 2)


def item_rows(draw, page, font, top, *, compact=False):
    items = page['items']
    step = 264 if compact else 262
    for index, item in enumerate(items):
        y = top + index * step
        draw.text((74, y + 4), f'{index + 1:02d}', font=font_at(font, 44), fill=BLUE)
        draw.line((158, y + 10, 158, y + step - 40), fill='#C6C9CB', width=2)
        if item['label']:
            text(draw, item['label'], font, (190, y, 806, 72), 46, lines=1)
        text(draw, item['text'], font, (190, y + 80, 806, step - 84), 42, lines=3)
        if page['kind'] == 'steps' and index < len(items) - 1:
            draw.polygon([(93, y + step - 32), (115, y + step - 32), (104, y + step - 16)], fill=ORANGE)


def comparison(draw, page, font):
    items = page['items']
    for index, item in enumerate(items[:2]):
        x = 72 + 480 * index
        draw.rectangle((x, 535, x + 456, 1100), fill=BLUE if index == 0 else SOFT)
        color = '#FFFFFF' if index == 0 else INK
        draw.rectangle((x + 32, 568, x + 110, 577), fill=ORANGE)
        text(draw, item['label'], font, (x + 32, 610, 390, 150), 48, color, 2)
        text(draw, item['text'], font, (x + 32, 750, 390, 350), 42, color, 6)
    if len(items) > 2:
        text(draw, items[2]['label'] + '：' + items[2]['text'], font, (76, 1145, 920, 180), 42, lines=3)


def render(page, index, count, raw=None):
    from hermes_platform.fonts import chinese_font
    font = chinese_font()
    if not font:
        raise ValueError('组图需要可用的中文字体')
    image = Image.new('RGB', (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    if page['kind'] == 'cover':
        if not raw:
            raise ValueError('封面主视觉尚未生成，保留文字草稿')
        cover(image, draw, page, font, raw)
    else:
        draw.rectangle((74, 68, 150, 80), fill=ORANGE)
        text(draw, page['title'], font, (72, 133, 936, 192), 70, lines=2)
        if page['intro']:
            text(draw, page['intro'], font, (76, 354, 928, 162), 40, lines=3)
        if raw:
            art(image, raw, (72, 535, 936, 408))
            compact = {**page, 'items': page['items'][:1]}
            # Art pages have one key takeaway; no silently omitted copy.
            if len(page['items']) > 1:
                raise ValueError('带插画内页最多一个要点，请拆分为信息图页')
            item_rows(draw, compact, font, 1035, compact=True)
        elif page['kind'] == 'comparison' and len(page['items']) >= 2:
            comparison(draw, page, font)
        else:
            item_rows(draw, page, font, 530)
    folio(draw, font, index, count)
    output = BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()
