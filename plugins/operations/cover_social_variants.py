"""Additional original paper and marker designs within the existing social styles."""
import math
import random


def soft_margin(draw, spec, path, colors):
    from .cover_xiaohongshu import paper, quotation, tint
    paper(draw, (250, 249, 246))
    draw.line((98, 354, 98, 1060), fill=tint(colors['accent'], .6), width=5)
    quotation(draw, path, (150, 170), colors['accent'])
    draw.line((770, 1240, 940, 1240), fill=colors['accent'], width=3)


def soft_frame(draw, spec, path, colors):
    from .cover_xiaohongshu import paper, quotation, tint
    paper(draw, (250, 249, 246))
    draw.rounded_rectangle((64, 86, 1016, 1354), radius=42, outline=tint(colors['accent'], .65), width=3)
    quotation(draw, path, (455, 160), colors['accent'])
    quotation(draw, path, (455, 1180), colors['accent'], closing=True)


def torn_oval(draw, center, radius, angle, seed):
    rng = random.Random(seed)
    x, y = center
    rx, ry = radius
    turn = math.radians(angle)
    points = []
    for i in range(180):
        theta = math.tau * i / 180
        r = 1 + rng.uniform(-.012, .012)
        px, py = rx * math.cos(theta) * r, ry * math.sin(theta) * r
        points.append((x + px * math.cos(turn) - py * math.sin(turn),
                       y + px * math.sin(turn) + py * math.cos(turn)))
    draw.polygon(points, fill='#fffdf7')


def paper_collage(draw, spec, path, colors):
    from .cover_xiaohongshu import paper, tint
    from .cover_typography import font_at
    paper(draw, tint(colors['accent'], .9))
    for center, radius, angle, seed in (
        ((465, 665), (385, 380), 25, 17), ((645, 650), (355, 370), -20, 19),
        ((430, 955), (355, 285), -22, 23), ((665, 945), (330, 290), 24, 29),
    ):
        torn_oval(draw, center, radius, angle, seed)
    draw.ellipse((742, 226, 876, 360), fill=tint(colors['accent'], .64))
    draw.ellipse((753, 237, 865, 349), outline=tint(colors['accent'], .15), width=2)
    draw.text((809, 293), '随手记', font=font_at(path, 24), fill=colors['ink'], anchor='mm')


def highlighter(draw, spec, path, colors):
    from .cover_xiaohongshu import paper
    paper(draw, (252, 252, 250))


def highlight_line(draw, box, color):
    """Layered dry-brush edges with deterministic bristle gaps."""
    x, y, width, height = box
    rng = random.Random(83)
    for offset in range(int(height)):
        inset = rng.uniform(0, 18)
        draw.line((x + inset, y + offset, x + width - rng.uniform(0, 15), y + offset), fill=color, width=1)
    for _ in range(85):
        left = x + rng.uniform(0, width)
        top = y + rng.uniform(0, height)
        draw.line((left, top, min(x + width, left + rng.uniform(2, 24)), top), fill='#fcfcfa', width=1)


BACKGROUNDS = {
    ('soft', 'margin'): soft_margin,
    ('soft', 'frame'): soft_frame,
    ('print', 'collage'): paper_collage,
    ('handwriting', 'highlighter'): highlighter,
}
