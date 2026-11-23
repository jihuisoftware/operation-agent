"""Named design variants, ordered within a style before filling from other styles."""
SOCIAL_VARIANTS = {
    'basic': {'quotation': '纯色引言'},
    'soft': {'quotation': '上下引言', 'margin': '侧边引言', 'frame': '细框留白'},
    'print': {'torn': '撕边纸笺', 'collage': '不规则纸片'},
    'doodle': {'sketch': '随手涂鸦'},
    'handwriting': {'notebook': '横线手记', 'highlighter': '荧光涂写'},
}


def normalize_variant(value, style, strict):
    choices = SOCIAL_VARIANTS[style]
    variant = value.get('variant', next(iter(choices)))
    if not isinstance(variant, str) or variant not in choices:
        if strict:
            raise ValueError('当前封面风格的款式无效')
        variant = next(iter(choices))
    return variant


def social_variations(spec):
    style = spec.get('style', 'basic')
    variant = spec.get('variant', next(iter(SOCIAL_VARIANTS[style])))
    same = [(style, variant), *[(style, key) for key in SOCIAL_VARIANTS[style] if key != variant]]
    others = [(other, key) for other, variants in SOCIAL_VARIANTS.items() if other != style for key in variants]
    return [{**spec, 'style': selected_style, 'variant': selected_variant}
            for selected_style, selected_variant in (same + others)[:3]]


def variant_label(spec):
    if spec['template'] == 'cartoon':
        from .cover_cartoon_catalog import CHARACTERS
        return CHARACTERS[spec.get('variant', 'kico')]
    if spec['template'] != 'xiaohongshu':
        return ''
    choices = SOCIAL_VARIANTS[spec.get('style', 'basic')]
    return choices[spec.get('variant', next(iter(choices)))]


def cover_font(spec):
    from hermes_platform.fonts import chinese_font, chinese_handwriting_font, chinese_serif_font
    if spec['template'] != 'xiaohongshu':
        return chinese_font()
    selectors = {'handwriting': chinese_handwriting_font, 'print': chinese_serif_font}
    return selectors.get(spec.get('style'), chinese_font)()
