"""Real SQLite collection flow with provider boundaries replaced by document fixtures."""
from copy import deepcopy
import json

from plugins.operations import collection, source_library
from plugins.operations.policy import DEFAULT
from plugins.operations.store import Store


def setup(tmp_path, monkeypatch, *, quota=10000):
    from tools import web_tools
    store = Store(tmp_path / 'collection.db')
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='收纳', goal='整理可靠收纳资料', sources=['https://example.org/a?utm_source=search#top'])
    policy['modules']['research'] = True
    policy['limits']['source'] = quota
    store.configure(policy, 0)
    monkeypatch.setattr(web_tools, 'web_search_tool', lambda *a, **k: '{"data":{"web":[]}}')
    return store, policy, web_tools


def test_login_shell_retries_in_place_and_keeps_failed_attempts_in_quota(tmp_path, monkeypatch):
    store, policy, web = setup(tmp_path, monkeypatch, quota=2)
    replies = iter(['请先登录，扫码登录后查看', '收纳步骤：先按使用频率分类，再标注位置。'])
    calls = []
    async def extract(urls, **kwargs):
        calls.append(urls)
        assert kwargs['include_metadata']
        return json.dumps({'results': [{'title': '收纳指南', 'content': next(replies), 'author': '作者'}]})
    monkeypatch.setattr(web, 'web_extract_tool', extract)
    failed = collection.collect(store, policy, '2026-11-01')
    identity = store.objects('source')[0]['id']
    assert failed['failed'] == 1 and not source_library.available_sources(store, policy, '2026-11-01')
    recovered = collection.collect(store, policy, '2026-11-01')
    rows = store.objects('source')
    assert len(rows) == 1 and rows[0]['id'] == identity and rows[0]['attempts'] == 2
    assert rows[0]['title'] == '收纳指南' and rows[0]['author'] == '作者'
    assert recovered['new'] == 1 and recovered['retried'] == 1 and recovered['used'] == 2
    exhausted = collection.collect(store, policy, '2026-11-01')
    assert exhausted['attempted'] == 0 and exhausted['reason']
    assert calls == [['https://example.org/a'], ['https://example.org/a']]
    assert source_library.catalog(store)['latest_collection']['reason']


def test_retries_stop_at_three_and_next_day_has_new_budget(tmp_path, monkeypatch):
    store, policy, web = setup(tmp_path, monkeypatch)
    async def extract(*a, **k):
        return json.dumps({'results': [{'content': 'error page', 'error': 'timeout'}]})
    monkeypatch.setattr(web, 'web_extract_tool', extract)
    for _ in range(3):
        assert collection.collect(store, policy, '2026-11-01')['failed'] == 1
    limited = collection.collect(store, policy, '2026-11-01')
    assert limited['not_attempted'] == 1 and limited['attempted'] == 0 and limited['used'] == 3
    assert collection.collect(store, policy, '2026-11-02')['used'] == 1
    assert all(not row['text'] for row in store.objects('source'))


def test_query_expansion_resumes_all_keywords_and_deduplicates_snapshots(tmp_path, monkeypatch):
    store, policy, web = setup(tmp_path, monkeypatch)
    policy['keywords'] = ['厨房', '书房', '客厅', '卧室']
    store.configure(policy, 1)
    calls = []
    def search(query, limit):
        calls.append((query, limit))
        return json.dumps({'data': {'web': [{'url': 'https://example.org/a?utm_source=other'},
                                          {'url': 'https://example.org/b?signature=a%2Fb'}]}})
    monkeypatch.setattr(web, 'web_search_tool', search)
    async def extract(urls, **kwargs):
        return json.dumps({'results': [{'content': '同一段  正文' if '/a' in urls[0] else '同一段 正文'}]})
    monkeypatch.setattr(web, 'web_extract_tool', extract)
    first = collection.collect(store, policy, '2026-11-01')
    assert first['succeeded'] == 2 and first['new'] == 1 and first['duplicate_content'] == 1
    for _ in range(7):
        collection.collect(Store(store.path), policy, '2026-11-01')
    assert any('卧室' in q for q, _ in calls)
    assert {limit for _, limit in calls} == {20, 50, 100}
    assert all('收纳' in q for q, _ in calls)
    assert len(source_library.available_sources(store, policy, '2026-11-01')) == 1
    assert any(row['url'].endswith('signature=a%2Fb') for row in store.objects('source'))
    assert collection.collect(store, policy, '2026-11-01')['attempted'] == 0


def test_unread_candidates_survive_restart_and_quota_increase(tmp_path, monkeypatch):
    store, policy, web = setup(tmp_path, monkeypatch, quota=1)
    monkeypatch.setattr(web, 'web_search_tool', lambda *a, **k: json.dumps({'data': {'web': [{'url': 'https://example.org/b'}]}}))
    calls = []
    async def extract(urls, **kwargs):
        calls.append(urls[0])
        return json.dumps({'results': [{'content': '有效资料 ' + urls[0]}]})
    monkeypatch.setattr(web, 'web_extract_tool', extract)
    first = collection.collect(store, policy, '2026-11-01')
    assert first['attempted'] == 1 and first['not_attempted'] == 1
    assert first['candidates'] == first['attempted'] + first['already_read'] + first['not_attempted']
    policy['limits']['source'] = 2
    store.configure(policy, 1)
    monkeypatch.setattr(web, 'web_search_tool', lambda *a, **k: '{"data":{"web":[]}}')
    second = collection.collect(Store(store.path), policy, '2026-11-01')
    assert second['new'] == 1 and second['used'] == 2 and calls[-1] == 'https://example.org/b'


def test_parallel_reservations_share_quota_and_pause_stops_new_reads(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import pytest
    from plugins.operations.collection_ledger import reserve
    store, policy, _ = setup(tmp_path, monkeypatch, quota=2)
    # Simulate an existing legacy source, before the attempt budget was introduced.
    store.put('source', {'day': '2026-11-01', 'url': 'https://example.org/legacy', 'text': '旧资料'})
    def request(index):
        return reserve(store, policy, '2026-11-01', f'https://example.org/{index}', None)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(request, range(4)))
    assert sum(result is not None for result in results) == 1
    store.configure({**policy, 'paused': True}, 1)
    with pytest.raises(ValueError, match='暂停'):
        collection.collect(store, policy, '2026-11-01')
    assert store.objects('collection_run')[0]['state'] == 'interrupted'
