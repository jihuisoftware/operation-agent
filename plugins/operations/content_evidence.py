"""Bound review input without discarding the middle passages cited by a manuscript."""
import hashlib
import re

REVIEW_CHARACTERS = 32_000


def terms(content):
    text = str(content.get('title', '')) + '\n' + str(content.get('body', ''))
    result = set(re.findall(r'[a-z][a-z0-9_-]{2,}|\d+(?:[.%–-]\d+)*%?', text.lower()))
    for phrase in re.findall(r'[\u4e00-\u9fff]{2,}', text):
        if len(phrase) <= 12:
            result.add(phrase)
        result.update(phrase[i:i + 4] for i in range(max(0, len(phrase) - 3)))
    return result


def excerpt(text, allowance, query):
    if len(text) <= allowance:
        return text, [[0, len(text)]]
    width = min(1000, max(100, allowance // 4))
    chunks = [(start, min(start + width, len(text))) for start in range(0, len(text), width)]
    def score(span):
        part = text[span[0]:span[1]].lower()
        return sum(min(len(term), 12) for term in query if term in part)
    ordered = [chunks[0], *sorted(chunks[1:], key=lambda span: (-score(span), span[0]))]
    selected, used = [], 0
    for start, end in ordered:
        if used + end - start <= allowance:
            selected.append((start, end))
            used += end - start
    ranges = []
    for start, end in sorted(selected):
        if ranges and ranges[-1][1] == start:
            ranges[-1][1] = end
        else:
            ranges.append([start, end])
    return '\n[未提供的正文段落]\n'.join(text[start:end] for start, end in ranges), ranges


def review_sources(content, sources):
    by_id = {row['id']: row for row in sources}
    cited = [by_id[identity] for identity in dict.fromkeys(content['source_ids']) if identity in by_id]
    remaining, allocations = REVIEW_CHARACTERS, {}
    for index, row in enumerate(sorted(cited, key=lambda value: len(value.get('text', '')))):
        amount = min(len(row.get('text', '')), remaining // (len(cited) - index))
        allocations[row['id']] = amount
        remaining -= amount
    query, result = terms(content), []
    from .model_inputs import fields
    for row in cited:
        text = row.get('text', '')
        selected, ranges = excerpt(text, allocations[row['id']], query)
        covered = sum(end - start for start, end in ranges)
        limited = covered < len(text)
        result.append({**fields(row, ('id', 'title', 'url', 'published_at', 'day', 'collected_at')),
                       'text': selected, 'text_truncated': limited or bool(row.get('truncated')),
                       'source_truncated': bool(row.get('truncated')), 'excerpted': limited,
                       'original_chars': row.get('original_chars') or len(text), 'captured_chars': len(text),
                       'review_ranges': ranges, 'content_signature': hashlib.sha256(text.encode()).hexdigest()})
    return result
