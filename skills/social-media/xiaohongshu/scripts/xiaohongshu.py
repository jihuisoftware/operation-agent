"""Xiaohongshu page controls, executed inside Hermes browser_exec's existing session."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlencode, urlsplit

HOME = "https://www.xiaohongshu.com/explore"
CREATOR = "https://creator.xiaohongshu.com/publish/publish?source=official"
PAGE_SCRIPT = Path(__file__).with_name("page.js").read_text(encoding="utf-8")


def note_url(value: str) -> str:
    """Keep signed share parameters intact, but only navigate directly to a note."""
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or parsed.netloc != "www.xiaohongshu.com"
            or not re.fullmatch(r"/(?:explore|search_result)/[a-fA-F0-9]{24}", parsed.path)):
        raise ValueError("请提供小红书笔记完整 HTTPS 链接；短链接请先在浏览器中展开。")
    return value


class Xiaohongshu:
    """Use the helpers provided by browser_exec; never create an independent profile."""

    def __init__(self, browser: dict):
        self.browser = browser

    def _page(self, action: str, **params) -> dict:
        payload = json.dumps({"action": action, **params}, ensure_ascii=False)
        result = self.browser["js"](f"{PAGE_SCRIPT}({payload})")
        if not isinstance(result, dict) or "status" not in result:
            raise RuntimeError("浏览器未返回可识别的页面状态。")
        return result

    def open(self) -> dict:
        """Start in a fresh tab so an existing user draft is not navigated away."""
        self.browser["new_tab"](HOME)
        self.browser["wait_for_load"]()
        return self.status()

    def status(self) -> dict:
        return self._page("status")

    def inspect(self) -> dict:
        return self._page("inspect")

    def search(self, keyword: str, count: int = 20) -> dict:
        if not isinstance(keyword, str) or not keyword.strip():
            raise ValueError("搜索词不能为空。")
        self._count(count)
        # A new tab also preserves a creator draft in this browser session.
        url = "https://www.xiaohongshu.com/search_result?" + urlencode({
            "keyword": keyword.strip(), "source": "web_explore_feed"})
        self.browser["new_tab"](url)
        self.browser["wait_for_load"]()
        return self._page("search", count=count)

    def read(self, url: str, count: int = 20) -> dict:
        self._count(count)
        self.browser["new_tab"](note_url(url))
        self.browser["wait_for_load"]()
        return self._page("read", count=count)

    def creator(self) -> dict:
        self.browser["new_tab"](CREATOR)
        self.browser["wait_for_load"]()
        return self.inspect()

    @staticmethod
    def _count(count: int) -> None:
        if type(count) is not int or not 1 <= count <= 50:
            raise ValueError("单次读取数量须为 1–50。")

    def _editor(self) -> dict:
        state = self.inspect()
        if state["status"] != "ready":
            return state
        if urlsplit(state["url"]).netloc != "creator.xiaohongshu.com":
            return {"status": "wrong_page"}
        return state

    @staticmethod
    def _field(fields: list[dict], kind: str, selector: str | None) -> dict | None:
        predicates = {
            "title": lambda f: f["tag"] == "input" and f["type"] in ("text", "")
                and (selector is not None or "标题" in f["placeholder"]),
            "body": lambda f: f["editable"],
            "image": lambda f: f["type"] == "file" and "image" in f["accept"],
        }
        candidates = [f for f in fields if not f["disabled"] and predicates[kind](f)
                      and (selector is None or f["selector"] == selector)]
        return candidates[0] if len(candidates) == 1 else None

    def upload_images(self, paths: list[str], selector: str | None = None) -> dict:
        """Request a browser file upload; platform processing still needs inspection."""
        if not isinstance(paths, list) or not paths:
            raise ValueError("请提供至少一个本地图片路径。")
        files = [Path(path).expanduser().resolve(strict=True) for path in paths]
        if any(not p.is_file() or p.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}
               for p in files):
            raise ValueError("仅支持 PNG、JPEG、WebP 图片文件。")
        state = self._editor()
        if state["status"] != "ready":
            return state
        field = self._field(state["fields"], "image", selector)
        if field is None:
            return {"status": "page_changed", "message": "请切换到上传图文，核对图片上传框。"}
        cdp = self.browser["cdp"]
        root = cdp("DOM.getDocument")["root"]["nodeId"]
        node = cdp("DOM.querySelector", nodeId=root, selector=field["selector"])["nodeId"]
        if not node:
            return {"status": "page_changed"}
        cdp("DOM.setFileInputFiles", nodeId=node, files=[str(p) for p in files])
        return {"status": "upload_requested", "count": len(files),
                "message": "已交给浏览器上传；请检查页面缩略图与错误提示，尚未确认上传完成。"}

    def fill_draft(self, title: str, body: str, *, replace: bool = False,
                   title_selector: str | None = None, body_selector: str | None = None) -> dict:
        """Fill the current creator editor and read it back; never press publish/save."""
        if not isinstance(title, str) or not title.strip() or not isinstance(body, str) or not body.strip():
            raise ValueError("标题和正文不能为空。")
        state = self._editor()
        if state["status"] != "ready":
            return state
        title_field = self._field(state["fields"], "title", title_selector)
        body_field = self._field(state["fields"], "body", body_selector)
        if title_field is None or body_field is None:
            return {"status": "page_changed", "message": "未找到唯一标题和正文编辑框，请先检查页面。"}
        pairs = [(title_field, title), (body_field, body)]
        if not replace and any(f["value"] and f["value"] != value for f, value in pairs):
            return {"status": "draft_conflict", "message": "编辑框已有不同内容，请先确认是否覆盖。"}
        if title_field["value"] != title:
            self.browser["fill_input"](title_field["selector"], title)
        if body_field["value"] != body:
            focused = self._page("focus_body", selector=body_field["selector"])
            if focused["status"] != "ready":
                return {**focused, "partial": True}
            self.browser["cdp"]("Input.insertText", text=body)
        after = self._editor()
        if after["status"] != "ready":
            return {**after, "partial": True}
        actual = {f["selector"]: f["value"] for f in after["fields"]}
        if any(actual.get(f["selector"]) != value for f, value in pairs):
            return {"status": "verification_failed", "partial": True,
                    "message": "页面回读与输入不一致，请检查编辑器；不要自动重试。"}
        return {"status": "draft_filled", "title": title, "body": body,
                "saved": False, "published": False}
