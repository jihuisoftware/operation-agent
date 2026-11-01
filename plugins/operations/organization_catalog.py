"""Read-only classified material views, scoped to the current topic and reusable sources."""
from .organization import materials, CATEGORIES
from .policy import local_day


def catalog(store, query='', category='', cursor=0):
    version, policy = store.policy()
    pairs = materials(store, policy, local_day(policy), include_history=True)
    items, counts = [], {name: 0 for name in CATEGORIES}
    for source, row in pairs:
        if row is None:
            continue
        counts[row['category']] += 1
        if category and row['category'] != category:
            continue
        if query and query.casefold() not in str([row, source.get('title', '')]).casefold():
            continue
        items.append({**row, **{k: source.get(k) for k in ('title', 'url', 'images', 'published_at')},
                      'source_day': source.get('day')})
    return {'version': version, 'topic': policy['topic'], 'day': local_day(policy),
            'total': len(pairs), 'organized': sum(counts.values()),
            'usable': sum(bool(row and row['relevant']) for _, row in pairs),
            'pending': sum(row is None for _, row in pairs), 'categories': counts,
            'matching': len(items), 'items': items[cursor:cursor + 24],
            'next_cursor': cursor + 24 if cursor + 24 < len(items) else None}
