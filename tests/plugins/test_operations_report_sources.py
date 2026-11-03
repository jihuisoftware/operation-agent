"""A daily export traces reused sources without calling them new collection."""
from plugins.operations.report import daily_report
from plugins.operations.store import Store


def test_report_links_previous_day_sources_used_by_current_content(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    store = Store()
    store.put("source", {"day": "2026-10-31", "title": "定位参考", "url": "https://example.org/original", "state": "read", "text": "原始资料"}, "source")
    store.put("content", {"day": "2026-11-01", "source_ids": ["source"]}, "draft")
    report = daily_report(store, "2026-11-01")["markdown"]
    assert "当日采集 0 条；本日内容引用既有资料 1 条" in report
    assert "[定位参考](https://example.org/original) · 既有资料" in report
    assert "已核对成功 0 次" in report


def test_debug_report_scopes_steps_and_separates_quick_preflight(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    store = Store()
    for slot, stage, detail in (
        ("debug:current:research", "research", "当前批次"),
        ("debug:previous:research", "research", "其他批次"),
        ("debug:current:comments", "comments", "仅检查就绪"),
    ):
        identity = store.start_run("2026-11-01", stage, slot, 0)
        store.finish_run(identity, "completed", detail)
    store.manual_run_id = "debug:current"
    store.run_options = {"coverage": True, "read_limit": 1, "query_limit": 1}

    report = daily_report(store, "2026-11-01")["markdown"]

    assert "当前批次" in report
    assert "其他批次" not in report
    assert "## 预检查结果" in report
    assert "仅抽样 1 条来源、外部动作不执行" in report
