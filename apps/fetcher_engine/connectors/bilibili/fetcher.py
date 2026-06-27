"""Bilibili 采集器 — 直接使用 Bilibili 官方 API，不再依赖 RSSHub。

API 参考:
  - 用户视频列表: https://api.bilibili.com/x/space/arc/search?mid={uid}
  - 视频信息:     https://api.bilibili.com/x/web-interface/view?bvid={bvid}
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

import httpx

from apps.fetcher_engine.runtime.base import BaseFetcher
from apps.workflow_engine.registry.contracts import FetchRequest, SourceItem

logger = logging.getLogger(__name__)

_BILIBILI_API_BASE = "https://api.bilibili.com"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
_DEFAULT_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Referer": "https://www.bilibili.com/",
    "Accept": "application/json, text/plain, */*",
}


class BilibiliFetcher(BaseFetcher):
    name = "bilibili"
    source_type = "bilibili"

    def __init__(
        self,
        feed_url: str | None = None,
        stream_key: str = "bilibili:default",
        uid: int | None = None,
    ) -> None:
        """初始化 Bilibili 采集器。

        Args:
            feed_url: 保留参数，已无效（之前用于 RSSHub URL），兼容旧配置
            stream_key: 流标识，用于去重
            uid: Bilibili 用户 ID（可在用户主页 URL 中获取，如 bilibili.com/2267573）
        """
        self.uid = uid or 2267573  # 默认用户（可配置）
        self.stream_key = stream_key

    async def fetch(self, request: FetchRequest) -> list[SourceItem]:
        items: list[SourceItem] = []
        page = 1
        max_items = request.limit if request.limit > 0 else 20

        async with httpx.AsyncClient(headers=_DEFAULT_HEADERS, timeout=httpx.Timeout(15, connect=10)) as client:
            while len(items) < max_items:
                params = {
                    "mid": self.uid,
                    "ps": min(30, max_items - len(items)),
                    "pn": page,
                    "order": "pubdate",
                }
                url = f"{_BILIBILI_API_BASE}/x/space/arc/search?{urlencode(params)}"
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as exc:
                    logger.error("Bilibili 用户视频列表请求失败: uid=%s, page=%s, %s", self.uid, page, exc)
                    break

                if data.get("code") != 0:
                    logger.warning("Bilibili API 返回错误: uid=%s, code=%s, message=%s",
                                   self.uid, data.get("code"), data.get("message"))
                    break

                vlist = data.get("data", {}).get("list", {}).get("vlist", [])
                if not vlist:
                    break  # 没有更多视频了

                for v in vlist:
                    if len(items) >= max_items:
                        break
                    item = self._to_source_item(v)
                    if item:
                        items.append(item)

                page += 1
                if len(vlist) < params["ps"]:
                    break  # 最后一页

        return items

    def _to_source_item(self, v: dict[str, Any]) -> SourceItem | None:
        bvid = str(v.get("bvid") or "")
        title = str(v.get("title") or "").strip()
        description = str(v.get("description") or "").strip()
        author = str(v.get("author") or "").strip()
        mid = str(v.get("mid") or "")

        if not bvid or not title:
            return None

        source_url = f"https://www.bilibili.com/video/{bvid}"
        cover = str(v.get("pic") or "")
        play_count = v.get("play") or 0
        danmaku = v.get("video_review") or 0
        duration = v.get("length") or ""
        created_ts = v.get("created") or 0
        comment = v.get("comment") or 0
        tags_str = str(v.get("tag") or "")

        # 原始内容描述
        raw_parts: list[str] = [f"播放: {play_count}", f"弹幕: {danmaku}", f"评论: {comment}"]
        if description:
            raw_parts.append(f"\n{description[:200]}")

        return SourceItem(
            source_type=self.source_type,
            source_id=bvid,
            title=title,
            source_url=source_url,
            raw_content="\n".join(raw_parts) or None,
            metadata={
                "bvid": bvid,
                "author": author,
                "author_id": mid,
                "play_count": play_count,
                "danmaku_count": danmaku,
                "comment_count": comment,
                "duration": duration,
                "cover_url": cover,
                "published_at": str(created_ts),
                "tags": [t.strip() for t in tags_str.split(",") if t.strip()],
                "stream_key": self.stream_key,
            },
        )
