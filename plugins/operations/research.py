"""Source collection through existing search/extract providers; raw evidence stays attached."""
import asyncio
import hashlib
import json
import httpx
from xml.etree.ElementTree import ParseError
from urllib.parse import urldefrag

from .policy import now_iso, public_url


def collect(store, policy, day):
    from tools.web_tools import web_search_tool, web_extract_tool
    if len(store.objects("source", day)) >= policy["limits"]["source"]:
        return
    candidates = [{"url": u, "title": u} for u in policy["sources"]]
    from .feeds import feed_entries
    for feed in policy.get("rss_sources", []):
        try:
            candidates.extend(feed_entries(feed))
        except (OSError, ValueError, httpx.HTTPError, ParseError) as exc:
            store.event("source_error", {"day": day, "url": feed, "error": str(exc)})
    keywords = policy["keywords"] or [policy["topic"]]
    domains = ["", "site:xiaohongshu.com", "site:zhihu.com", "site:bilibili.com", "site:mp.weixin.qq.com", "site:douyin.com"]
    for domain in domains:
        store.renew()
        if store.policy()[1] != policy or policy["paused"] or not policy["enabled"]:
            raise ValueError("运营规则变更或已暂停，停止采集")
        query = " ".join([*keywords[:3], domain]).strip()
        store.progress("正在检索信息来源", {"query": query})
        found = json.loads(web_search_tool(query, limit=5))
        candidates.extend(found.get("data", {}).get("web", []))
        if found.get("error"):
            store.event("source_error", {"day": day, "query": query, "error": found["error"]})
    already = {row["url"] for row in store.objects("source") if row.get("day") == day}
    remaining = max(0, policy["limits"]["source"] - len(already))
    urls = {}
    for candidate in candidates:
        try:
            url = urldefrag(public_url(candidate.get("url", "")))[0]
        except ValueError:
            continue
        if url not in already:
            urls.setdefault(url, candidate)
    for url, candidate in list(urls.items())[:remaining]:
        store.renew()
        if store.policy()[1] != policy or policy["paused"] or not policy["enabled"]:
            raise ValueError("运营规则变更或已暂停，停止采集")
        store.progress("正在读取来源正文", {"url": url, "title": candidate.get("title", url)})
        extracted = json.loads(asyncio.run(web_extract_tool([url], char_limit=10000)))
        pages = extracted.get("results", [])
        page = pages[0] if pages else {}
        text = page.get("content") or page.get("markdown") or page.get("text") or ""
        record = {"day": day, "url": url, "title": candidate.get("title", url),
                  "author": page.get("author") or candidate.get("author"), "published_at": page.get("published_at") or candidate.get("published_at"),
                  "collected_at": now_iso(), "text": text, "state": "read" if text else "unavailable",
                  "error": page.get("error") or extracted.get("error"), "summary": "",
                  "fingerprint": hashlib.sha256(text.encode()).hexdigest() if text else None}
        previous = next((s for s in store.objects("source") if s.get("fingerprint") and s["fingerprint"] == record["fingerprint"]), None)
        record.update(is_new=previous is None, previous_source_id=previous["id"] if previous else None)
        store.put("source", record, hashlib.sha256(f"{day}:{url}".encode()).hexdigest())


def distinct_sources(store, day):
    seen, records = set(), []
    for row in store.objects("source"):
        if row.get("day") != day or not row.get("text") or row["fingerprint"] in seen:
            continue
        seen.add(row["fingerprint"])
        records.append(row)
    return records


def save_brief(store, day, result, sources):
    from .store import encoded
    known = {s["id"]: s for s in sources}
    for fact in result.get("facts", []):
        if not isinstance(fact, dict) or not fact.get("source_ids") or not set(fact["source_ids"]) <= set(known):
            raise ValueError("信息结论缺少有效来源依据")
    with store.connection() as db:
        for summary in result.get("summaries", []):
            if summary.get("source_id") not in known or not isinstance(summary.get("summary"), str):
                continue
            source = {**known[summary["source_id"]], "summary": summary["summary"][:2000], "topics": summary.get("topics", [])}
            db.execute("UPDATE objects SET data=? WHERE id=? AND kind='source'", (encoded(source), source["id"]))
    store.put("brief", {"day": day, "result": result, "source_ids": list(known)})
