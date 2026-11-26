"""Discovery rotation, conservative revisit and evidence lineage through real SQLite stores."""
from copy import deepcopy
from datetime import date, timedelta
import json

import pytest

from plugins.operations import collection, collection_language, organization, topics
from plugins.operations.collection_ledger import reserve
from plugins.operations.policy import DEFAULT
from plugins.operations.store import Store
from tests.plugins.operations_support import organized_response


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    store = Store()
    policy = deepcopy(DEFAULT)
    policy.update(enabled=True, topic='AI Agent 实践', goal='查官方文档与原始论文', keywords=['工具调用', 'RAG', '评测'])
    policy['modules'].update(research=True, organize=True, topics=True)
    store.configure(policy, 0)
    suggestions, searches, reads = [], [], []

    def suggest(*args):
        suggestions.append(args[-1])
        return {'needed': True, 'reason': '需要官方原始资料', 'terms': [
            {'keyword': '工具调用', 'queries': ['LLM agent tool calling evaluation', 'tool calling papers']},
            {'keyword': '评测', 'queries': ['agent benchmark research']},
            {'keyword': '不存在', 'queries': ['foreign query']}]}

    def search(query, limit):
        searches.append(query)
        return json.dumps({'data': {'web': [{'url': 'https://example.org/paper'}]}})

    async def extract(urls, **_):
        reads.extend(urls)
        return json.dumps({'results': [{'title': 'API release', 'content':
            'The new RAG API v2 is limited to 12 requests per minute for trial users.'}]})
    monkeypatch.setattr(collection_language, 'generate', suggest)
    monkeypatch.setattr('tools.web_tools.web_search_tool', search)
    monkeypatch.setattr('tools.web_tools.web_extract_tool', extract)
    return store, policy, suggestions, searches, reads


def test_seven_days_rotate_languages_and_do_not_invent_sources_on_deferred_days(setup):
    store, policy, suggestions, searches, reads = setup
    batches = []
    for i in range(7):
        day = (date(2026, 11, 1) + timedelta(days=i)).isoformat()
        batches.append(collection.collect(Store(store.path), policy, day))
    assert len(suggestions) == 1 and len(set(searches)) > 12
    for batch in batches:
        assert batch['searches'] == 12 and sum(q['language'] == 'en' for q in batch['queries']) == 3
        assert all('site:' not in q['query'] for q in batch['queries'] if q['language'] == 'en')
    assert [b['attempted'] for b in batches] == [1, 1, 0, 0, 1, 0, 0]
    assert batches[2]['deferred_rechecks'] == 1 and batches[2]['used'] == 0
    assert len(reads) == len(store.objects('source')) == 3
    row = store.objects('source')[0]
    assert row['document_language'] == 'en'
    assert {o['language'] for o in row['origins']} == {'en', 'zh'}
    assert store.policy()[1]['keywords'] == policy['keywords']


def test_one_slot_rotation_and_plan_cache_invalidation(setup):
    store, policy, suggestions, _, _ = setup
    store.run_options = {'query_limit': 1, 'read_limit': 1}
    actual = [collection.collect(store, policy, '2026-11-01')['queries'][0] for _ in range(4)]
    assert [q['language'] for q in actual] == ['zh', 'zh', 'zh', 'en']
    assert len({q['query'] for q in actual}) == 4
    policy = {**policy, 'keywords': ['RAG']}
    store.configure(policy, 1)
    row = collection.collect(store, policy, '2026-11-02')
    assert len(suggestions) == 2 and all(q['keyword'] != '工具调用' for q in row['queries'])
    assert collection_language.intent({**policy, 'topic': '本地生活', 'goal': '到店体验'})[0] == 'zh'


def test_model_failure_reuses_english_names_without_retry_or_user_policy_changes(setup, monkeypatch):
    store, policy, _, _, _ = setup
    tried = []
    def offline(*args):
        tried.append(True)
        raise collection_language.ModelServiceUnavailable('offline')
    monkeypatch.setattr(collection_language, 'generate', offline)
    first = collection.collect(store, policy, '2026-11-01')
    collection.collect(store, policy, '2026-11-01')
    assert len(tried) == 1 and any(q['query'] == 'RAG' for q in first['queries'])
    store.configure({**policy, 'model_calls': 0, 'goal': '仅查英文'}, 1)
    result = collection.collect(store, store.policy()[1], '2026-11-02')
    assert result['queries'] and all(q['language'] == 'en' for q in result['queries'])
    assert len(tried) == 1


