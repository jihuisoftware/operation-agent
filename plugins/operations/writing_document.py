"""Versioned rich-document validation and deterministic plain-text publication projection."""
import json
from urllib.parse import urlsplit

SCHEMA_VERSION = 1
MAX_BYTES, MAX_TEXT, MAX_NODES = 2 * 1024 * 1024, 100_000, 20_000
BLOCKS = {'paragraph', 'heading', 'blockquote', 'bulletList', 'orderedList', 'codeBlock', 'horizontalRule', 'table', 'image', 'uploadPlaceholder'}
CHILDREN = {'doc': BLOCKS, 'paragraph': {'text', 'hardBreak'}, 'heading': {'text', 'hardBreak'},
            'blockquote': BLOCKS, 'bulletList': {'listItem'}, 'orderedList': {'listItem'}, 'listItem': BLOCKS,
            'codeBlock': {'text'}, 'table': {'tableRow'}, 'tableRow': {'tableCell', 'tableHeader'},
            'tableCell': BLOCKS - {'table'}, 'tableHeader': BLOCKS - {'table'}}
ATTRS = {'paragraph': {'textAlign'}, 'heading': {'level', 'textAlign'}, 'orderedList': {'start', 'type'},
         'codeBlock': {'language'}, 'image': {'assetId', 'alt'}, 'uploadPlaceholder': {'id', 'name', 'state'},
         'tableCell': {'colspan', 'rowspan', 'colwidth'}, 'tableHeader': {'colspan', 'rowspan', 'colwidth'}}
MARKS = {'bold', 'italic', 'underline', 'strike', 'code', 'highlight', 'link'}


def safe_link(value):
    if not isinstance(value, str) or len(value) > 2000:
        raise ValueError('链接格式无效')
    parsed = urlsplit(value)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError('仅支持不含凭据的 HTTP(S) 链接')
    return value


def attributes(kind, attrs):
    if not isinstance(attrs, dict) or set(attrs) - ATTRS.get(kind, set()):
        raise ValueError('文档属性不受支持')
    for key, value in attrs.items():
        if value is None:
            continue
        if key == 'textAlign' and value not in {'left', 'center', 'right', 'justify'}:
            raise ValueError('段落对齐方式无效')
        if key in {'level', 'start', 'colspan', 'rowspan'} and (type(value) is not int or not 1 <= value <= (3 if key == 'level' else 1000)):
            raise ValueError('文档层级或表格参数无效')
        if key == 'colwidth' and (not isinstance(value, list) or len(value) > 100 or any(type(width) is not int or not 1 <= width <= 4000 for width in value)):
            raise ValueError('表格列宽无效')
        if key in {'assetId', 'id', 'name', 'state', 'alt', 'language', 'type'} and (not isinstance(value, str) or len(value) > 300):
            raise ValueError('文档属性文字过长或格式无效')
    return dict(attrs)


def marks(items):
    if not isinstance(items, list) or len(items) > 8:
        raise ValueError('文字格式无效')
    clean = []
    for item in items:
        if not isinstance(item, dict) or item.get('type') not in MARKS or set(item) - {'type', 'attrs'}:
            raise ValueError('不支持的文字格式')
        attrs = item.get('attrs') or {}
        if not isinstance(attrs, dict):
            raise ValueError('文字格式属性无效')
        if item['type'] == 'link':
            href = safe_link(attrs.get('href'))
            clean.append({'type': 'link', 'attrs': {'href': href}})
        elif item['type'] == 'highlight':
            if attrs.get('color') not in (None, '#fff3a3', '#c7e8ff', '#d6f5d6'):
                raise ValueError('高亮颜色不受支持')
            clean.append({'type': 'highlight', 'attrs': {'color': attrs.get('color')}})
        else:
            clean.append({'type': item['type']})
    return clean


