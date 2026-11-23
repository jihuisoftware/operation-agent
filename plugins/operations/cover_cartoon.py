"""Polka-dot cover with measured caption strips and a single character sticker."""
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from .cover_cartoon_catalog import CHARACTERS
from .cover_design import PALETTES
from .cover_typography import fit, font_at

STICKERS = Path(__file__).with_name('cartoon_stickers')


def strip(draw, text, path, box, background, foreground, maximum, *, max_lines=4, protected=()):
    x, y, width, height = box
    padding = 18
    # A short mixed-script headline (e.g. "bot起号") looks best on one strip.
    font = font_at(path, maximum)
    if '\n' not in text and draw.textlength(text, font=font) <= width - 2 * padding and maximum * 1.35 <= height:
        lines, spacing = [text], round(maximum * 1.35)
    else:
        font, lines, spacing = fit(draw, text, path, width=width - 2 * padding, height=height,
                                   maximum=maximum, minimum=22, max_lines=max_lines, protected=protected)
    for i, line in enumerate(lines):
        top = y + i * spacing
        right = x + round(draw.textlength(line, font=font)) + 2 * padding
        draw.rectangle((x, top, right, top + spacing - 5), fill=background)
        draw.text((x + padding, top + (spacing - 5) // 2), line, font=font, anchor='lm', fill=foreground)
    return {'box': list(box), 'lines': lines, 'font_size': font.size, 'used_height': len(lines) * spacing}


def render(spec, path):
    colors = PALETTES[spec['palette']]
    image = Image.new('RGB', (1080, 1440), colors['paper'])
    draw = ImageDraw.Draw(image)
    for row, y in enumerate(range(10, image.height, 49)):
        for x in range(20 + 48 * (row % 2), image.width, 96):
            draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=colors['soft'])

    character = spec.get('variant', 'kico')
    if character not in CHARACTERS:
        raise ValueError('请选择有效的卡通角色')
    with Image.open(STICKERS / (character + '.png')) as asset:
        sticker = ImageOps.contain(asset, (660, 765), method=Image.Resampling.LANCZOS)
    bottom = 1290 if spec['subtitle'] else 1370
    image.paste(sticker, (1030 - sticker.width, bottom - sticker.height), sticker)

    accent = colors['accent']
    light_ink = colors['ink'] if spec['palette'] == 'lime' else 'white'
    title = strip(draw, spec['title'], path, (72, 84, 938, 490), accent, light_ink,
                  248 if spec['size'] == 'large' else 224, protected=spec['keywords'])
    tag_top = 106 + title['used_height']
    if spec['eyebrow']:
        eyebrow = strip(draw, spec['eyebrow'], path, (72, tag_top, 875, 157),
              '#19151a', 'white', 106, max_lines=2)
        tag_top += eyebrow['used_height'] + 26
    if spec['keywords']:
        strip(draw, ' · '.join(spec['keywords']), path, (72, max(640, tag_top), 390, 410),
              accent, light_ink, 102, max_lines=8)
    if spec['subtitle']:
        strip(draw, spec['subtitle'], path, (57, 1248, 968, 145), colors['bright'], colors['ink'], 67)
    output = BytesIO()
    image.save(output, format='PNG')
    return output.getvalue(), {'title': title, 'width': image.width, 'height': image.height, 'overflow': False}