def test_cross_day_binding_costs_no_call_and_topics_reference_todays_original(setup, monkeypatch):
    store, policy, *_ = setup
    calls = []
    def summarize(*args):
        calls.append(args[-1])
        row = organized_response(args[-1])
        row['items'][0]['facts'] = ['RAG API v2 的试用用户上限是每分钟 12 次']
        return row
    monkeypatch.setattr(organization, 'generate', summarize)
    for day in ('2026-11-01', '2026-11-02'):
        collection.collect(store, policy, day)
        r = organization.organize(store, policy, day, 1)
    assert len(calls) == 1 and r['added'] == 0 and r['reused'] == 1
    source = store.objects('source', day)[0]
    sources, evidence = organization.production_evidence(store, policy, day)
    assert [s['id'] for s in sources] == [source['id']]
    assert evidence[0]['facts'] == ['RAG API v2 的试用用户上限是每分钟 12 次']
    assert '12 requests per minute for trial users' in source['text']
    captured = []
    def propose(*args):
        captured.append(args[-1])
        return {'topics': [{'title': '试用额度解读', 'reason': '发布说明', 'source_ids': [source['id']]}]}
    monkeypatch.setattr(topics, 'generate', propose)
    topics.generate_topics(store, policy, day, 1)
    assert captured[0]['sources'][0]['id'] == source['id']
    assert store.objects('brief', day)[0]['result']['topics'][0]['source_ids'] == [source['id']]
    assert store.objects('organized_source', day)[0]['reused_from']


def test_url_reservation_prevents_simultaneous_double_charge(setup):
    store, policy, *_ = setup
    url = 'https://example.org/shared'
    def claim(token):
        return reserve(store, policy, '2026-11-01', url, claim=token)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(claim, ['a', 'b'])).count(1) == 1
    assert store.objects('collection_budget')[0]['used'] == 1


def test_rss_signal_can_recheck_today_preserving_both_revisions_and_metadata(setup, monkeypatch):
    store, policy, *_ = setup
    feed = 'https://example.org/feed'
    policy = {**policy, 'rss_sources': [feed]}
    store.configure(policy, 1)
    stamp = ['01:00']
    monkeypatch.setattr('plugins.operations.feeds.feed_entries', lambda _: [{
        'url': 'https://example.org/paper', 'published_at': 'original-date', 'feed_updated': stamp[0]}])
    async def extract(urls, **_):
        return json.dumps({'results': [{'content': 'Source revision ' + stamp[0]}]})
    monkeypatch.setattr('tools.web_tools.web_extract_tool', extract)
    day = '2026-11-01'
    collection.collect(store, policy, day)
    stamp[0] = '12:00'
    result = collection.collect(store, policy, day)
    assert result['changed'] == result['rechecks'] == 1
    sources = store.objects('source', day)
    assert len(sources) == 2 and sources[0]['previous_url_source_id'] == sources[1]['id']
    assert sources[0]['published_at'] == 'original-date' and sources[0]['feed_updated'] == '12:00'
    assert collection.collect(store, policy, day)['attempted'] == 0


def test_pending_urls_expire_and_removed_keyword_cannot_authorize_old_candidates(setup, monkeypatch):
    store, policy, *_ = setup
    monkeypatch.setattr('tools.web_tools.web_search_tool', lambda query, **_: json.dumps({'data': {'web': [
        {'url': 'https://example.org/pending'}] if query == 'LLM agent tool calling evaluation' else []}}))
    store.run_options = {'read_limit': 0}
    assert collection.collect(store, policy, '2026-11-01')['candidates'] == 1
    monkeypatch.setattr('tools.web_tools.web_search_tool', lambda *a, **kw: '{"data":{"web":[]}}')
    other = {**policy, 'keywords': ['RAG']}
    store.configure(other, 1)
    assert collection.collect(store, other, '2026-11-02')['candidates'] == 0
    store.configure(policy, 2)
    assert collection.collect(store, policy, '2026-11-07')['candidates'] == 1
    assert collection.collect(store, policy, '2026-11-08')['candidates'] == 0


