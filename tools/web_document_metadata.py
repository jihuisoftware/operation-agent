"""Bounded metadata for internal document consumers; model-facing output stays compact."""
from urllib.parse import urljoin, urlsplit


def document_metadata(page):
    meta = page.get('metadata') if isinstance(page.get('metadata'), dict) else {}
    result = {}
    fields = {'author': ('author', 'authorName', 'creator'),
              'published_at': ('published_at', 'publishedDate', 'publishedTime', 'article:published_time', 'datePublished')}
    for key, aliases in fields.items():
        value = next((row[name] for row in (page, meta) for name in aliases if isinstance(row.get(name), str) and row[name].strip()), None)
        if value:
            result[key] = value[:1000]
    links = []
    for row in (page, meta):
        images = row.get('images', [])
        if isinstance(images, list):
            links.extend(image.get('url', image.get('src')) if isinstance(image, dict) else image for image in images[:12])
        links.extend(row.get(k) for k in ('image', 'image_url', 'thumbnail', 'ogImage', 'og:image'))
    result['images'] = image_links(links, page.get('url', ''))
    return result


def image_links(links, base):
    urls = []
    for value in links:
        if not isinstance(value, str) or not value or len(value) > 4000:
            continue
        try:
            url = urljoin(base, value)
            parsed = urlsplit(url)
        except ValueError:
            continue
        if parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username and not parsed.password and url not in urls:
            urls.append(url)
    return urls[:12]
