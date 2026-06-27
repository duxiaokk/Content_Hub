from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from apps.fetcher_engine.connectors.xiaohongshu.xhs_downloader_bridge import XhsDownloaderBridge
from apps.fetcher_engine.runtime.base import BaseFetcher
from apps.workflow_engine.registry.contracts import FetchRequest, SourceItem

logger = logging.getLogger(__name__)


class XiaohongshuFetcher(BaseFetcher):
    """通过 XHS-Downloader 采集小红书笔记数据。"""

    name = "xiaohongshu"
    source_type = "xiaohongshu"

    def __init__(
        self,
        urls: list[str] | None = None,
        stream_key: str = "xiaohongshu:default",
        cookie: str | None = None,
        proxy: str | dict[str, Any] | None = None,
        timeout: int = 10,
        user_agent: str | None = None,
    ) -> None:
        self.urls = [url.strip() for url in (urls or []) if isinstance(url, str) and url.strip()]
        self.stream_key = stream_key
        self.cookie = cookie or ""
        self.proxy = proxy
        self.timeout = timeout
        self.user_agent = user_agent or ""

    async def fetch(self, request: FetchRequest) -> list[SourceItem]:
        if not self.urls:
            logger.warning("XiaohongshuFetcher urls is empty, nothing to fetch")
            return []

        bridge = XhsDownloaderBridge(
            cookie=self.cookie,
            proxy=self.proxy,
            timeout=self.timeout,
            user_agent=self.user_agent,
        )
        details = await bridge.extract_many(self.urls)
        items = [self._to_source_item(detail) for detail in details]
        normalized_items = [item for item in items if item is not None]
        max_items = request.limit if request.limit > 0 else len(normalized_items)
        return normalized_items[:max_items]

    def _to_source_item(self, detail: dict[str, Any]) -> SourceItem | None:
        source_url = self._safe_text(detail.get("作品链接"))
        source_id = self._safe_text(detail.get("作品ID")) or self._extract_source_id(source_url)
        description = self._safe_text(detail.get("作品描述"))
        media_urls = self._split_media_urls(detail.get("下载地址"))
        live_photo_urls = self._split_media_urls(detail.get("动图地址"))
        title = self._safe_text(detail.get("作品标题")) or description or source_id
        if not title or (not description and not media_urls and not live_photo_urls):
            return None

        author = self._safe_text(detail.get("作者昵称"))
        author_id = self._safe_text(detail.get("作者ID"))
        published_at = self._safe_text(detail.get("发布时间"))
        note_type = self._normalize_type(detail.get("作品类型"))
        tags = self._normalize_tags(detail.get("作品标签"))

        video_url = media_urls[0] if note_type == "video" and media_urls else None
        images = media_urls if note_type != "video" else []
        cover_url = images[0] if images else None
        raw_content = self._build_raw_content(description, images, note_type, video_url)

        return SourceItem(
            source_type=self.source_type,
            source_id=source_id,
            title=title,
            source_url=source_url,
            raw_content=raw_content,
            metadata={
                "published_at": published_at,
                "author": author,
                "author_id": author_id,
                "type": note_type,
                "images": images,
                "cover_url": cover_url,
                "video_url": video_url,
                "live_photo_urls": live_photo_urls,
                "stream_key": self.stream_key,
                "note_id": source_id,
                "likes": detail.get("点赞数量"),
                "comments": detail.get("评论数量"),
                "collected": detail.get("收藏数量"),
                "shares": detail.get("分享数量"),
                "tags": tags,
            },
        )

    @staticmethod
    def _safe_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

    @staticmethod
    def _normalize_type(raw_type: Any) -> str:
        value = XiaohongshuFetcher._safe_text(raw_type)
        if value == "视频":
            return "video"
        if value in {"图文", "图集"}:
            return "image"
        return "image"

    @staticmethod
    def _normalize_tags(raw_tags: Any) -> list[str]:
        if isinstance(raw_tags, list):
            return [str(tag).strip() for tag in raw_tags if str(tag).strip()]
        if isinstance(raw_tags, str):
            separators = raw_tags.replace("，", ",").replace("、", ",")
            return [tag.strip() for tag in separators.split(",") if tag.strip()]
        return []

    @staticmethod
    def _split_media_urls(raw_urls: Any) -> list[str]:
        if isinstance(raw_urls, list):
            return [str(url).strip() for url in raw_urls if str(url).strip() and str(url).strip() != "NaN"]
        if isinstance(raw_urls, str):
            return [url.strip() for url in raw_urls.split() if url.strip() and url.strip() != "NaN"]
        return []

    @staticmethod
    def _extract_source_id(url: str) -> str:
        if not url:
            return ""
        parsed = urlparse(url)
        path = parsed.path
        if "/discovery/item/" in path:
            parts = path.split("/discovery/item/")
            if len(parts) > 1:
                return parts[1].split("?")[0]
        if "/user/profile/" in path:
            parts = path.split("/")
            if len(parts) >= 5:
                return parts[4].split("?")[0]
        return path.split("/")[-1].split("?")[0] or url

    @staticmethod
    def _build_raw_content(content: str, images: list[str], note_type: str, video_url: str | None) -> str | None:
        parts: list[str] = []
        if content:
            parts.append(content)
        if note_type == "video" and video_url:
            parts.append(f"\n\n[视频]({video_url})")
        elif images:
            for image_url in images:
                parts.append(f"\n\n![图片]({image_url})")
        return "\n".join(parts) if parts else None
