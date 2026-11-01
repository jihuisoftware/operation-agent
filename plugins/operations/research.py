"""Deduplicated evidence and saved topic briefs; collection lives in collection.py."""

from .collection_validation import fingerprint


def distinct_sources(store, day):
    seen, records = set(), []
    for row in store.objects("source"):
        if row.get("day") != day or not row.get("text") or fingerprint(row["text"]) in seen:
            continue
        seen.add(fingerprint(row["text"]))
        records.append(row)
    return records


def save_brief(store, day, result, sources, *, scope_topic=None, version=None):
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
    return store.put("brief", {"day": day, "result": result, "source_ids": list(known),
                               "scope_topic": scope_topic, "version": version})
