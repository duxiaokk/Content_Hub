from __future__ import annotations

import asyncio

from apps.fetcher_engine.connectors.xiaohongshu.fetcher import XiaohongshuFetcher


def _request(limit: int = 10):
    return type(
        "Request",
        (),
        {"source_name": "Xiaohongshu", "lookback_hours": 24, "limit": limit, "cursor": None, "options": {}},
    )()


def _image_note_response():
    return {
        "title": "西安美食探店",
        "desc": "这家泡馍真的绝了！",
        "nickname": "littlekycap",
        "type": "图片",
        "downloads": [
            "https://example.com/img1.jpg",
            "https://example.com/img2.png",
        ],
        "published_at": "2026-06-20T10:00:00+08:00",
        "id": "abc123",
    }


def _video_note_response():
    return {
        "title": "Vlog 日常",
        "desc": "今天去了大雁塔~",
        "nickname": "littlekycap",
        "type": "视频",
        "downloads": [
            "https://example.com/video.mp4",
        ],
        "cover_url": "https://example.com/cover.jpg",
        "published_at": "2026-06-19T18:00:00+08:00",
        "id": "def456",
    }


def _nested_note_response():
    return {
        "data": {
            "note": {
                "title": "nested title",
                "description": "nested desc",
                "author": "littlekycap",
                "mediaType": "image",
                "imageList": [
                    {"url": "https://example.com/nested1.jpg"},
                    {"url": "https://example.com/nested2.jpg"},
                ],
                "create_time": "2026-06-18T12:00:00+08:00",
                "id": "ghi789",
            }
        }
    }


def test_xiaohongshu_image_note() -> None:
    fetcher = XiaohongshuFetcher(
        urls=["https://www.xiaohongshu.com/explore/abc123"],
        api_base_url="http://localhost:5556",
    )
    fetcher._call_detail_api = lambda url: _image_note_response()  # noqa: ARG005

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


def test_xiaohongshu_video_note() -> None:
    fetcher = XiaohongshuFetcher(
        urls=["https://www.xiaohongshu.com/explore/def456"],
        api_base_url="http://localhost:5556",
    )
    fetcher._call_detail_api = lambda url: _video_note_response()  # noqa: ARG005

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


def test_xiaohongshu_nested_structure() -> None:
    fetcher = XiaohongshuFetcher(
        urls=["https://www.xiaohongshu.com/explore/ghi789"],
        api_base_url="http://localhost:5556",
    )
    fetcher._call_detail_api = lambda url: _nested_note_response()  # noqa: ARG005

    items = asyncio.run(fetcher.fetch(_request()))

    assert len(items) == 1
    item = items[0]
    assert item.title == "nested title"
    assert item.metadata["type"] == "image"
    assert item.metadata["images"] == ["https://example.com/nested1.jpg", "https://example.com/nested2.jpg"]
    assert item.source_id == "ghi789"


def test_xiaohongshu_empty_urls() -> None:
    fetcher = XiaohongshuFetcher(urls=[])
    items = asyncio.run(fetcher.fetch(_request()))
    assert items == []


def test_xiaohongshu_api_failure_graceful() -> None:
    fetcher = XiaohongshuFetcher(
        urls=[
            "https://www.xiaohongshu.com/explore/ok1",
            "https://www.xiaohongshu.com/explore/bad",
            "https://www.xiaohongshu.com/explore/ok2",
        ],
        api_base_url="http://localhost:5556",
    )

    def _mock_call(url: str) -> dict:
        if "bad" in url:
            raise RuntimeError("xhs api http error: 500")
        return _image_note_response()

    fetcher._call_detail_api = _mock_call
    items = asyncio.run(fetcher.fetch(_request()))

    assert len(items) == 2


def test_xiaohongshu_limit_respected() -> None:
    fetcher = XiaohongshuFetcher(
        urls=[
            "https://www.xiaohongshu.com/explore/1",
            "https://www.xiaohongshu.com/explore/2",
            "https://www.xiaohongshu.com/explore/3",
        ],
        api_base_url="http://localhost:5556",
    )
    fetcher._call_detail_api = lambda url: _image_note_response()  # noqa: ARG005

    items = asyncio.run(fetcher.fetch(_request(limit=2)))
    assert len(items) == 2
