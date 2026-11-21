"""Original social-note layouts: local vector decorations and measured Chinese typography."""
from io import BytesIO
import math
import random

from PIL import Image, ImageDraw

from .cover_design import PALETTES
from .cover_typography import fit, font_at, draw_block

WIDTH, HEIGHT = 1080, 1440


def tint(color, amount):
    rgb = tuple(int(color[index:index + 2], 16) for index in (1, 3, 5))
    return tuple(round(channel + (255 - channel) * amount) for channel in rgb)


def paper(draw, base, seed=19):
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=base)
    rng = random.Random(seed)
    for _ in range(16000):
        x, y = rng.randrange(WIDTH), rng.randrange(HEIGHT)
        offset = rng.choice((-5, -3, 2, 4))
        draw.point((x, y), fill=tuple(max(0, min(255, c + offset)) for c in base))


def quotation(draw, path, xy, color, closing=False):
    draw.text(xy, '”' if closing else '“', font=font_at(path, 210), fill=color, anchor='lt')


def star(draw, center, color, radius=28):
    x, y = center
    points = [(x + math.cos(i * math.pi / 4) * (radius if i % 2 == 0 else radius / 4),
               y + math.sin(i * math.pi / 4) * (radius if i % 2 == 0 else radius / 4)) for i in range(8)]
    draw.polygon(points, fill=color)


def pig_sketch(draw, x, y, color):
    """A small original guinea-pig line drawing, not a bundled platform sticker."""
    draw.rounded_rectangle((x, y + 28, x + 170, y + 154), radius=62, outline=color, width=5)
    draw.ellipse((x + 22, y + 6, x + 60, y + 50), fill='#fffdf7', outline=color, width=5)
    draw.ellipse((x + 112, y + 6, x + 150, y + 50), fill='#fffdf7', outline=color, width=5)
    for px in (x + 56, x + 116):
        draw.ellipse((px, y + 70, px + 10, y + 82), fill=color)
    draw.ellipse((x + 82, y + 91, x + 96, y + 102), fill=color)
    draw.arc((x + 68, y + 94, x + 110, y + 121), 10, 170, fill=color, width=4)
    draw.line((x + 12, y + 128, x - 24, y + 111), fill=color, width=4)
    draw.line((x + 159, y + 128, x + 192, y + 111), fill=color, width=4)


def basic(draw, spec, path, colors):
    paper(draw, tint(colors['accent'], .84))
    quotation(draw, path, (110, 134), tint(colors['accent'], .62))
    draw.line((870, 1260, 946, 1260), fill=tint(colors['accent'], .55), width=12)


def soft(draw, spec, path, colors):
    paper(draw, (250, 249, 246))
    quotation(draw, path, (116, 144), colors['accent'])
    quotation(draw, path, (116, 1180), colors['accent'], closing=True)


def printed(draw, spec, path, colors):
    paper(draw, tint(colors['accent'], .9))
    rng = random.Random(37)
    left = [(100 + rng.randrange(-20, 20), y) for y in range(290, 1160, 35)]
    right = [(976 + rng.randrange(-20, 20), y) for y in range(1140, 270, -35)]
    draw.polygon([*left, *right], fill='#fffdf7')
    draw.line((130, 1210, 950, 1210), fill=tint(colors['accent'], .7), width=2)
    draw.ellipse((820, 180, 950, 310), fill=tint(colors['accent'], .64))
    draw.ellipse((830, 190, 940, 300), outline=colors['accent'], width=2)
    draw.text((885, 245), '随手记', font=font_at(path, 24), fill=colors['ink'], anchor='mm')


def doodle(draw, spec, path, colors):
    paper(draw, (250, 252, 251))
    ink = tint(colors['accent'], .28)
    draw.arc((110, 126, 320, 268), 180, 520, fill=ink, width=10)
    draw.line([(260, 220), (359, 247), (346, 191)], fill=ink, width=10, joint='curve')
    star(draw, (930, 310), ink, 35)
    star(draw, (888, 356), ink, 16)
    pig_sketch(draw, 735, 1110, colors['ink'])
    draw.line([(607, 1311), (949, 1299), (946, 1257)], fill=ink, width=9)
    draw.line([(620, 1326), (956, 1317)], fill=ink, width=3)


def handwriting(draw, spec, path, colors):
    paper(draw, (250, 252, 249))
    for y in range(110, HEIGHT, 66):
        draw.line((56, y, WIDTH - 56, y), fill=tint(colors['accent'], .91), width=2)
    pig_sketch(draw, 780, 1170, colors['ink'])


def marker(draw, x, y, width, height, color, seed):
    rng = random.Random(seed)
    top = [(x + i, y + rng.randrange(-7, 8)) for i in range(0, int(width) + 1, 18)]
    bottom = [(x + i, y + height + rng.randrange(-7, 8)) for i in range(int(width), -1, -18)]
    draw.polygon([*top, *bottom], fill=color)


def title_block(draw, spec, path, colors, style):
    variant = spec.get('variant')
    box = (180, 330, 740, 660) if variant == 'margin' else (140, 350, 800, 660)
    x, top, width, height = box
    font, lines, spacing = fit(draw, spec['title'], path, width=width, height=height,
                               maximum=124 if spec['size'] == 'large' else 108,
                               max_lines=5, protected=spec['keywords'])
    y = top + (height - len(lines) * spacing) // 2
    color = colors['accent'] if style == 'soft' else colors['ink']
    for index, line in enumerate(lines):
        line_y = y + index * spacing
        if variant == 'highlighter' and index == len(lines) // 2:
            from .cover_social_variants import highlight_line
            highlight_line(draw, (x - 24, line_y - 8, width + 48, font.size + 28), colors['accent'])
        elif style == 'handwriting' and variant != 'highlighter':
            marker(draw, x - 16, line_y + font.size * .45,
                   draw.textlength(line, font=font) + 30, font.size * .65, tint(colors['accent'], .72), index)
        line_x = x + (width - draw.textlength(line, font=font)) / 2 if variant == 'frame' else x
        draw.text((line_x, line_y), line, font=font, fill=color, anchor='lt', stroke_width=2 if variant == 'highlighter' else 0)
    return {'lines': lines, 'font_size': font.size, 'box': [x, y, width, height - (y - top)],
            'used_height': len(lines) * spacing}


def render(spec, path):
    style = spec.get('style', 'basic')
    from .cover_variants import cover_font
    from .cover_social_variants import BACKGROUNDS
    path = cover_font(spec) or path
    image = Image.new('RGB', (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    colors = PALETTES[spec['palette']]
    default = {'basic': basic, 'soft': soft, 'print': printed, 'doodle': doodle, 'handwriting': handwriting}[style]
    BACKGROUNDS.get((style, spec.get('variant')), default)(draw, spec, path, colors)
    title = title_block(draw, spec, path, colors, style)
    if spec.get('eyebrow') and spec['eyebrow'] != '主题分享':
        draw_block(draw, spec['eyebrow'], path, (140, 88, 760, 50), color=colors['accent'], maximum=26, max_lines=1)
    if spec.get('subtitle'):
        draw_block(draw, spec['subtitle'], path, (140, 1024, 760, 132), color=colors['ink'], maximum=30, max_lines=3)
    output = BytesIO()
    image.save(output, format='PNG')
    return output.getvalue(), {'title': title, 'width': WIDTH, 'height': HEIGHT, 'overflow': False,
                               'style': style, 'variant': spec.get('variant'), 'font_family': font_at(path, 20).getname()[0]}