def test_legacy_reads_initialize_history_and_fixed_urls_remain_daily(setup, monkeypatch):
    store, policy, *_ = setup
    url = 'https://example.org/paper'
    store.put('source', {'url': url, 'title': 'Old', 'day': '2026-11-01', 'text': 'old snapshot'}, 'legacy')
    p = {**policy, 'sources': [url]}
    store.configure(p, 1)
    for day in ('2026-11-02', '2026-11-03', '2026-11-04'):
        result = collection.collect(Store(store.path), p, day)
        assert result['rechecks'] == 1 and result['new_reads'] == 0
    second = store.objects('source', '2026-11-02')[0]
    assert second['previous_url_source_id'] == 'legacy'
    separate = Store(store.path.parent / 'other-topic.db')
    separate.configure(p, 0)
    assert collection.collect(separate, p, '2026-11-04')['new'] == 1


def test_explicit_chinese_theme_never_requests_a_translation_and_paused_run_cannot_search(setup):
    store, policy, suggestions, searches, reads = setup
    local = {**policy, 'goal': '仅查中文', 'keywords': ['GPT']}
    store.configure(local, 1)
    batch = collection.collect(store, local, '2026-11-01')
    assert not suggestions and all(q['language'] == 'zh' for q in batch['queries'])
    counts = (len(searches), len(reads))
    store.configure({**local, 'paused': True}, 2)
    with pytest.raises(ValueError, match='暂停'):
        collection.collect(store, local, '2026-11-02')
    assert counts == (len(searches), len(reads))


def test_daily_allocation_and_primary_sources_within_one_search():
    from plugins.operations.collection_revisit import ordered
    def found(url):
        return {'url': url, 'origins': [{'type': 'search', 'query': 'RAG paper', 'language': 'en'}]}
    urls = {url: found(url) for url in [*(f'https://docs.example.org/papers/{i}' for i in range(30)),
                                         *(f'https://example.org/old/{i}' for i in range(10))]}
    history = {url: {'feed_updated': None, 'next_day': '2026-11-02', 'last_day': '2026-11-01'}
               for url in urls if '/old/' in url}
    stats = dict(rechecks=0, attempted=0)
    for url, row in ordered(urls, history, {}, '2026-11-02', stats, 0, 0):
        stats['attempted'] += 1
        stats['rechecks'] += url in history
        if stats['attempted'] == 20:
            break
    assert stats == {'attempted': 20, 'rechecks': 4}


def test_weekly_counts_use_cited_document_language_not_query_language(setup, monkeypatch):
    from plugins.operations import collection_report
    store, policy, *_ = setup
    day = '2026-11-02'
    collection.collect(store, policy, day)
    source = store.objects('source', day)[0]
    store.put('brief', {'day': day, 'scope_topic': policy['topic'], 'result': {'topics': [{'source_ids': [source['id']]}]}})
    monkeypatch.setattr(collection_report, 'local_day', lambda _: day)
    result = collection_report.report(store)
    assert result['attempted'] == 1 and result['new_per_100'] == 100
    assert result['cited_english'] == 1 and result['cited_unknown_language'] == 0
    assert '工具调用' in result['keywords']


@pytest.mark.parametrize('difference', ['revision', 'published_at', 'url', 'incomplete'])
def test_reuse_requires_matching_complete_evidence(setup, monkeypatch, difference):
    store, policy, *_ = setup
    first_day, second_day = '2026-11-01', '2026-11-02'
    source = {'day': first_day, 'scope_topic': policy['topic'], 'url': 'https://example.org/releases/1',
              'title': 'Release 1', 'text': 'The service is limited to 12 requests per minute.', 'published_at': first_day}
    store.put('source', source, 'one')
    calls = []
    def summarize(*args):
        calls.append(1)
        return organized_response(args[-1])
    monkeypatch.setattr(organization, 'generate', summarize)
    organization.organize(store, policy, first_day, 1)
    second = {**source, 'day': second_day}
    if difference == 'incomplete':
        with store.connection() as db:
            db.execute("UPDATE objects SET data=json_set(data,'$.format_incomplete',1) WHERE kind='organized_source'")
    elif difference == 'revision':
        second['text'] = second['text'].replace('12', '18')
    elif difference == 'url':
        second['url'] += '/copy'
    else:
        second['published_at'] = second_day
    store.put('source', second, 'two')
    result = organization.organize(store, policy, second_day, 1)
    assert result['reused'] == 0 and len(calls) == 2
    assert organization.production_evidence(store, policy, second_day)[1][0]['id'] == 'two'