def validate(document):
    if not isinstance(document, dict) or document.get('type') != 'doc':
        raise ValueError('富文本文档格式无效')
    try:
        size = len(json.dumps(document, ensure_ascii=False, allow_nan=False).encode())
    except (RecursionError, TypeError) as exc:
        raise ValueError('文档层级或格式无效') from exc
    if size > MAX_BYTES:
        raise ValueError('草稿文档超过 2 MiB 上限')
    totals = {'nodes': 0, 'text': 0}

    def visit(node, parent, depth):
        totals['nodes'] += 1
        if depth > 32 or totals['nodes'] > MAX_NODES or not isinstance(node, dict):
            raise ValueError('文档层级或节点数量超过上限')
        kind = node.get('type')
        if (parent and kind not in CHILDREN.get(parent, set())) or set(node) - {'type', 'attrs', 'content', 'text', 'marks'}:
            raise ValueError('文档包含不支持的节点')
        result = {'type': kind}
        if 'attrs' in node:
            result['attrs'] = attributes(kind, node['attrs'])
        if kind == 'text':
            if not isinstance(node.get('text'), str) or not node['text']:
                raise ValueError('文档文字格式无效')
            totals['text'] += len(node['text'])
            result['text'] = node['text']
        elif 'text' in node:
            raise ValueError('文字必须放在文字节点中')
        if 'marks' in node:
            if kind not in {'text', 'hardBreak'}:
                raise ValueError('此节点不能使用文字格式')
            result['marks'] = marks(node['marks'])
        children = node.get('content', [])
        if not isinstance(children, list):
            raise ValueError('文档子节点格式无效')
        if kind in {'doc', 'blockquote', 'bulletList', 'orderedList', 'listItem', 'table', 'tableRow', 'tableCell', 'tableHeader'} and not children:
            raise ValueError('文档容器不能为空')
        if kind == 'listItem' and children[0].get('type') != 'paragraph':
            raise ValueError('列表项应以段落开始')
        if children:
            result['content'] = [visit(child, kind, depth + 1) for child in children]
        return result

    cleaned = visit(document, None, 0)
    if totals['text'] > MAX_TEXT:
        raise ValueError('正文超过 10 万字符上限')
    return cleaned


def inline(nodes):
    parts, buffer, current = [], '', ''
    for node in nodes:
        href = next((m['attrs']['href'] for m in node.get('marks', []) if m['type'] == 'link'), '')
        if href != current or node['type'] == 'hardBreak':
            parts.append(buffer + (f'（{current}）' if current and buffer != current else ''))
            buffer, current = '', href
        if node['type'] == 'hardBreak':
            parts.append('\n')
        else:
            buffer += node.get('text', '')
    parts.append(buffer + (f'（{current}）' if current and buffer != current else ''))
    return ''.join(parts)


def project(document, cover_asset_id=''):
    assets, warnings = [], set()
    pending = []

    def block(node):
        kind, children = node['type'], node.get('content', [])
        attrs = node.get('attrs', {})
        if kind in {'paragraph', 'heading', 'codeBlock'}:
            if kind != 'paragraph':
                warnings.add('标题和代码块将按普通文本发布')
            return inline(children)
        if kind == 'image':
            identity = attrs.get('assetId')
            if identity:
                assets.append(identity)
            else:
                pending.append('未导入图片')
            return ''
        if kind == 'uploadPlaceholder':
            pending.append(attrs.get('name') or '未上传图片')
            return ''
        if kind in {'bulletList', 'orderedList'}:
            rows = []
            for index, child in enumerate(children):
                prefix = f"{(attrs.get('start') or 1) + index}. " if kind == 'orderedList' else '• '
                lines = block(child).split('\n')
                rows.append(prefix + ('\n' + ' ' * len(prefix)).join(lines))
            return '\n'.join(rows)
        if kind == 'table':
            warnings.add('表格将按行转换为普通文本')
            return '\n'.join(block(child) for child in children)
        if kind == 'tableRow':
            return ' | '.join(block(child).replace('\n', ' / ') for child in children)
        if kind == 'horizontalRule':
            return '——'
        separator = '\n' if kind in {'listItem', 'tableCell', 'tableHeader'} else '\n\n'
        return separator.join(value for child in children if (value := block(child)))

    body = block(document)
    ordered = list(dict.fromkeys(([cover_asset_id] if cover_asset_id else []) + assets))
    return {'body': body, 'asset_ids': ordered, 'pending_images': pending,
            'body_characters': len(body), 'warnings': sorted(warnings | {'字体、颜色等样式不在当前发布通道中保留'})}


def from_plain(body, asset_ids=()):
    nodes = []
    for index, line in enumerate(body.split('\n')):
        if index:
            nodes.append({'type': 'hardBreak'})
        if line:
            nodes.append({'type': 'text', 'text': line})
    return {'type': 'doc', 'content': [{'type': 'paragraph', 'content': nodes},
        *[{'type': 'image', 'attrs': {'assetId': identity, 'alt': ''}} for identity in asset_ids]]}
