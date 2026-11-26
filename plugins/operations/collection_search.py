"""Daily query depth and topic-local, cross-day rotation share one bounded dispatch."""
import hashlib
import json

import httpx

from .collection_ledger import check, load, save
from .collection_language import plan
from .policy import now_iso

DOMAINS = ('', 'site:xiaohongshu.com', 'site:zhihu.com', 'site:bilibili.com', 'site:mp.weixin.qq.com', 'site:douyin.com')
DEPTHS = (20, 50, 100)


def query_options(policy, mode, phrases):
    options = {}
    if mode != 'en':
        for term in ['', *policy['keywords']]:
            for domain in DOMAINS:
                text = ' '.join(dict.fromkeys(filter(None, (policy['topic'], term, domain))))
                options[text] = {'type': 'search', 'query': text, 'language': 'zh', 'keyword': term or policy['topic']}
    for word, terms in phrases.items():
        for text in terms:
            existing = options.get(text)
            keywords = existing['keywords'] if existing and existing['language'] == 'en' else []
            keywords = list(dict.fromkeys([*keywords, word]))
            options[text] = {'type': 'search', 'query': text, 'language': 'en', 'keyword': keywords[0], 'keywords': keywords}
    return options


def choose(options, daily, history, limit, offset, topic, mode):
    eligible = [q for q in options if daily.get(q, {}).get('depth', 0) < len(DEPTHS)
                and daily.get(q, {}).get('errors', 0) < 2]
    eligible.sort(key=lambda q: (daily.get(q, {}).get('attempts', 0), history.get(q, {}).get('last', '')))
    chosen = []
    from collections import deque
    from itertools import groupby
    for _, peers in groupby(eligible, key=lambda q: daily.get(q, {}).get('attempts', 0)):
        groups = {'zh': deque(), 'en': deque()}
        for query in peers:
            groups[options[query]['language']].append(query)
        if limit > 1 and topic in groups['zh'] and topic not in daily:
            groups['zh'].remove(topic)
            groups['zh'].appendleft(topic)
        while (groups['zh'] or groups['en']) and len(chosen) < limit:
            minority = (offset + len(chosen) + 1) % 4 == 0
            lang = 'en' if minority != (mode == 'prefer_en') else 'zh'
            group = groups[lang] or groups['en' if lang == 'zh' else 'zh']
            chosen.append(group.popleft())
        if len(chosen) >= limit:
            break
    return eligible, chosen


def run_query(store, policy, day, option, state, stats):
    from tools.web_tools import web_search_tool
    check(store, policy)
    query = option['query']
    limit = DEPTHS[state['depth']]
    store.progress('正在分轮检索信息来源', {'query': query, 'requested': limit})
    try:
        found = json.loads(web_search_tool(query, limit=limit))
    except (OSError, ValueError, httpx.HTTPError) as exc:
        found = {'error': str(exc)}
    rows = found.get('data', {}).get('web', [])
    error = found.get('error')
    state.update(query=query, day=day, attempts=state['attempts'] + 1, requested=limit, returned=len(rows), error=error)
    if error:
        state['errors'] += 1
        stats['search_errors'] += 1
        store.event('source_error', state)
    else:
        state['depth'] += 1
    key = hashlib.sha256(f'{day}:{query}'.encode()).hexdigest()
    save(store, 'collection_search', 'collection-search:' + key, state)
    store.event('source_search', {**state, **option})
    stats['queries'].append(option)
    stats['searches'] += 1
    origins = [{**option, 'keyword': term} for term in option.get('keywords', [option['keyword']])]
    return [{**row, 'origins': origins} for row in rows if isinstance(row, dict)]


def search(store, policy, day, stats):
    mode, reason, phrases, config_key = plan(store, policy, day)
    stats.update(english_reason=reason, queries=[])
    options = query_options(policy, mode, phrases)
    key = 'query-rotation:' + hashlib.sha256(policy['topic'].encode()).hexdigest()
    rotation = load(store, key) or {}
    history = rotation.get('history', {})
    offset = rotation.get('count', 0)
    daily = {r['query']: r for r in store.objects('collection_search', day)}
    eligible, chosen = choose(options, daily, history, stats['query_limit'], offset, policy['topic'], mode)
    results = []
    for i, query in enumerate(chosen, 1):
        state = daily.get(query, {'depth': 0, 'errors': 0, 'attempts': 0})
        option = {**options[query], 'config_key': config_key}
        results.extend(run_query(store, policy, day, option, state, stats))
        history[query] = {'last': now_iso()}
        save(store, 'query_rotation', key, {'count': offset + i, 'history': {q: history[q] for q in options if q in history}})
        daily[query] = state
    stats['searches_remaining'] = sum(daily.get(q, {}).get('depth', 0) < len(DEPTHS)
                                     and daily.get(q, {}).get('errors', 0) < 2 for q in eligible)
    return results, options
