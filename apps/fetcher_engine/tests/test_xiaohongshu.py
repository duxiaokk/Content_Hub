from __future__ import annotations

import asyncio

from apps.fetcher_engine.connectors.xiaohongshu.fetcher import XiaohongshuFetcher


def _request(limit: int = 10):
    return type(
        "Request",
        (),
        {"source_name": "Xiaohongshu", "lookback_hours": 24, "limit": limit, "cursor": None, "options": {}},
    )()


def _image_note_data():
    return {
        "作品标题": "西安美食探店",
        "作品描述": "这家泡馍真的绝了！",
        "作者昵称": "littlekycap",
        "作品类型": "图文",
        "下载地址": [
            "https://example.com/img1.jpg",
            "https://example.com/img2.png",
        ],
        "发布时间": "2026-06-20T10:00:00+08:00",
        "作品ID": "abc123",
    }


def _video_note_data():
    return {
        "作品标题": "Vlog 日常",
        "作品描述": "今天去了大雁塔~",
        "作者昵称": "littlekycap",
        "作品类型": "视频",
        "下载地址": [
            "https://example.com/video.mp4",
        ],
        "封面": "https://example.com/cover.jpg",
        "发布时间": "2026-06-19T18:00:00+08:00",
        "作品ID": "def456",
    }


def _nested_note_data():
    return {
        "作品标题": "nested title",
        "作品描述": "nested desc",
        "作者昵称": "littlekycap",
        "作品类型": "图集",
        "下载地址": [
            "https://example.com/nested1.jpg",
            "https://example.com/nested2.jpg",
        ],
        "发布时间": "2026-06-18T12:00:00+08:00",
        "作品ID": "ghi789",
    }


class _FakeXHS:
    def __init__(self, data_map):
        self._data_map = data_map

    async def extract(self, url, download=False, data=True):  # noqa: ARG002
        return self._data_map.get(url, [])


def test_xiaohongshu_image_note() -> None:
    fetcher = XiaohongshuFetcher(
        urls=["https://www.xiaohongshu.com/explore/abc123"],
    )
    fetcher._xhs = _FakeXHS({"https://www.xiaohongshu.com/explore/abc123": [_image_note_data()]})

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
    )
    fetcher._xhs = _FakeXHS({"https://www.xiaohongshu.com/explore/def456": [_video_note_data()]})

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
    )
    fetcher._xhs = _FakeXHS({"https://www.xiaohongshu.com/explore/ghi789": [_nested_note_data()]})

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
    )

    class FakeXHS:
        async def extract(self, url, download=False, data=True):  # noqa: ARG002
            if "bad" in url:
                raise RuntimeError("extract failed")
            return [_image_note_data()]

    fetcher._xhs = FakeXHS()
    items = asyncio.run(fetcher.fetch(_request()))

    assert len(items) == 2


def test_xiaohongshu_limit_respected() -> None:
    fetcher = XiaohongshuFetcher(
        urls=[
            "https://www.xiaohongshu.com/explore/1",
            "https://www.xiaohongshu.com/explore/2",
            "https://www.xiaohongshu.com/explore/3",
        ],
    )
    fetcher._xhs = _FakeXHS({
        "https://www.xiaohongshu.com/explore/1": [_image_note_data()],
        "https://www.xiaohongshu.com/explore/2": [_image_note_data()],
        "https://www.xiaohongshu.com/explore/3": [_image_note_data()],
    })
    items = asyncio.run(fetcher.fetch(_request(limit=2)))
    assert len(items) == 2


def test_xiaohongshu_returns_empty_on_invalid_data() -> None:
    fetcher = XiaohongshuFetcher(
        urls=["https://www.xiaohongshu.com/explore/empty"],
    )
    fetcher._xhs = _FakeXHS({"https://www.xiaohongshu.com/explore/empty": [{}]})
    items = asyncio.run(fetcher.fetch(_request()))
    assert items == []
