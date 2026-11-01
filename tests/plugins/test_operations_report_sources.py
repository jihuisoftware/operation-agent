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
