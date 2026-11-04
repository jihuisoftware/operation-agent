"""Keep raw extraction, clean known page chrome, and repair incomplete documents within read budgets."""
import asyncio
import hashlib
import json
import re

import httpx

from .collection_ledger import check, reserve, save
from .collection_validation import document, fingerprint
from .policy import now_iso
from .store import encoded

EXTRACT_LIMIT = 500_000
DOCUMENT_VERSION = 1
FOOTER = '\n──────── [TRUNCATED] ────────'
AUTH_BLOCK = re.compile(r'(?m)^(?:其他扫码方式[^\n]*|下载知乎\s*App|扫码下载知乎\s*App|验证码登录)\s*\n(?:(?!^##? ).*\n){0,60}?关闭二维码\s*(?:\n|$)')


def clean_text(raw):
    body = raw.split(FOOTER, 1)[0]
    def remove(match):
        value = match.group()
        return '' if sum(marker in value for marker in ('验证码登录', '密码登录', '获取短信验证码', '下载知乎', '隐私保护指引')) >= 3 else value
    return AUTH_BLOCK.sub(remove, body).strip()


def prepared(raw, *, truncated=False, original_chars=None):
    text = clean_text(raw)
    incomplete = bool(truncated or FOOTER in raw)
    revision = hashlib.sha256(encoded([text, incomplete]).encode()).hexdigest()
    return {'text': text, 'raw_text': raw, 'document_version': DOCUMENT_VERSION, 'text_revision': revision,
            'truncated': incomplete, 'original_chars': original_chars or len(raw), 'fingerprint': fingerprint(text)}


def requires_repair(source):
    return source.get('truncated', False) or FOOTER in source.get('text', '')


def _allowance(store):
    limit = (store.run_options or {}).get('read_limit')
    if limit is None:
        return float('inf')
    batch = getattr(store, 'debug_id', None) or store.manual_run_id
    used = sum(row.get('attempted', 0) for row in store.objects('collection_run')
               if batch and batch in {row.get('debug_id'), row.get('manual_run_id')})
    return max(0, limit - used)


def repair_sources(store, policy, day, sources):
    allowance = _allowance(store)
    for source in sources:
        if source.get('document_version') == DOCUMENT_VERSION and not requires_repair(source):
            continue
        old_text = source.get('text', '')
        if not old_text:
            continue
        needs_fetch = requires_repair(source)
        if not needs_fetch and clean_text(old_text) == old_text:
            continue
        if needs_fetch:
            if allowance <= 0:
                continue
            attempt = reserve(store, policy, day, source['url'])
            if attempt is None:
                continue
            allowance -= 1
            from tools.web_tools import web_extract_tool
            try:
                data = json.loads(asyncio.run(web_extract_tool([source['url']], char_limit=EXTRACT_LIMIT, include_metadata=True)))
                page = (data.get('results') or [{}])[0]
                raw, error = document(page, data.get('error'))
            except (OSError, ValueError, httpx.HTTPError) as exc:
                raw, error, page = '', str(exc), {}
            check(store, policy)
            store.event('source_repair_attempt', {'day': day, 'source_id': source['id'], 'attempt': attempt,
                                                 'error': error, 'complete': bool(raw and not page.get('truncated'))})
            if error:
                continue
            projection = prepared(raw, truncated=page.get('truncated', False), original_chars=page.get('original_chars'))
        else:
            projection = prepared(source.get('raw_text', old_text), original_chars=source.get('original_chars'))
        if projection['truncated'] or not projection['text']:
            continue
        archive = 'source-revision:' + source['id'] + ':' + hashlib.sha256(encoded(source).encode()).hexdigest()
        store.put('source_revision', {**source, 'source_id': source['id'], 'archived_at': now_iso()}, archive)
        updated = {**source, **projection, 'summary': '', 'previous_revision': archive, 'repaired_at': now_iso()}
        save(store, 'source', source['id'], updated)
        store.event('source_repaired', {'day': day, 'source_id': source['id'], 'revision': projection['text_revision']})
