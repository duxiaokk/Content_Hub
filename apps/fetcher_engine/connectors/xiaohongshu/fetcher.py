from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from apps.fetcher_engine.runtime.base import BaseFetcher
from apps.workflow_engine.registry.contracts import FetchRequest, SourceItem

logger = logging.getLogger(__name__)


class XiaohongshuFetcher(BaseFetcher):
    """小红书笔记抓取器，通过分享链接直接请求 HTML 解析笔记数据。

    无需 Cookie，无需 XHS-Downloader 服务。
    支持格式：
    - https://www.xiaohongshu.com/discovery/item/{note_id}?xsec_token=...
    - https://www.xiaohongshu.com/user/profile/{user_id}/{note_id}?xsec_token=...
    """

    name = "xiaohongshu"
    source_type = "xiaohongshu"
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
    request_timeout = 30

    def __init__(
        self,
        urls: list[str] | None = None,
        stream_key: str = "xiaohongshu:default",
    ) -> None:
        self.urls = urls or []
        self.stream_key = stream_key

    async def fetch(self, request: FetchRequest) -> list[SourceItem]:
        target_urls = self.urls
        if not target_urls:
            logger.warning("XiaohongshuFetcher urls is empty, nothing to fetch")
            return []

        items: list[SourceItem] = []
        for url in target_urls:
            try:
                item = self._fetch_single(url)
            except Exception as exc:
                logger.warning("XHS fetch failed for %s: %s", url, exc)
                continue
            if item is not None:
                items.append(item)

        max_items = request.limit if request.limit > 0 else len(items)
        return items[:max_items]

    def _fetch_single(self, url: str) -> SourceItem | None:
        """请求单条笔记页面，解析 HTML 中的笔记数据。"""
        # 标准化 URL（确保是完整的分享链接）
        normalized_url = self._normalize_url(url)

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.xiaohongshu.com",
        }

        with httpx.Client(timeout=self.request_timeout, follow_redirects=True) as client:
            resp = client.get(normalized_url, headers=headers)

        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")

        # 检查是否被重定向到 404/登录页
        if "404" in str(resp.url) or "error_code" in str(resp.url):
            raise RuntimeError("note not found or requires login")

        # 解析 HTML 中的 INITIAL_STATE
        return self._parse_html_to_item(url, resp.text)

    def _normalize_url(self, url: str) -> str:
        """将 user/profile 链接转换为 discovery/item 格式（如果适用）。"""
        # 如果是 /user/profile/{user_id}/{note_id}?xsec_token=... 格式
        # 保持原样，因为带 xsec_token 的链接可以直接访问
        return url.strip()

    def _parse_html_to_item(self, url: str, html: str) -> SourceItem | None:
        """从 HTML 文本解析笔记数据并转换为 SourceItem。"""
        data = self._parse_initial_state(html)
        if not data:
            return None
        return self._to_source_item(url, data)

    def _parse_initial_state(self, html: str) -> dict[str, Any] | None:
        """从 HTML 中提取并解析 window.__INITIAL_STATE__。"""
        match = re.search(r"window\.__INITIAL_STATE__=({.+?});?</script>", html, re.DOTALL)
        if not match:
            return None

        raw = match.group(1)
        # 修复 JavaScript 中的 undefined / NaN
        raw = raw.replace("undefined", "null").replace("NaN", "null")

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse INITIAL_STATE JSON: %s", exc)
            return None

        if not isinstance(data, dict):
            return None

        # 提取笔记数据
        note_section = data.get("note")
        if not isinstance(note_section, dict):
            return None

        detail_map = note_section.get("noteDetailMap")
        if not isinstance(detail_map, dict):
            return None

        # 找到第一个非 null 的笔记
        for key, value in detail_map.items():
            if key == "null":
                continue
            if isinstance(value, dict) and "note" in value:
                return value["note"]

        return None

    def _to_source_item(self, original_url: str, note: dict[str, Any]) -> SourceItem | None:
        title = note.get("title")
        if not title or not isinstance(title, str) or not title.strip():
            return None

        desc = note.get("desc") or ""
        author = note.get("user", {}).get("nickname") if isinstance(note.get("user"), dict) else None
        note_type = self._detect_type(note)
        images = self._extract_images(note)
        video_url = self._extract_video_url(note)
        cover_url = note.get("cover", {}).get("url") if isinstance(note.get("cover"), dict) else None
        if not cover_url and images:
            cover_url = images[0]

        published_at = note.get("time")
        source_id = note.get("id") or self._extract_source_id(original_url)

        raw_content = self._build_raw_content(desc, images, note_type, video_url)

        interact = note.get("interactInfo", {}) if isinstance(note.get("interactInfo"), dict) else {}
        tags = note.get("tagList", []) if isinstance(note.get("tagList"), list) else []
        tag_names = [t.get("name") for t in tags if isinstance(t, dict) and t.get("name")]

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
                "likes": interact.get("likedCount"),
                "comments": interact.get("commentCount"),
                "collected": interact.get("collectedCount"),
                "shares": interact.get("sharedCount"),
                "tags": tag_names,
            },
        )

    def _detect_type(self, note: dict[str, Any]) -> str:
        raw_type = note.get("type", "")
        if raw_type == "video":
            return "video"
        if raw_type == "normal":
            return "image"
        # fallback: 根据图片/视频字段推断
        if note.get("video"):
            return "video"
        if note.get("imageList"):
            return "image"
        return "image"

    def _extract_images(self, note: dict[str, Any]) -> list[str]:
        image_list = note.get("imageList", [])
        if not isinstance(image_list, list):
            return []
        urls = []
        for img in image_list:
            if isinstance(img, dict):
                url = img.get("url") or img.get("urlDefault")
                if url:
                    urls.append(url)
            elif isinstance(img, str):
                urls.append(img)
        return urls

    def _extract_video_url(self, note: dict[str, Any]) -> str | None:
        video = note.get("video")
        if isinstance(video, dict):
            return video.get("url") or video.get("src")
        return None

    def _extract_source_id(self, url: str) -> str:
        # 从 URL 中提取 note_id
        parsed = urlparse(url)
        path = parsed.path
        # 匹配 /discovery/item/xxx 或 /user/profile/xxx/xxx
        if "/discovery/item/" in path:
            parts = path.split("/discovery/item/")
            if len(parts) > 1:
                return parts[1].split("?")[0]
        if "/user/profile/" in path:
            parts = path.split("/")
            if len(parts) >= 5:
                return parts[4].split("?")[0]
        return path.split("/")[-1].split("?")[0] or url

    def _build_raw_content(self, content: str, images: list[str], note_type: str, video_url: str | None) -> str | None:
        parts: list[str] = []
        if content:
            parts.append(content)

        if note_type == "video" and video_url:
            parts.append(f"\n\n[视频]({video_url})")
        elif images:
            for img in images:
                parts.append(f"\n\n![图片]({img})")

        return "\n".join(parts) if parts else None
