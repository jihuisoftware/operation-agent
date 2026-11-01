"""Bounded local reference-image snapshots; collecting an image grants no publishing rights."""
import hashlib
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
import re
from urllib.parse import urljoin

import httpx
from PIL import Image

from .policy import now_iso, public_url


class ImageLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "img":
            self.urls.append(values.get("src") or values.get("data-src"))
        if tag == "meta" and values.get("property", values.get("name")) in {"og:image", "twitter:image"}:
            self.urls.append(values.get("content"))


def image_urls(page, candidate, base, text):
    links = []
    for record in (page, candidate, page.get("metadata") or {}):
        if not isinstance(record, dict):
            continue
        images = record.get("images") or []
        if isinstance(images, list):
            links.extend(item.get("url", item.get("src")) if isinstance(item, dict) else item for item in images)
        links.extend(record.get(key) for key in ("image", "image_url", "thumbnail", "ogImage", "og:image"))
    links.extend(re.findall(r'!\[[^\]]*\]\(\s*<?([^\s)>]+)>?(?:\s+[^)]*)?\)', text))
    parser = ImageLinks()
    parser.feed(str(page.get("html") or "")[:100_000] + text)
    links.extend(parser.urls)
    urls = []
    for link in links:
        if not isinstance(link, str) or not link.strip():
            continue
        try:
            url = public_url(urljoin(base, link.strip()))
        except ValueError:
            continue
        if url not in urls:
            urls.append(url)
    return urls[:12]


def directory(store):
    from plugins.plugin_storage import plugin_data_dir
    return (Path(store.path).parent if store.path else plugin_data_dir("operations")) / "reference-images"


def download(url):
    from tools.url_safety import create_ssrf_safe_client, is_safe_url
    with create_ssrf_safe_client(timeout=8, follow_redirects=False) as client:
        for _ in range(4):
            if not is_safe_url(url):
                raise ValueError("图片地址不可访问")
            with client.stream("GET", url) as response:
                if response.is_redirect:
                    url = public_url(urljoin(url, response.headers["location"]))
                    continue
                response.raise_for_status()
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 2 * 1024 * 1024:
                        raise ValueError("参考图片超过 2 MB")
                    chunks.append(chunk)
                return b"".join(chunks)
    raise ValueError("图片跳转次数过多")


def save_image(store, url):
    payload = download(url)
    with Image.open(BytesIO(payload)) as picture:
        if picture.format not in {"PNG", "JPEG", "WEBP"} or picture.width * picture.height > 20_000_000:
            raise ValueError("参考图片格式或尺寸不支持")
        mime = Image.MIME[picture.format]
        picture.verify()
    identity = hashlib.sha256(payload).hexdigest()
    path = directory(store)
    path.mkdir(parents=True, exist_ok=True)
    (path / identity).write_bytes(payload)
    store.put("source_image", {"file": identity, "mime": mime, "url": url, "captured_at": now_iso(),
                               "authorized": False, "usage": "reference_only"}, identity)
    return identity


def capture(store, urls, source_url):
    images = []
    for index, url in enumerate(urls):
        row = {"url": url, "state": "link_only", "authorized": False}
        if index < 3:
            store.renew()
            try:
                row.update(id=save_image(store, url), state="saved")
            except (ValueError, OSError, httpx.HTTPError, Image.DecompressionBombError) as exc:
                row.update(state="unavailable", error=str(exc))
                store.event("source_image_error", {"url": url, "source_url": source_url, "error": str(exc)})
        images.append(row)
    return images
