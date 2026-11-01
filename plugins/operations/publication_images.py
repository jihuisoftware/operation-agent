"""Exact image evidence; CDN transformations are reported as unverified, never guessed equal."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
import hashlib
import json
import time
from urllib.parse import urlsplit
import httpx
from .source_media import download


def image_bytes(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not (parsed.hostname or '').endswith('.xhscdn.com') or parsed.username or parsed.password:
        raise ValueError('只核对小红书图片地址')
    return download(url, max_bytes=20 * 1024 * 1024)


def verify_images(store, command_id, worker, urls):
    with store.connection() as db:
        command = db.execute("SELECT * FROM commands WHERE id=? AND worker=? AND state='running' AND expires>?",
                             (command_id, worker, time.time())).fetchone()
    if not command or command['kind'] not in {'publish', 'verify'}:
        raise ValueError('图片核对任务不属于当前执行者')
    if not isinstance(urls, list) or not 1 <= len(urls) <= 18 or not all(isinstance(u, str) and len(u) < 4000 for u in urls):
        return {'state': 'incomplete', 'evidence': '未取得完整图片列表'}
    payload = json.loads(command['payload'])
    expected = payload.get('content', {}).get('asset_ids', [])
    assets = {a['id']: a for a in store.objects('asset') if a.get('authorized') and not a.get('revoked')}
    authorized = set(assets)
    if not expected or not set(expected) <= authorized or len(urls) != len(expected):
        return {'state': 'incomplete', 'evidence': '图片数量、素材授权或版本不完整'}
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(copy_context().run, inspect_image, store, payload, assets[asset_id], url) for asset_id, url in zip(expected, urls)]
            results = [future.result() for future in futures]
            hashes = [result['hash'] for result in results]
    except (ValueError, OSError, httpx.HTTPError) as exc:
        return {'state': 'incomplete', 'evidence': '无法下载核对平台图片：' + type(exc).__name__}
    if hashes != expected:
        comparisons = [result['comparison'] for result in results if result.get('comparison')]
        return {'state': 'incomplete', 'evidence': '图片发生转码或内容变化，无法按原文件精确核对', 'hashes': hashes, 'comparisons': comparisons}
    return {'state': 'matched', 'evidence': '全部平台图片按顺序与授权原图 SHA-256 一致', 'hashes': hashes}


def inspect_image(store, payload, asset, url):
    from .image_comparison import reference, thumbnail
    from .browser_evidence import screenshot
    from PIL import Image
    raw = image_bytes(url)
    digest = hashlib.sha256(raw).hexdigest()
    if digest == asset['id']:
        return {'hash': digest}
    result = {'asset_id': asset['id'], **reference(asset, raw)}
    try:
        identity, data = screenshot(thumbnail(raw))
        store.put('browser_evidence', {'image': data, 'action_id': payload.get('verification_action_id'), 'purpose': 'image_comparison'}, identity)
        result['evidence_id'] = identity
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        result['preview_error'] = type(exc).__name__
    return {'hash': digest, 'comparison': result}
