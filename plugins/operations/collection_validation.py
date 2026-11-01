"""Conservative URL deduplication and rejection of unusable document shells."""
import hashlib
import re
from urllib.parse import unquote_plus, urlsplit, urlunsplit

from .policy import public_url


def canonical_url(value):
    parts = urlsplit(public_url(value))
    query = '&'.join(part for part in parts.query.split('&') if part and not tracking_key(part))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, query, ''))


def tracking_key(part):
    key = unquote_plus(part.split('=', 1)[0]).lower()
    return key.startswith('utm_') or key in {'fbclid', 'gclid'}


def fingerprint(text):
    body = text.split('\n──────── [TRUNCATED] ────────', 1)[0]
    return hashlib.sha256(' '.join(body.split()).encode()).hexdigest() if body else None


def document(page, error=None):
    text = page.get('content') or page.get('markdown') or page.get('text') or ''
    reason = page.get('error') or error
    if page.get('blocked_by_policy'):
        reason = reason or '网站读取规则禁止访问'
    if not isinstance(text, str) or not text.strip():
        return '', str(reason or '未取得正文')
    if reason:
        return '', str(reason)
    compact = re.sub(r'\s+', ' ', text).strip().lower()
    markers = ('请完成验证', '请先登录', '扫码登录', '安全验证', '访问过于频繁',
               '当前笔记暂时无法浏览', 'access denied', 'verify you are human',
               'captcha', 'sign in to continue', '404 not found')
    # A substantive article can discuss authentication; only reject short shells.
    if len(compact) < 600 and any(marker in compact for marker in markers):
        return '', '页面要求登录、验证或访问受限，未作为正文保存'
    return text, None
