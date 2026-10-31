"""Browser control contracts without accessing a real account or browser profile."""

import json
import runpy
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[2] /
    "skills/social-media/xiaohongshu/scripts/xiaohongshu.py"))
Xiaohongshu = MODULE["Xiaohongshu"]
NOTE_URL = "https://www.xiaohongshu.com/explore/0123456789abcdef01234567?xsec_token=a%2Bb"


def field(selector, *, title=False, image=False, value=""):
    return {"selector": selector, "tag": "input" if title or image else "div",
            "type": "file" if image else "text" if title else "",
            "placeholder": "填写标题" if title else "", "editable": not (title or image),
            "accept": "image/*" if image else "", "disabled": False, "value": value}


def editor(title="", body=""):
    return {"status": "ready", "url": "https://creator.xiaohongshu.com/publish/publish",
            "fields": [field("#title", title=True, value=title), field("#body", value=body)]}


@pytest.fixture
def browser():
    return {key: Mock() for key in ("new_tab", "wait_for_load", "js", "fill_input", "cdp")}


def test_search_encodes_user_query_and_read_preserves_signed_url(browser):
    browser["js"].return_value = {"status": "ok", "notes": []}
    xhs = Xiaohongshu(browser)
    keyword = '咖啡 & #话题 "引号"'
    xhs.search(keyword)
    url = browser["new_tab"].call_args.args[0]
    assert parse_qs(urlsplit(url).query)["keyword"] == [keyword]
    assert xhs.read(NOTE_URL)["status"] == "ok"
    browser["new_tab"].assert_called_with(NOTE_URL)


@pytest.mark.parametrize("url", [
    "http://www.xiaohongshu.com/explore/0123456789abcdef01234567",
    "https://www.xiaohongshu.com.evil.test/explore/0123456789abcdef01234567",
    "https://www.xiaohongshu.com@evil.test/explore/0123456789abcdef01234567",
    "https://www.xiaohongshu.com/", "https://xhslink.com/example", "javascript:alert(1)",
])
def test_invalid_note_link_never_navigates(browser, url):
    with pytest.raises(ValueError):
        Xiaohongshu(browser).read(url)
    browser["new_tab"].assert_not_called()


@pytest.mark.parametrize("count", [0, 51, True, "20"])
def test_invalid_read_count_never_navigates(browser, count):
    with pytest.raises(ValueError):
        Xiaohongshu(browser).search("主题", count=count)
    browser["new_tab"].assert_not_called()


@pytest.mark.parametrize("state", [
    {"status": "login_required"}, {"status": "verification_required"},
    {"status": "wrong_page"}, {**editor(), "url": "https://www.xiaohongshu.com/explore"},
])
def test_blocked_editor_performs_no_writes(browser, state):
    browser["js"].return_value = state
    result = Xiaohongshu(browser).fill_draft("标题", "正文")
    assert result["status"] in {"login_required", "verification_required", "wrong_page"}
    browser["fill_input"].assert_not_called()
    browser["cdp"].assert_not_called()


def test_draft_conflict_and_repeated_same_content_never_write(browser):
    browser["js"].return_value = editor("原有标题", "原有正文")
    xhs = Xiaohongshu(browser)
    assert xhs.fill_draft("新标题", "新正文")["status"] == "draft_conflict"
    assert xhs.fill_draft("原有标题", "原有正文")["status"] == "draft_filled"
    browser["fill_input"].assert_not_called()
    browser["cdp"].assert_not_called()


def test_fill_reads_back_content_and_does_not_claim_save_or_publication(browser):
    title, body = '标题 "示例"', "第一段\n第二段 <script>不是代码</script>"
    browser["js"].side_effect = [editor(), {"status": "ready"}, editor(title, body)]
    result = Xiaohongshu(browser).fill_draft(title, body)
    assert result == {"status": "draft_filled", "title": title, "body": body,
                      "saved": False, "published": False}
    browser["fill_input"].assert_called_once_with("#title", title)
    browser["cdp"].assert_called_once_with("Input.insertText", text=body)
    # The selector is serialized as data, including hostile quote characters.
    code = browser["js"].call_args_list[1].args[0]
    assert json.loads(code.rsplit("\n(", 1)[1][:-1])["selector"] == "#body"


def test_mismatched_readback_is_partial_failure(browser):
    browser["js"].side_effect = [editor(), {"status": "ready"}, editor("标题", "被截断")]
    result = Xiaohongshu(browser).fill_draft("标题", "完整正文")
    assert result["status"] == "verification_failed"
    assert result["partial"] is True
    assert browser["cdp"].call_count == 1


def test_ambiguous_fields_require_observed_selector(browser):
    state = editor()
    state["fields"].append(field("#other-body"))
    browser["js"].return_value = state
    assert Xiaohongshu(browser).fill_draft("标题", "正文")["status"] == "page_changed"
    browser["fill_input"].assert_not_called()
    browser["cdp"].assert_not_called()


def test_upload_uses_existing_browser_and_does_not_claim_completion(browser, tmp_path):
    image = tmp_path / "封面.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    browser["js"].return_value = {**editor(), "fields": [field("#upload", image=True)]}
    browser["cdp"].side_effect = [{"root": {"nodeId": 1}}, {"nodeId": 7}, {}]
    result = Xiaohongshu(browser).upload_images([str(image)])
    assert result["status"] == "upload_requested"
    browser["cdp"].assert_called_with("DOM.setFileInputFiles", nodeId=7, files=[str(image)])
    browser["new_tab"].assert_not_called()


def test_missing_upload_file_stops_before_browser_access(browser, tmp_path):
    with pytest.raises(FileNotFoundError):
        Xiaohongshu(browser).upload_images([str(tmp_path / "missing.png")])
    browser["js"].assert_not_called()
    browser["cdp"].assert_not_called()


@pytest.mark.platforms("macos")
def test_bundled_skill_loads_and_executes_from_isolated_profile(tmp_path, monkeypatch, browser):
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override
    from tools import skills_sync, skills_tool

    home = tmp_path / "profile"
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    source = Path(__file__).resolve().parents[2] / "skills/social-media"
    monkeypatch.setattr(skills_sync, "_get_bundled_dir", lambda: source)
    token = set_hermes_home_override(home)
    try:
        skills_sync.sync_skills(quiet=True)
        loaded = json.loads(skills_tool.skill_view("xiaohongshu", preprocess=False))
        assert loaded["success"] is True
        skill_dir = Path(loaded["skill_dir"])
        assert skill_dir.is_relative_to(home)
        copied = runpy.run_path(str(skill_dir / "scripts/xiaohongshu.py"))
        browser["js"].return_value = {"status": "login_required"}
        assert copied["Xiaohongshu"](browser).open()["status"] == "login_required"
        browser["new_tab"].assert_called_once_with("https://www.xiaohongshu.com/explore")
    finally:
        reset_hermes_home_override(token)
