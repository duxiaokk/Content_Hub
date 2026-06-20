from __future__ import annotations

import logging
from typing import Any

from apps.fetcher_engine.runtime.base import BaseFetcher
from apps.workflow_engine.registry.contracts import FetchRequest, SourceItem

logger = logging.getLogger(__name__)


class XiaohongshuFetcher(BaseFetcher):
    """小红书笔记抓取器，直接内嵌 XHS-Downloader 核心能力。

    通过 import XHS-Downloader 的 XHS 类，直接调用其 extract 方法获取笔记详情，
    无需单独启动外部 HTTP 服务。
    """

    name = "xiaohongshu"
    source_type = "xiaohongshu"

    def __init__(
        self,
        urls: list[str] | None = None,
        cookie: str = "",
        proxy: str | None = None,
        timeout: int = 10,
        stream_key: str = "xiaohongshu:default",
    ) -> None:
        self.urls = urls or []
        self.cookie = cookie
        self.proxy = proxy
        self.timeout = timeout
        self.stream_key = stream_key
        self._xhs: Any = None

    def _get_xhs(self) -> Any:
        """懒加载 XHS 实例（单例模式）。"""
        if self._xhs is None:
            import sys

            xhs_path = r"D:\Python\content_hub\XHS-Downloader"
            if xhs_path not in sys.path:
                sys.path.insert(0, xhs_path)
            from source.application.app import XHS

            self._xhs = XHS(
                cookie=self.cookie,
                proxy=self.proxy,
                timeout=self.timeout,
                record_data=False,
                image_download=False,
                video_download=False,
                live_download=False,
                language="zh_CN",
            )
        return self._xhs

    async def fetch(self, request: FetchRequest) -> list[SourceItem]:
        target_urls = self.urls
        if not target_urls:
            logger.warning("XiaohongshuFetcher urls is empty, nothing to fetch")
            return []

        xhs = self._get_xhs()
        items: list[SourceItem] = []

        for url in target_urls:
            try:
                result = await xhs.extract(url, download=False, data=True)
            except Exception as exc:
                logger.warning("XHS extract failed for %s: %s", url, exc)
                continue

            if not result or not isinstance(result, list):
                continue

            for data in result:
                if not isinstance(data, dict):
                    continue
                item = self._to_source_item(url, data)
                if item is not None:
                    items.append(item)

        max_items = request.limit if request.limit > 0 else len(items)
        return items[:max_items]

    def _to_source_item(self, original_url: str, data: dict[str, Any]) -> SourceItem | None:
        title = data.get("作品标题")
        if not title or not isinstance(title, str) or not title.strip():
            return None

        content = data.get("作品描述")
        author = data.get("作者昵称")
        note_type = self._detect_type(data)
        downloads = data.get("下载地址", [])
        images = [u for u in downloads if isinstance(u, str) and not u.lower().endswith((".mp4", ".mov", ".avi", ".mkv"))]
        video_url = next((u for u in downloads if isinstance(u, str) and u.lower().endswith((".mp4", ".mov", ".avi", ".mkv"))), None)
        cover_url = data.get("封面")
        if not cover_url and images:
            cover_url = images[0]

        published_at = data.get("发布时间")
        source_id = data.get("作品ID") or self._extract_source_id(original_url)

        raw_content = self._build_raw_content(content, images, note_type, video_url)

        return SourceItem(
            source_type=self.source_type,
            source_id=source_id,
            title=title.strip(),
            source_url=original_url,
            raw_content=raw_content,
            metadata={
                "published_at": published_at,
                "author": author,
                "type": note_type,
                "images": images,
                "cover_url": cover_url,
                "video_url": video_url,
                "stream_key": self.stream_key,
                "note_id": source_id,
                "likes": data.get("点赞数量"),
                "comments": data.get("评论数量"),
                "collects": data.get("收藏数量"),
                "shares": data.get("分享数量"),
                "tags": data.get("作品标签", []),
            },
        )

    def _detect_type(self, data: dict[str, Any]) -> str:
        raw_type = data.get("作品类型", "")
        if isinstance(raw_type, str):
            if raw_type == "视频":
                return "video"
            if raw_type in ("图文", "图集"):
                return "image"
        # fallback: 根据下载地址推断
        downloads = data.get("下载地址", [])
        if downloads and isinstance(downloads, list):
            first = str(downloads[0]).lower() if downloads else ""
            if first.endswith((".mp4", ".mov", ".avi", ".mkv")):
                return "video"
            if first.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
                return "image"
        return "image"

    def _extract_source_id(self, url: str) -> str:
        if "explore/" in url:
            parts = url.split("explore/")
            if len(parts) > 1:
                return parts[1].split("?")[0].split("#")[0].strip("/")
        return url.split("/")[-1].split("?")[0] or url

    def _build_raw_content(self, content: str | None, images: list[str], note_type: str, video_url: str | None) -> str | None:
        parts: list[str] = []
        if content:
            parts.append(content)

        if note_type == "video" and video_url:
            parts.append(f"\n\n[视频]({video_url})")
        elif images:
            for img in images:
                parts.append(f"\n\n![图片]({img})")

        return "\n".join(parts) if parts else None
