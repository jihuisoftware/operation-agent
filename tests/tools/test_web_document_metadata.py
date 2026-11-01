"""Internal document consumers retain provider metadata across the real extract cache."""
import asyncio
import json

from tools import web_tools, web_result_cache


def test_metadata_survives_extract_and_cache_without_expanding_model_output(tmp_path, monkeypatch):
    monkeypatch.setattr(web_result_cache, '_cache_dir', lambda: tmp_path)
    monkeypatch.setattr(web_result_cache, '_web_config', dict)
    monkeypatch.setattr(web_tools, '_ensure_web_plugins_loaded', lambda: None)
    monkeypatch.setattr(web_tools, '_get_extract_backend', lambda: 'fake')
    async def safe(*args):
        return True
    monkeypatch.setattr(web_tools, 'async_is_safe_url', safe)
    calls = []
    class Provider:
        name = 'fake'
        display_name = 'Fake'
        def supports_extract(self):
            return True
        async def extract(self, urls, **kwargs):
            calls.append(urls)
            return [{'url': urls[0], 'title': '资料', 'content': '资料正文' * 1000,
                     'metadata': {'author': '作者', 'publishedTime': '2026-11-01', 'og:image': '/cover.png',
                                  'internal_secret': 'never expose'}}]
    monkeypatch.setattr('agent.web_search_registry.get_provider', lambda *_: Provider())
    url = 'https://example.com/article'
    def extract(**kwargs):
        return json.loads(asyncio.run(web_tools.web_extract_tool([url], char_limit=1000, **kwargs)))['results'][0]
    first = extract(include_metadata=True)
    cached = extract(include_metadata=True)
    for page in (first, cached):
        assert page['author'] == '作者' and page['published_at'] == '2026-11-01'
        assert page['images'] == ['https://example.com/cover.png']
        assert page['truncated'] and page['original_chars'] == 4000
        assert 'internal_secret' not in page
    assert len(calls) == 1
    compact = extract()
    assert 'author' not in compact and 'images' not in compact and 'truncated' not in compact

    web_result_cache.extract_cache_invalidate(url)
    assert extract(include_metadata=True)['author'] == '作者'
    assert len(calls) == 2
