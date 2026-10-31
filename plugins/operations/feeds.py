"""Bounded RSS/Atom reader using the host's connect-time SSRF guard."""
from urllib.parse import urljoin
from xml.etree import ElementTree


def feed_entries(url):
    from tools.url_safety import create_ssrf_safe_client, is_safe_url
    if not is_safe_url(url):
        raise ValueError("RSS 地址不能访问")
    with create_ssrf_safe_client(timeout=20, follow_redirects=False) as client:
        for _ in range(5):
            with client.stream("GET", url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers["location"])
                    if not is_safe_url(url):
                        raise ValueError("RSS 跳转地址不能访问")
                    continue
                response.raise_for_status()
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 1024 * 1024:
                        raise ValueError("RSS 超过 1 MB")
                    chunks.append(chunk)
                return parse_feed(b"".join(chunks), url)
    raise ValueError("RSS 跳转次数过多")


def parse_feed(data, base):
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("不支持含实体声明的 RSS")
    root = ElementTree.fromstring(data)
    entries = []
    for item in root.iter():
        if item.tag.rsplit("}", 1)[-1] not in {"item", "entry"}:
            continue
        fields = {child.tag.rsplit("}", 1)[-1]: child for child in item}
        link = fields.get("link")
        if link is None:
            continue
        url = link.attrib.get("href") or link.text or ""
        def value(key):
            element = fields.get(key)
            return "".join(element.itertext()).strip() if element is not None else None
        entries.append({"url": urljoin(base, url), "title": value("title") or url,
                        "author": value("author") or value("creator"),
                        "published_at": value("pubDate") or value("published") or value("updated")})
        if len(entries) == 100:
            break
    return entries
