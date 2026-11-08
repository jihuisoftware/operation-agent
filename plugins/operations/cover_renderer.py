"""Four local cover layouts with bounded title areas and no invented factual copy."""
from io import BytesIO
from PIL import Image, ImageDraw

from .cover_design import PALETTES
from .cover_typography import draw_block, font_at

WIDTH, HEIGHT = 1080, 1440


def label(draw, value, path, xy, color, size=30):
    draw.text(xy, value.replace('\n', ' '), font=font_at(path, size), fill=color, anchor='lt')


def geometry(draw, colors, *, dark=False):
    ink = colors['bright'] if dark else colors['accent']
    for i in range(3):
        x, y = 720 + i * 48, 1020 + i * 48
        draw.rounded_rectangle((x, y, x + 150, y + 150), radius=22, outline=ink, width=3)
    draw.line((720, 1240, 970, 990), fill=ink, width=3)


def common(draw, spec, path, colors, *, dark=False):
    color = colors['bright'] if dark else colors['accent']
    draw.rounded_rectangle((72, 76, 106, 110), radius=8, fill=color)
    label(draw, spec['eyebrow'], path, (126, 76), color, 32)
    draw.line((72, 1310, 1008, 1310), fill=color, width=2)
    label(draw, '内容笔记', path, (72, 1340), color, 24)


def subtitle(draw, spec, path, y, color, width=896, x=80):
    if not spec['subtitle']:
        return
    draw_block(draw, spec['subtitle'], path, (x, y, width, 190), color=color, maximum=44, max_lines=3, protected=spec['keywords'])


def keywords(draw, spec, path, colors, y=1040, *, numbered=False, dark=False):
    words = spec['keywords']
    if not words:
        geometry(draw, colors, dark=dark)
        return
    fill, ink = (colors['paper'], colors['ink']) if dark else (colors['soft'], colors['ink'])
    if numbered:
        for index, word in enumerate(words):
            top = y + index * 82
            draw.rounded_rectangle((80, top, 146, top + 58), radius=16, fill=colors['accent'])
            label(draw, str(index + 1).zfill(2), path, (94, top + 12), colors['paper'], 28)
            draw_block(draw, word, path, (170, top + 7, 810, 60), color=ink, maximum=40, max_lines=1)
    else:
        for index, word in enumerate(words):
            top = y + index * 78
            draw.rounded_rectangle((80, top, 660, top + 62), radius=18, fill=fill)
            draw_block(draw, word, path, (106, top + 12, 530, 44), color=ink, maximum=34, max_lines=1)


def editorial(draw, spec, path, colors):
    draw.rounded_rectangle((72, 170, 1008, 965), radius=34, fill='#ffffff')
    draw.rectangle((80, 204, 190, 212), fill=colors['accent'])
    title = draw_block(draw, spec['title'], path, (112, 270, 856, 510), color=colors['ink'], maximum=120 if spec['size'] == 'large' else 106, protected=spec['keywords'])
    subtitle(draw, spec, path, 780, colors['ink'], width=856, x=112)
    keywords(draw, spec, path, colors, y=1040)
    return title


def comparison(draw, spec, path, colors):
    title = draw_block(draw, spec['title'], path, (80, 240, 920, 510), color=colors['ink'], maximum=124 if spec['size'] == 'large' else 110, protected=spec['keywords'])
    subtitle(draw, spec, path, 770, colors['ink'])
    if len(spec['keywords']) < 2:
        keywords(draw, spec, path, colors)
        return title
    for index in range(2):
        x = 80 + index * 474
        draw.rounded_rectangle((x, 1040, x + 446, 1246), radius=26, fill=colors['ink'] if index == 0 else colors['soft'])
        draw.rectangle((x + 26, 1072, x + 100, 1078), fill=colors['bright'] if index == 0 else colors['accent'])
        if index < len(spec['keywords']):
            draw_block(draw, spec['keywords'][index], path, (x + 26, 1110, 390, 116), color=colors['paper'] if index == 0 else colors['ink'], maximum=44, max_lines=2)
    if len(spec['keywords']) == 3:
        label(draw, spec['keywords'][2], path, (82, 1270), colors['accent'], 26)
    return title


def checklist(draw, spec, path, colors):
    draw.rectangle((80, 192, 96, 720), fill=colors['accent'])
    title = draw_block(draw, spec['title'], path, (136, 218, 856, 510), color=colors['ink'], maximum=118 if spec['size'] == 'large' else 104, protected=spec['keywords'])
    subtitle(draw, spec, path, 780, colors['ink'])
    keywords(draw, spec, path, colors, numbered=True)
    return title


def spotlight(draw, spec, path, colors):
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=colors['dark'])
    draw.ellipse((830, -180, 1270, 260), outline=colors['accent'], width=42)
    common(draw, spec, path, colors, dark=True)
    title = draw_block(draw, spec['title'], path, (80, 270, 920, 510), color=colors['paper'], maximum=132 if spec['size'] == 'large' else 116, protected=spec['keywords'])
    subtitle(draw, spec, path, 800, colors['bright'])
    keywords(draw, spec, path, colors, dark=True)
    return title


def render(spec, path):
    colors = PALETTES[spec['palette']]
    image = Image.new('RGB', (WIDTH, HEIGHT), colors['paper'])
    draw = ImageDraw.Draw(image)
    common(draw, spec, path, colors)
    title = {'editorial': editorial, 'comparison': comparison, 'checklist': checklist, 'spotlight': spotlight}[spec['template']](draw, spec, path, colors)
    output = BytesIO()
    image.save(output, format='PNG')
    return output.getvalue(), {'title': title, 'width': WIDTH, 'height': HEIGHT, 'overflow': False}
