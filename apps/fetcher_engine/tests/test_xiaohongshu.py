from __future__ import annotations

import asyncio

from apps.fetcher_engine.connectors.xiaohongshu.fetcher import XiaohongshuFetcher


def _request(limit: int = 10):
    return type(
        "Request",
        (),
        {"source_name": "Xiaohongshu", "lookback_hours": 24, "limit": limit, "cursor": None, "options": {}},
    )()


def _build_html(note_data: dict):
    """构造包含 window.__INITIAL_STATE__ 的测试 HTML。"""
    import json
    state = {
        "note": {
            "noteDetailMap": {
                "abc123": {"note": note_data}
            }
        }
    }
    return f'<script>window.__INITIAL_STATE__={json.dumps(state, ensure_ascii=False)};</script>'


def _image_note_data():
    return {
        "id": "abc123",
        "title": "西安美食探店",
        "desc": "这家泡馍真的绝了！",
        "type": "normal",
        "user": {"nickname": "littlekycap", "id": "user123"},
        "imageList": [
            {"url": "https://example.com/img1.jpg"},
            {"url": "https://example.com/img2.png"},
        ],
        "time": "2026-06-20T10:00:00+08:00",
        "interactInfo": {"likedCount": 1287, "commentCount": 10, "collectedCount": 130},
        "tagList": [{"name": "西安美食"}, {"name": "探店"}],
    }


def _video_note_data():
    return {
        "id": "def456",
        "title": "Vlog 日常",
        "desc": "今天去了大雁塔~",
        "type": "video",
        "user": {"nickname": "littlekycap", "id": "user123"},
        "imageList": [],
        "video": {"url": "https://example.com/video.mp4"},
        "cover": {"url": "https://example.com/cover.jpg"},
        "time": "2026-06-19T18:00:00+08:00",
        "interactInfo": {"likedCount": 500, "commentCount": 20},
        "tagList": [],
    }


def _empty_desc_note_data():
    return {
        "id": "ghi789",
        "title": "纯图片笔记",
        "desc": "",
        "type": "normal",
        "user": {"nickname": "littlekycap"},
        "imageList": [
            {"url": "https://example.com/pic1.jpg"},
        ],
        "time": "2026-06-18T12:00:00+08:00",
        "interactInfo": {},
        "tagList": [],
    }


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200, url: str = "https://test.com"):
        self.text = text
        self.status_code = status_code
        self.url = url


def test_xiaohongshu_image_note() -> None:
    fetcher = XiaohongshuFetcher(
        urls=["https://www.xiaohongshu.com/discovery/item/abc123?xsec_token=test"],
    )
    html = _build_html(_image_note_data())
    fetcher._fetch_single = lambda url: fetcher._parse_html_to_item(url, html)  # type: ignore[method-assign]

    items = asyncio.run(fetcher.fetch(_request()))

    assert len(items) == 1
    item = items[0]
    assert item.source_type == "xiaohongshu"
    assert item.source_id == "abc123"
    assert item.title == "西安美食探店"
    assert item.raw_content is not None
    assert "泡馍" in item.raw_content
    assert "![图片](https://example.com/img1.jpg)" in item.raw_content
    assert item.metadata["type"] == "image"
    assert item.metadata["images"] == ["https://example.com/img1.jpg", "https://example.com/img2.png"]
    assert item.metadata["author"] == "littlekycap"
    assert item.metadata["likes"] == 1287
    assert item.metadata["tags"] == ["西安美食", "探店"]


def test_xiaohongshu_video_note() -> None:
    fetcher = XiaohongshuFetcher(
        urls=["https://www.xiaohongshu.com/discovery/item/def456?xsec_token=test"],
    )
    html = _build_html(_video_note_data())
    fetcher._fetch_single = lambda url: fetcher._parse_html_to_item(url, html)  # type: ignore[method-assign]

    items = asyncio.run(fetcher.fetch(_request()))

    assert len(items) == 1
    item = items[0]
    assert item.source_id == "def456"
    assert item.title == "Vlog 日常"
    assert item.raw_content is not None
    assert "[视频](https://example.com/video.mp4)" in item.raw_content
    assert item.metadata["type"] == "video"
    assert item.metadata["video_url"] == "https://example.com/video.mp4"
    assert item.metadata["cover_url"] == "https://example.com/cover.jpg"


def test_xiaohongshu_empty_desc() -> None:
    fetcher = XiaohongshuFetcher(
        urls=["https://www.xiaohongshu.com/discovery/item/ghi789?xsec_token=test"],
    )
    html = _build_html(_empty_desc_note_data())
    fetcher._fetch_single = lambda url: fetcher._parse_html_to_item(url, html)  # type: ignore[method-assign]

    items = asyncio.run(fetcher.fetch(_request()))

    assert len(items) == 1
    item = items[0]
    assert item.title == "纯图片笔记"
    assert item.raw_content is not None
    assert "![图片](https://example.com/pic1.jpg)" in item.raw_content


def test_xiaohongshu_empty_urls() -> None:
    fetcher = XiaohongshuFetcher(urls=[])
    items = asyncio.run(fetcher.fetch(_request()))
    assert items == []


def test_xiaohongshu_failure_graceful() -> None:
    fetcher = XiaohongshuFetcher(
        urls=[
            "https://www.xiaohongshu.com/discovery/item/ok1",
            "https://www.xiaohongshu.com/discovery/item/bad",
            "https://www.xiaohongshu.com/discovery/item/ok2",
        ],
    )

    def _mock_fetch(url: str):
        if "bad" in url:
            raise RuntimeError("fetch failed")
        return _image_note_data()

    fetcher._fetch_single = _mock_fetch  # type: ignore[method-assign]
    items = asyncio.run(fetcher.fetch(_request()))

    assert len(items) == 2


def test_xiaohongshu_limit_respected() -> None:
    fetcher = XiaohongshuFetcher(
        urls=[
            "https://www.xiaohongshu.com/discovery/item/1",
            "https://www.xiaohongshu.com/discovery/item/2",
            "https://www.xiaohongshu.com/discovery/item/3",
        ],
    )
    html = _build_html(_image_note_data())
    fetcher._fetch_single = lambda url: fetcher._parse_html_to_item(url, html)  # type: ignore[method-assign]
    items = asyncio.run(fetcher.fetch(_request(limit=2)))
    assert len(items) == 2


def test_xiaohongshu_returns_empty_on_invalid_data() -> None:
    fetcher = XiaohongshuFetcher(
        urls=["https://www.xiaohongshu.com/discovery/item/empty"],
    )
    fetcher._fetch_single = lambda url: None  # type: ignore[method-assign]
    items = asyncio.run(fetcher.fetch(_request()))
    assert items == []


def test_xiaohongshu_extract_source_id() -> None:
    fetcher = XiaohongshuFetcher()
    # discovery/item 格式
    assert fetcher._extract_source_id("https://www.xiaohongshu.com/discovery/item/abc123?xsec_token=test") == "abc123"
    # user/profile 格式
    assert fetcher._extract_source_id("https://www.xiaohongshu.com/user/profile/user123/abc456?xsec_token=test") == "abc456"
    # 纯路径
    assert fetcher._extract_source_id("https://www.xiaohongshu.com/explore/abc789") == "abc789"
