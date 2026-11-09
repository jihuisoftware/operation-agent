"""Bounded cover copy and design choices; optional model output never breaks a draft."""
import re
import unicodedata

RENDER_VERSION = 3
TEMPLATES = {'editorial': '编辑精选', 'comparison': '对比卡片', 'checklist': '清单要点', 'spotlight': '醒目标题'}
PALETTES = {
    'blue': {'name': '深海蓝', 'paper': '#edf2f7', 'ink': '#12283f', 'accent': '#196cbe', 'soft': '#d8e6f5', 'dark': '#12283f', 'bright': '#a5d6ff'},
    'mint': {'name': '薄荷绿', 'paper': '#edf4ee', 'ink': '#173b35', 'accent': '#267a63', 'soft': '#d5e7d7', 'dark': '#173b35', 'bright': '#b7e3be'},
    'sand': {'name': '暖砂橙', 'paper': '#f6f1e7', 'ink': '#342d28', 'accent': '#b8492d', 'soft': '#eadbc7', 'dark': '#342d28', 'bright': '#f5bd8b'},
    'plum': {'name': '雾紫色', 'paper': '#f2eef6', 'ink': '#352541', 'accent': '#8051a1', 'soft': '#e4d9ee', 'dark': '#352541', 'bright': '#d9b9f1'},
}
LIMITS = {'title': 36, 'subtitle': 60, 'eyebrow': 12, 'keyword': 12}


def options():
    return {'templates': [{'id': key, 'label': value} for key, value in TEMPLATES.items()],
            'palettes': [{'id': key, 'label': value['name'], 'color': value['accent']} for key, value in PALETTES.items()],
            'limits': LIMITS, 'renderer_version': RENDER_VERSION}


def text(value):
    if not isinstance(value, str):
        return ''
    clean = ''.join(c for c in value if c == '\n' or not unicodedata.category(c).startswith('C'))
    return re.sub(r'[^\S\n]+', ' ', clean).strip()


def normalized(value, article_title, *, strict=False):
    article_title = text(article_title)
    value = value if isinstance(value, dict) else {}
    result = {}
    for key in ('title', 'subtitle', 'eyebrow'):
        default = article_title if key == 'title' else '主题分享' if key == 'eyebrow' else ''
        content = text(value.get(key, default))
        if key == 'title' and not content:
            content = text(article_title)
        if strict and (len(content) > LIMITS[key] or (key == 'title' and not content)):
            raise ValueError(f'封面{key}需填写有效文字，最多 {LIMITS[key]} 字')
        result[key] = content[:LIMITS[key]]
    words = value.get('keywords', [])
    if not isinstance(words, list):
        words = re.split(r'[,，、]', words) if isinstance(words, str) else []
    words = [text(word).replace('\n', ' ') for word in words if text(word)]
    if strict and (len(words) > 3 or any(len(word) > LIMITS['keyword'] for word in words)):
        raise ValueError('封面关键词最多 3 项，每项不超过 12 字')
    result['keywords'] = list(dict.fromkeys(word[:LIMITS['keyword']] for word in words))[:3]
    inferred = 'comparison' if '对比' in article_title else 'checklist' if any(word in article_title for word in ('步骤', '清单', '教程', '指南')) else 'editorial'
    for key, choices, default in (('template', TEMPLATES, inferred), ('palette', PALETTES, 'blue'), ('size', ('normal', 'large'), 'normal')):
        chosen = value.get(key, default)
        if not isinstance(chosen, str) or chosen not in choices:
            if strict:
                raise ValueError('封面样式无效：' + key)
            chosen = default
        result[key] = chosen
    return result


def variations(spec):
    alternatives = ['spotlight', 'checklist', 'editorial', 'comparison']
    templates = [spec['template'], *[key for key in alternatives if key != spec['template']]][:3]
    palettes = [spec['palette'], 'mint' if spec['palette'] != 'mint' else 'blue', 'sand' if spec['palette'] != 'sand' else 'plum']
    return [{**spec, 'template': template, 'palette': palette} for template, palette in zip(templates, palettes)]
