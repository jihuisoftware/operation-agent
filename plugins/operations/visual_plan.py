"""Source-bound magazine storyboards; all visible copy remains reviewable text."""
import hashlib

from .store import encoded

VERSION = 1
STYLE = 'magazine'
PROMPT = '''同时返回 visual_plan: {"pages":[{"kind":"cover/steps/comparison/checklist/story","title":"短标题", "intro":"一句导语", "items":[{"label":"小标题","text":"说明"}], "art":"画面主体与构图，不含任何文字"}]}。
组图采用清爽杂志与信息图风格，通常3至6页，含第一页封面。每页一个信息重点，不重复正文凑页；资料少可少于3页。
封面标题6至18字，可用换行分成两个完整短句，英文名与中文词组不拆开，导语最多45字；内页标题最多20字，导语最多60字，内页1至3个要点（label最多12字，text最多48字），每页所有中文合计不超过160字。
流程仅使用有依据的步骤；对比必须使用明确对象和相同维度。所有文字、数字、结论仅来自本稿和获授权依据，不能编造实测或界面。
只有封面和至多一个重点内页使用art，带插画内页最多一个要点，其余使用信息图。art只描述无文字插画，不生成截图、Logo、代码、文字或数据图表。'''


def signature(content):
    return hashlib.sha256(encoded({key: content.get(key) for key in ('title', 'body', 'source_ids', 'analysis_context')}).encode()).hexdigest()


def short(value, limit, name):
    if not isinstance(value, str) or len(value.strip()) > limit:
        raise ValueError(f'组图{name}格式不正确或超过{limit}字，请精简后重试')
    return value.strip()


def validate(value):
    pages = value.get('pages') if isinstance(value, dict) else None
    if not isinstance(pages, list) or not 2 <= len(pages) <= 6:
        raise ValueError('组图需要2至6页有效内容，不拼凑空白页面')
    result, art_count = [], 0
    for index, page in enumerate(pages):
        if not isinstance(page, dict):
            raise ValueError('组图页面格式无效')
        kind = 'cover' if index == 0 else page.get('kind', 'story')
        if kind not in {'cover', 'steps', 'comparison', 'checklist', 'story'} or (index and kind == 'cover'):
            raise ValueError('组图页面类型无效')
        title = short(page.get('title', ''), 24 if index == 0 else 20, '标题')
        intro = short(page.get('intro', ''), 60, '导语')
        items = page.get('items', [])
        if not title or not isinstance(items, list) or len(items) > 3:
            raise ValueError('每页需有标题，且最多三个要点')
        clean = [{'label': short(item.get('label', ''), 12, '要点标题'), 'text': short(item.get('text', ''), 48, '要点说明')}
                 for item in items if isinstance(item, dict)]
        if len(clean) != len(items) or (index and (not clean or any(not item['text'] or not item['label'] for item in clean))):
            raise ValueError('组图页面缺少有效信息')
        if len(title + intro + ''.join(item['label'] + item['text'] for item in clean)) > 160:
            raise ValueError('单页文案超过160字，请拆分而非缩小字体')
        if kind == 'comparison' and len(clean) < 2:
            raise ValueError('对比页至少需要两个明确对象')
        art = short(page.get('art', ''), 800, '插画描述')
        if index and (len(clean) > 1 or kind == 'comparison'):
            art = ''
        if art_count >= 2:
            art = ''
        if art:
            art_count += 1
        result.append({'kind': kind, 'title': title, 'intro': intro, 'items': clean, 'art': art})
    if not result[0]['art']:
        result[0]['art'] = 'An editorial conceptual illustration about ' + result[0]['title']
        for page in result[2:]:
            page['art'] = ''
    return {'version': VERSION, 'style': STYLE, 'pages': result}


def plan(store, content):
    value = content.get('visual_plan')
    if value:
        return validate(value)
    if len(content['body']) > 6000:
        raise ValueError('组图请使用6000字以内的写作副本，原长文已保留')
    from .model import generate
    from .policy import local_day
    _, policy = store.policy()
    value = generate(store, policy, local_day(policy), '为现有稿件设计组图，只返回 visual_plan 对象。' + PROMPT,
                     {'title': content['title'], 'body': content['body'], 'source_ids': content.get('source_ids', [])}, manual=getattr(store, 'visual_manual', False))
    return validate(value.get('visual_plan', value))


def visible_copy(value):
    return '\n'.join(part for page in value['pages'] for part in
                     [page['title'], page['intro'], *[item['label'] + '：' + item['text'] for item in page['items']]] )


def art_prompt(page):
    return ('Create a premium editorial magazine illustration, calm ivory background, cobalt blue and warm orange accents, '
            'sophisticated tangible materials, intentional whitespace, strong single focal point, clean precise composition. '
            'This is a conceptual illustration, not a screenshot or photograph of a real event. Absolutely NO text, letters, '
            'numbers, logos, watermarks, interfaces, charts or decorative pseudo-writing. Landscape composition. Subject: ' + page['art'])
