from __future__ import annotations

import json
import logging
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from apps.fetcher_engine.runtime.base import BaseFetcher
from apps.workflow_engine.registry.contracts import FetchRequest, SourceItem


logger = logging.getLogger(__name__)


class XiaohongshuFetcher(BaseFetcher):
    """通过 XHS-Downloader API 抓取小红书笔记（图文 / 视频）。

    外部依赖：本地需运行 XHS-Downloader API 服务（默认 http://127.0.0.1:5556）。
    调用接口：POST /xhs/detail，参数 {"url": "笔记链接", "download": false}
    """

    name = "xiaohongshu"
    source_type = "xiaohongshu"
    user_agent = "content-hub-fetcher/1.0"
    default_api_base = "http://127.0.0.1:5556"

    def __init__(
        self,
        urls: list[str] | None = None,
        api_base_url: str | None = None,
        stream_key: str = "xiaohongshu:default",
    ) -> None:
        self.urls = urls or []
        self.api_base_url = (api_base_url or self.default_api_base).rstrip("/")
        self.stream_key = stream_key

    async def fetch(self, request: FetchRequest) -> list[SourceItem]:
        target_urls = self.urls
        if not target_urls:
            logger.warning("XiaohongshuFetcher urls is empty, nothing to fetch")
            return []

        items: list[SourceItem] = []
        for url in target_urls:
            try:
                data = self._call_detail_api(url)
            except RuntimeError as exc:
                logger.warning("XHS detail API failed: %s", exc)
                continue

            item = self._to_source_item(url, data)
            if item is not None:
                items.append(item)

        max_items = request.limit if request.limit > 0 else len(items)
        return items[:max_items]

    def _call_detail_api(self, url: str) -> dict[str, Any]:
        api_url = f"{self.api_base_url}/xhs/detail"
        payload = json.dumps({"url": url, "download": False}, ensure_ascii=False).encode("utf-8")
        req = Request(
            api_url,
            data=payload,
            headers={
                "User-Agent": self.user_agent,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(req, timeout=30) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except HTTPError as error:
            raise RuntimeError(f"xhs api http error: {error.code}") from error
        except URLError as error:
            raise RuntimeError(f"xhs api network error: {error.reason}") from error
        except TimeoutError as error:
            raise RuntimeError("xhs api request timeout") from error

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as error:
            raise RuntimeError("xhs api invalid json response") from error

        if not isinstance(data, dict):
            raise RuntimeError("xhs api response is not a dict")
        return data

    def _to_source_item(self, original_url: str, data: dict[str, Any]) -> SourceItem | None:
        # 灵活解析：支持两种可能的嵌套结构（扁平 / data.note）
        note = self._extract_note(data)
        if not note:
            return None

        title = self._first_str(note, "title", "作品标题")
        if not title:
            return None

        content = self._first_str(note, "desc", "description", "content", "作品描述")
        author = self._first_str(note, "nickname", "author", "user.nickname")
        note_type = self._detect_type(note)

        images = self._extract_images(note)
        video_url = self._extract_video_url(note)
        cover_url = self._first_str(note, "cover_url", "cover", "coverUrl")

        # 正文拼接图片 markdown，便于后续发布直接引用
        raw_content = self._build_raw_content(content, images, note_type, video_url)

        published_at = self._extract_published_at(note)

        return SourceItem(
            source_type=self.source_type,
            source_id=self._extract_source_id(original_url, note),
            title=title,
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
            },
        )

    def _extract_note(self, data: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(data, dict):
            return None
        # 尝试嵌套结构 data.note
        nested = data.get("data")
        if isinstance(nested, dict) and "note" in nested:
            note = nested["note"]
            if isinstance(note, dict):
                return note
        # 扁平结构
        return data

    def _first_str(self, obj: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            if "." in key:
                parts = key.split(".")
                cur = obj
                for part in parts:
                    cur = cur.get(part) if isinstance(cur, dict) else None
                if isinstance(cur, str) and cur.strip():
                    return cur.strip()
            else:
                value = obj.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    def _detect_type(self, note: dict[str, Any]) -> str:
        # 常见字段：type / 作品类型 / mediaType
        raw_type = self._first_str(note, "type", "作品类型", "mediaType")
        if raw_type:
            lowered = raw_type.lower()
            if "视频" in raw_type or "video" in lowered or "v" in lowered:
                return "video"
            if "图片" in raw_type or "image" in lowered or "图文" in raw_type or "normal" in lowered:
                return "image"
        # 根据 downloads 内容推断
        downloads = note.get("downloads")
        if isinstance(downloads, list) and downloads:
            first = str(downloads[0]).lower()
            if first.endswith((".mp4", ".mov", ".avi", ".mkv")):
                return "video"
            if first.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
                return "image"
        if note.get("video") or note.get("video_url") or note.get("videoUrl"):
            return "video"
        return "image"

    def _extract_images(self, note: dict[str, Any]) -> list[str]:
        # 尝试 downloads 列表（图片 URL 列表）
        downloads = note.get("downloads")
        if isinstance(downloads, list):
            urls = [str(u) for u in downloads if isinstance(u, str)]
            if urls and not urls[0].lower().endswith((".mp4", ".mov", ".avi", ".mkv")):
                return urls

        # 尝试 imageList / image_list
        image_list = note.get("imageList") or note.get("image_list")
        if isinstance(image_list, list):
            urls = []
            for img in image_list:
                if isinstance(img, dict):
                    url = img.get("url") or img.get("urlDefault") or img.get("url_default")
                    if isinstance(url, str):
                        urls.append(url)
                elif isinstance(img, str):
                    urls.append(img)
            return urls

        # 尝试 images 字段
        images = note.get("images")
        if isinstance(images, list):
            return [str(u) for u in images if isinstance(u, str)]

        return []

    def _extract_video_url(self, note: dict[str, Any]) -> str | None:
        # 尝试 downloads 列表（如果是视频，downloads 通常只有一个视频 URL）
        downloads = note.get("downloads")
        if isinstance(downloads, list) and downloads:
            first = str(downloads[0])
            if first.lower().endswith((".mp4", ".mov", ".avi", ".mkv")):
                return first

        # 尝试 video / video_url / videoUrl
        for key in ("video", "video_url", "videoUrl"):
            value = note.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                url = value.get("url") or value.get("src")
                if isinstance(url, str) and url.strip():
                    return url.strip()

        return None

    def _extract_published_at(self, note: dict[str, Any]) -> str | None:
        for key in ("published_at", "publishTime", "publish_time", "create_time", "time"):
            value = note.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _extract_source_id(self, original_url: str, note: dict[str, Any]) -> str:
        # 优先从 URL 提取作品 ID
        # 常见格式：https://www.xiaohongshu.com/explore/123456789
        if "explore/" in original_url:
            parts = original_url.split("explore/")
            if len(parts) > 1:
                sid = parts[1].split("?")[0].split("#")[0].strip("/")
                if sid:
                    return sid
        # 尝试 note 中的 id 字段
        for key in ("id", "note_id", "noteId", "source_id"):
            value = note.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, (int, float)):
                return str(int(value))
        # fallback：用 URL 哈希
        return original_url.split("/")[-1].split("?")[0] or original_url

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
