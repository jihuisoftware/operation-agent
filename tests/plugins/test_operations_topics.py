"""Collection and topic planning are independent; chosen topics reach saved content."""
from copy import deepcopy
import json

import pytest

from plugins.operations import content, topics, workflow
from plugins.operations.policy import DEFAULT, local_day
from plugins.operations.store import Store, encoded
from tests.plugins.operations_support import prepare_materials


def configured(tmp_path):
    store = Store(tmp_path / "operations.db")
    policy = deepcopy(DEFAULT)
    policy.update(topic="小户型收纳", goal="提供有来源的收纳方法", enabled=True)
    policy["modules"].update(research=True, topics=True, content=True)
    store.configure(policy, 0)
    return store, policy, local_day(policy)


def source(store, day):
    return store.put("source", {"day": day, "text": "原始资料" * 2000, "state": "read", "fingerprint": "one",
                                "url": "https://example.org/source", "title": "厨房实测"}, "source")


def test_collection_does_not_select_and_selection_does_not_collect(tmp_path, monkeypatch):
    store, policy, day = configured(tmp_path)
    monkeypatch.setattr(workflow, "collect", lambda *_: source(store, day))
    monkeypatch.setattr(workflow, "generate", lambda *_: pytest.fail("采集不能调用选题模型"))
    assert "未在本步骤执行" in workflow.research(store, policy, day, 1)
    assert not store.objects("brief")
    monkeypatch.setattr(workflow, "collect", lambda *_: pytest.fail("选题不能采集"))
    inputs = []
    def generate(*args):
        inputs.append(args[-1])
        return {"topics": [{"title": "厨房收纳的三个步骤", "source_ids": ["source"], "reason": "实测资料"}],
                "facts": [], "summaries": [{"source_id": "source", "summary": "厨房资料摘要"}]}
    prepare_materials(store, policy, day, monkeypatch)
    monkeypatch.setattr(topics, "generate", generate)
    assert "生成 1 个" in workflow.topics(store, policy, day, 1)
    assert inputs[0]["topic"] == policy["topic"]
    assert inputs[0]["sources"][0]["summary"] == "来源方法摘要"
    assert "text" not in inputs[0]["sources"][0]
    saved = store.objects("source")[0]
    assert saved["day"] == day and len(saved["text"]) == 8000
    assert saved["summary"] == "厨房资料摘要"
    assert topics.production_topic(store, policy, day)["title"] == "厨房收纳的三个步骤"


def test_manual_topic_is_used_in_production_without_auto_planning_or_publishing(tmp_path, monkeypatch):
    store, policy, day = configured(tmp_path)
    source(store, day)
    prepare_materials(store, policy, day, monkeypatch)
    selected = topics.select(store, {"version": 1, "title": "300 元厨房收纳改造"})
    monkeypatch.setattr(topics, "generate", lambda *_: pytest.fail("手动选题不能调用模型"))
    seen = []
    def generate(*args):
        seen.append(args[-1])
        return {"title": "厨房收纳改造", "body": "依据已采集资料", "source_ids": ["source"], "asset_ids": []}
    monkeypatch.setattr(content, "generate", generate)
    monkeypatch.setattr(content, "check_content", lambda *_: {"pass": True})
    content.produce_content(store, policy, day, 1)
    assert seen[0]["selected_topic"]["title"] == selected["title"]
    assert store.objects("content")[0]["selected_topic"]["id"] == selected["id"]
    assert not store.objects("brief") and not store.snapshot()["actions"]
    assert topics.catalog(Store(tmp_path / "other.db"))["selected"] is None
    changed = {**policy, "topic": "工厂获客"}
    store.configure(changed, 1)
    assert topics.catalog(store)["selected"] is None
    with pytest.raises(ValueError, match="规则已变更"):
        topics.select(store, {"version": 1, "title": "过期页面提交"})


def test_v2_migration_splits_modules_without_replaying_claimed_topics(tmp_path):
    store, policy, day = configured(tmp_path)
    old = deepcopy(policy)
    old["schema_version"] = 2
    old["modules"].pop("topics")
    old["times"].pop("topics")
    old["times"]["research"] = ["08:30", "17:00"]
    old["limits"]["source"] = 7
    store.put("brief", {"day": day, "source_ids": [], "result": {"topics": ["旧选题"]}})
    with store.connection() as db:
        db.execute("UPDATE settings SET version=4,data=?", (encoded(old),))
    run = store.start_run(day, "research", "08:30", 4)
    store.finish_run(run, "completed", "旧的采集与选题已完成")
    migrated = Store(store.path)
    version, policy = migrated.policy()
    assert version == 5 and policy["schema_version"] == DEFAULT["schema_version"]
    assert policy["modules"]["research"] and policy["modules"]["topics"]
    assert policy["times"]["topics"] == ["08:30", "17:00"]
    assert policy["limits"] == old["limits"] and policy["allowed"] == old["allowed"]
    assert migrated.start_run(day, "topics", "08:30", version) is None
    assert topics.catalog(migrated)["candidates"][0]["title"] == "旧选题"
    with pytest.raises(workflow.StageSkipped, match="旧选题"):
        topics.production_topic(migrated, policy, day)
    assert Store(store.path).policy()[0] == version
    with migrated.connection() as db:
        history = json.loads(db.execute("SELECT data FROM objects WHERE id='policy:4'").fetchone()[0])
    assert history["policy"]["schema_version"] == 2
    migrated.configure({**policy, "topic": "另一个运营主题"}, version)
    assert topics.catalog(migrated)["candidates"] == []


def test_candidate_selection_rejects_stale_batch_and_carries_source_evidence(tmp_path, monkeypatch):
    store, policy, day = configured(tmp_path)
    source(store, day)
    prepare_materials(store, policy, day, monkeypatch)
    monkeypatch.setattr(topics, "generate", lambda *_: {"topics": [{"title": "选题", "source_ids": ["source"]}]})
    workflow.topics(store, policy, day, 1)
    data = topics.catalog(store)
    selected = topics.select(store, {"version": 1, "brief_id": data["brief_id"], "candidate_index": 0})
    assert selected["source_ids"] == ["source"]
    with pytest.raises(ValueError, match="候选选题已变化"):
        topics.select(store, {"version": 1, "brief_id": "old", "candidate_index": 0})


def test_collection_queries_include_custom_scope_even_with_template_keywords(tmp_path, monkeypatch):
    from tools import web_tools
    from plugins.operations.research import collect
    store, policy, day = configured(tmp_path)
    policy['keywords'] = ['领域新问题', '成长经验']
    store.configure(policy, 1)
    queries = []
    def search(query, **kwargs):
        queries.append(query)
        return json.dumps({'data': {'web': []}})
    monkeypatch.setattr(web_tools, 'web_search_tool', search)
    collect(store, policy, day)
    assert queries and all(policy['topic'] in query for query in queries)
