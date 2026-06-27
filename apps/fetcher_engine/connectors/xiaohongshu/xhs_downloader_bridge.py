"""直接使用 curl_cffi + xhshow 调小红书 API 采集笔记数据。

相比原来的 XHS-Downloader bridge，本实现：
  1. 不再依赖 XHS-Downloader 项目，只依赖 xhshow（已在项目中安装）
  2. xhshow 负责生成小红书 API 必需的 X-S 签名头
  3. curl_cffi 负责网络请求（模拟浏览器 TLS 指纹，绕过反爬 461）
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from typing import Any

from curl_cffi.requests import AsyncSession
from xhshow import Xhshow

logger = logging.getLogger(__name__)

# 小红书 API 端点
_FEED_API = "https://edith.xiaohongshu.com/api/sns/web/v1/feed"

# 提取笔记 ID 的正则（支持多种 URL 格式）
_NOTE_ID_REGEX = re.compile(
    r"(?:xiaohongshu\.com/(?:discovery/item|explore)/|/discovery/item/|/explore/|note_id=)([a-f0-9]{24})"
)

# 全局重用签名器（只初始化一次，避免每次重新生成密钥对）
_XHSHOW = Xhshow()


def _extract_note_id(url: str) -> str | None:
    """从小红书 URL 中提取 24 位笔记 ID。"""
    m = _NOTE_ID_REGEX.search(url)
    if m:
        return m.group(1)
    return None


def _parse_note_item(raw: dict[str, Any]) -> dict[str, Any] | None:
    """从 API 原始响应中提取标准化的笔记字段。"""
    note_card = raw.get("note_card") or {}
    if not note_card:
        return None

    # 基础信息
    display_title = note_card.get("display_title") or ""
    desc = note_card.get("desc") or ""
    note_id = note_card.get("note_id") or raw.get("note_id") or ""
    note_url = note_card.get("note_url") or f"https://www.xiaohongshu.com/discovery/item/{note_id}"
    user = note_card.get("user") or {}
    interact = note_card.get("interact_info") or {}
    image_list = note_card.get("image_list") or []
    video = note_card.get("video") or {}
    tag_list = note_card.get("tag_list") or []

    # 作者
    author_name = (user.get("nickname") or "").strip()
    author_id = (user.get("user_id") or "").strip()

    # 类型判断
    note_type = "video" if video and video.get("media", {}).get("stream", {}) else "image"

    # 图片/封面
    images: list[str] = []
    cover_url: str | None = None
    for img in image_list:
        url = (img.get("url_default") or img.get("url") or "").strip()
        if url:
            # 补全协议
            if url.startswith("//"):
                url = "https:" + url
            images.append(url)
    if images:
        cover_url = images[0]

    # 视频 URL
    video_url: str | None = None
    if video:
        stream = video.get("media", {}).get("stream", {})
        if stream:
            video_url = (stream.get("h264", [{}])[0].get("master_url")
                         or stream.get("h265", [{}])[0].get("master_url")
                         or "")

    # 标签
    tags: list[str] = []
    for tag in tag_list:
        t = (tag.get("name") or "").strip()
        if t:
            tags.append(t)

    # 互动数据
    likes = interact.get("liked_count") or interact.get("like_count") or ""
    comments = interact.get("comment_count") or ""
    collected = interact.get("collected_count") or ""
    shares = interact.get("share_count") or ""
    published_at = note_card.get("time") or interact.get("time") or ""

    # raw_content
    parts: list[str] = []
    if desc:
        parts.append(desc)
    if note_type == "video" and video_url:
        parts.append(f"\n\n[视频]({video_url})")
    elif images:
        for img_url in images:
            parts.append(f"\n\n![图片]({img_url})")

    return {
        "作品ID": note_id,
        "作品标题": display_title,
        "作品描述": desc,
        "作品类型": "视频" if note_type == "video" else "图文",
        "作品链接": note_url,
        "发布时间": str(published_at),
        "作者昵称": author_name,
        "作者ID": author_id,
        "作品标签": tags,
        "下载地址": images if note_type == "image" else ([video_url] if video_url else []),
        "动图地址": [],
        "点赞数量": likes,
        "评论数量": comments,
        "收藏数量": collected,
        "分享数量": shares,
    }


class XhsDownloaderBridge:
    """通过 httpx + xhshow 签名调用小红书 API 采集笔记数据。

    用法:
        bridge = XhsDownloaderBridge(cookie="...")
        results = await bridge.extract_many(["https://www.xiaohongshu.com/explore/..."])
    """

    def __init__(
        self,
        *,
        cookie: str | None = None,
        proxy: str | dict[str, Any] | None = None,
        timeout: int = 10,
        user_agent: str | None = None,
    ) -> None:
        self.cookie = cookie or ""
        self.proxy = proxy
        self.timeout = timeout
        self.user_agent = user_agent or ""

    async def extract_many(self, urls: Iterable[str]) -> list[dict[str, Any]]:
        """批量采集小红书笔记。"""
        items: list[dict[str, Any]] = []

        client_kwargs: dict[str, Any] = {
            "timeout": self.timeout,
        }
        if self.proxy:
            if isinstance(self.proxy, str):
                client_kwargs["proxies"] = {"all://": self.proxy}
            elif isinstance(self.proxy, dict):
                client_kwargs["proxies"] = self.proxy

        async with AsyncSession(**client_kwargs) as client:
            for url in urls:
                note_id = _extract_note_id(url)
                if not note_id:
                    logger.warning("无法从 URL 中提取笔记 ID: %s", url)
                    continue

                try:
                    detail = await self._fetch_note(client, note_id)
                    if detail:
                        items.append(detail)
                except Exception as exc:
                    logger.error("采集笔记 %s 失败: %s", note_id, exc)

        return items

    async def _fetch_note(self, client: AsyncSession, note_id: str) -> dict[str, Any] | None:
        """采集单篇笔记详情，使用 xhshow 签名。"""
        payload = {"source_note_id": note_id, "image_formats": ["jpg", "webp", "avif"], "extra": {"need_body_topic": 1}}

        # 用 xhshow 生成签名头（数据类 API 需要 xyw 格式，否则返回 406）
        signed_headers = _XHSHOW.sign_headers_post(
            uri=_FEED_API,
            cookies=self.cookie or "",
            payload=payload,
            sign_format="xyw",
        )

        # 组装完整请求头（参考 XHS-Downloader 的 HEADERS 结构）
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,"
                      "application/signed-exchange;v=b3;q=0.7",
            "Referer": "https://www.xiaohongshu.com/explore",
            "User-Agent": self.user_agent or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        }
        if self.cookie:
            headers["Cookie"] = self.cookie
        # 合并签名头
        for k, v in signed_headers.items():
            headers[k] = v

        resp = await client.post(
            _FEED_API,
            json=payload,
            headers=headers,
            impersonate="chrome124",
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("success") and data.get("data"):
            raw_items = data["data"].get("items") if isinstance(data["data"], dict) else data.get("items")
            if not raw_items and isinstance(data["data"], list):
                raw_items = data["data"]
            if not raw_items:
                raw_items = [data["data"]]
            if raw_items:
                return _parse_note_item(raw_items[0])

        logger.warning("小红书 API 返回非成功响应: note_id=%s, success=%s", note_id, data.get("success"))
        return None
