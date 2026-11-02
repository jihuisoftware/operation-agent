"""Bounded query expansion; providers expose result counts, not a portable page cursor."""
import hashlib
import json

import httpx

from .collection_ledger import check, load, save

DOMAINS = ('', 'site:xiaohongshu.com', 'site:zhihu.com', 'site:bilibili.com', 'site:mp.weixin.qq.com', 'site:douyin.com')
DEPTHS = (20, 50, 100)


def queries(policy):
    terms = list(dict.fromkeys(['', *policy['keywords']]))
    return list(dict.fromkeys(' '.join(dict.fromkeys(filter(None, [policy['topic'], term, domain])))
                              for term in terms for domain in DOMAINS))


def search(store, policy, day, stats):
    from tools.web_tools import web_search_tool
    plans = []
    for query in queries(policy):
        key = 'collection-search:' + hashlib.sha256(f'{day}:{query}'.encode()).hexdigest()
        state = load(store, key) or {'day': day, 'query': query, 'depth': 0, 'errors': 0, 'attempts': 0}
        if state['depth'] < len(DEPTHS) and state['errors'] < 2:
            plans.append((key, state))
    plans.sort(key=lambda item: item[1]['attempts'])
    results = []
    for key, state in plans[:stats.get('query_limit', 12)]:
        check(store, policy)
        limit = DEPTHS[state['depth']]
        store.progress('正在分轮检索信息来源', {'query': state['query'], 'requested': limit})
        try:
            found = json.loads(web_search_tool(state['query'], limit=limit))
        except (OSError, ValueError, httpx.HTTPError) as exc:
            found = {'error': str(exc)}
        rows = found.get('data', {}).get('web', [])
        error = found.get('error')
        state.update(attempts=state['attempts'] + 1, requested=limit, returned=len(rows), error=error)
        if error:
            state['errors'] += 1
            stats['search_errors'] += 1
            store.event('source_error', state)
        else:
            state['depth'] += 1
        save(store, 'collection_search', key, state)
        store.event('source_search', state)
        stats['searches'] += 1
        results.extend(rows)
    stats['searches_remaining'] = sum(1 for _, state in plans if state['depth'] < len(DEPTHS) and state['errors'] < 2)
    return results
