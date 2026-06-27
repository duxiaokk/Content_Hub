from __future__ import annotations

import asyncio

from apps.fetcher_engine.connectors.xiaohongshu import fetcher as xhs_fetcher_module
from apps.fetcher_engine.connectors.xiaohongshu.fetcher import XiaohongshuFetcher


def _request(limit: int = 10):
    return type(
        "Request",
        (),
        {"source_name": "Xiaohongshu", "lookback_hours": 24, "limit": limit, "cursor": None, "options": {}},
    )()


class _FakeBridge:
    last_init: dict | None = None

    def __init__(self, **kwargs):  # noqa: ANN003
        type(self).last_init = dict(kwargs)

    async def extract_many(self, urls):  # noqa: ANN001
        return [
            {
                "作品ID": "abc123",
                "作品标题": "西安美食探店",
                "作品描述": "这家泡馍真的绝了！",
                "作品类型": "图文",
                "作品链接": str(urls[0]),
                "发布时间": "2026-06-20T10:00:00+08:00",
                "作者昵称": "littlekycap",
                "作者ID": "user123",
                "作品标签": "西安美食,探店",
                "下载地址": "https://example.com/img1.jpg https://example.com/img2.png",
                "动图地址": "NaN NaN",
                "点赞数量": 1287,
                "评论数量": 10,
                "收藏数量": 130,
                "分享数量": 9,
            },
            {
                "作品ID": "def456",
                "作品标题": "Vlog 日常",
                "作品描述": "今天去了大雁塔~",
                "作品类型": "视频",
                "作品链接": "https://www.xiaohongshu.com/discovery/item/def456?xsec_token=test",
                "发布时间": "2026-06-19T18:00:00+08:00",
                "作者昵称": "littlekycap",
                "作者ID": "user123",
                "作品标签": ["旅行", "Vlog"],
                "下载地址": "https://example.com/video.mp4",
                "动图地址": "NaN",
                "点赞数量": 500,
                "评论数量": 20,
                "收藏数量": 12,
                "分享数量": 6,
            },
            {},
        ]


def test_xiaohongshu_fetcher_maps_bridge_payload(monkeypatch) -> None:
    monkeypatch.setattr(xhs_fetcher_module, "XhsDownloaderBridge", _FakeBridge)
    fetcher = XiaohongshuFetcher(
        urls=["https://www.xiaohongshu.com/discovery/item/abc123?xsec_token=test"],
        cookie="cookie=value",
        proxy="http://127.0.0.1:7890",
        timeout=15,
        user_agent="custom-agent",
    )

    items = asyncio.run(fetcher.fetch(_request()))

    assert len(items) == 2
    image_item = items[0]
    assert image_item.source_type == "xiaohongshu"
    assert image_item.source_id == "abc123"
    assert image_item.title == "西安美食探店"
    assert "泡馍" in (image_item.raw_content or "")
    assert "![图片](https://example.com/img1.jpg)" in (image_item.raw_content or "")
    assert image_item.metadata["type"] == "image"
    assert image_item.metadata["images"] == ["https://example.com/img1.jpg", "https://example.com/img2.png"]
    assert image_item.metadata["author"] == "littlekycap"
    assert image_item.metadata["likes"] == 1287
    assert image_item.metadata["tags"] == ["西安美食", "探店"]

    video_item = items[1]
    assert video_item.source_id == "def456"
    assert video_item.title == "Vlog 日常"
    assert "[视频](https://example.com/video.mp4)" in (video_item.raw_content or "")
    assert video_item.metadata["type"] == "video"
    assert video_item.metadata["video_url"] == "https://example.com/video.mp4"
    assert video_item.metadata["cover_url"] is None

    assert _FakeBridge.last_init == {
        "cookie": "cookie=value",
        "proxy": "http://127.0.0.1:7890",
        "timeout": 15,
        "user_agent": "custom-agent",
    }


def test_xiaohongshu_empty_urls() -> None:
    fetcher = XiaohongshuFetcher(urls=[])
    items = asyncio.run(fetcher.fetch(_request()))
    assert items == []


def test_xiaohongshu_limit_respected(monkeypatch) -> None:
    monkeypatch.setattr(xhs_fetcher_module, "XhsDownloaderBridge", _FakeBridge)
    fetcher = XiaohongshuFetcher(
        urls=[
            "https://www.xiaohongshu.com/discovery/item/1",
            "https://www.xiaohongshu.com/discovery/item/2",
        ]
    )
    items = asyncio.run(fetcher.fetch(_request(limit=1)))
    assert len(items) == 1
    assert items[0].source_id == "abc123"


def test_xiaohongshu_returns_empty_on_invalid_data(monkeypatch) -> None:
    class _InvalidBridge:
        def __init__(self, **kwargs):  # noqa: ANN003
            del kwargs

        async def extract_many(self, urls):  # noqa: ANN001
            del urls
            return [{"作品链接": "https://www.xiaohongshu.com/explore/abc789"}]

    monkeypatch.setattr(xhs_fetcher_module, "XhsDownloaderBridge", _InvalidBridge)
    fetcher = XiaohongshuFetcher(urls=["https://www.xiaohongshu.com/explore/abc789"])
    items = asyncio.run(fetcher.fetch(_request()))
    assert items == []


def test_xiaohongshu_extract_source_id() -> None:
    assert XiaohongshuFetcher._extract_source_id(
        "https://www.xiaohongshu.com/discovery/item/abc123?xsec_token=test"
    ) == "abc123"
    assert XiaohongshuFetcher._extract_source_id(
        "https://www.xiaohongshu.com/user/profile/user123/abc456?xsec_token=test"
    ) == "abc456"
    assert XiaohongshuFetcher._extract_source_id("https://www.xiaohongshu.com/explore/abc789") == "abc789"
