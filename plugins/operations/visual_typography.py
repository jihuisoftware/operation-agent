"""Measured, balanced wrapping with indivisible English names and protected Chinese phrases."""
import re
from functools import cache, lru_cache

from PIL import ImageFont

PHRASES = ('人工智能', '智能体', '工作流', '代码库', '待核实', '数据', '模型', '开发', '工具', '分析', '对比', '原理', '实践', '方法', '降本', '入门', '教程', '指南', '边界', '核对', '应用', '效率', '案例', '为什么', '不适合', '真的', '更省', '如何', '是否', '值得', '不能')
OPENING, CLOSING = '（《「【(', '，。！？：；、）》」】!?.,:;)'


@lru_cache(maxsize=256)
def font_at(path, size):
    from hermes_platform.fonts import chinese_font_index
    return ImageFont.truetype(str(path), size, index=chinese_font_index(path))


def tokens(value, protected=()):
    phrases = sorted({word for word in (*PHRASES, *protected) if word}, key=len, reverse=True)
    pattern = '|'.join((r'(?<![A-Za-z0-9._+#/-])' + re.escape(word) + r'(?![A-Za-z0-9._+#/-])')
                       if re.search('[A-Za-z]', word) else re.escape(word) for word in phrases)
    return re.findall(pattern + r'|[A-Za-z0-9]+(?:[._+#/-][A-Za-z0-9]+)*|\s+|.', value)


def wrap(draw, value, font, width, protected=()):
    pieces = tokens(value, protected)

    @cache
    def solve(start):
        if start == len(pieces):
            return 0, []
        best = None
        for end in range(start + 1, len(pieces) + 1):
            line = ''.join(pieces[start:end]).strip()
            if not line:
                continue
            length = draw.textlength(line, font=font)
            if length > width:
                break
            cost, rest = solve(end)
            penalty = (width - length) ** 2
            if line[-1] in OPENING or (rest and rest[0][0] in CLOSING):
                penalty += width ** 2 * 8
            if len(line) <= 2 and len(pieces) > 4:
                penalty += width ** 2 * 3
            candidate = (cost + penalty, [line, *rest])
            if best is None or candidate[0] < best[0]:
                best = candidate
        return best or (float('inf'), [])

    return solve(0)[1]


def fit(draw, value, path, *, width, height, maximum=120, minimum=36, max_lines=4, protected=()):
    # A named tool followed by Chinese copy deserves its own line, rather than
    # squeezing the final Chinese syllable onto the next row. Single-line labels
    # must keep the original text: an inserted break cannot fit their line budget.
    if max_lines > 1 and '\n' not in value:
        value = re.sub(r'^([A-Za-z][A-Za-z0-9._+#/-]{2,})\s*(?=[\u4e00-\u9fff])', r'\1\n', value)
    paragraphs = [line.strip() for line in value.splitlines() if line.strip()]
    if len(paragraphs) > 1:
        for size in range(maximum, max(minimum, round(maximum * .78)) - 1, -2):
            font = font_at(path, size)
            spacing = round(size * 1.35)
            if len(paragraphs) <= max_lines and spacing * len(paragraphs) <= height and all(draw.textlength(line, font=font) <= width for line in paragraphs):
                return font, paragraphs, spacing
    for size in range(maximum, minimum - 1, -2):
        font = font_at(path, size)
        lines = [line for paragraph in value.splitlines() if paragraph.strip() for line in wrap(draw, paragraph, font, width, protected)]
        line_height = round(size * 1.35)
        if lines and len(lines) <= max_lines and line_height * len(lines) <= height and all(draw.textlength(line, font=font) <= width for line in lines):
            # Reject a partial wrap when a single word cannot fit at this size.
            if ''.join(lines).replace(' ', '') == ''.join(value.split()):
                return font, lines, line_height
    raise ValueError('封面文字无法完整排版，请缩短主标题、副标题或减少换行')


def draw_block(draw, value, path, box, *, color, maximum=120, max_lines=4, protected=()):
    x, y, width, height = box
    font, lines, spacing = fit(draw, value, path, width=width, height=height, maximum=maximum,
                               minimum=min(36, maximum // 2), max_lines=max_lines, protected=protected)
    for index, line in enumerate(lines):
        draw.text((x, y + index * spacing), line, font=font, fill=color, anchor='lt')
    return {'lines': lines, 'font_size': font.size, 'box': list(box), 'used_height': len(lines) * spacing}
