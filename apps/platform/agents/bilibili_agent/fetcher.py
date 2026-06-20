"""Bilibili 抓取逻辑。

封装 B 站 API 调用，支持：
- 获取用户视频列表（wbi 签名 + 反爬头 + Cookie）
- 数据清洗为 SourceItem 结构
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from apps.platform.agents.bilibili_agent.wbi import _extract_filename, encode_wbi

logger = logging.getLogger(__name__)

# 反爬请求头
BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://space.bilibili.com",
    "Accept": "application/json, text/plain, */*",
}


def _build_headers(cookie: str | None = None) -> dict[str, str]:
    """构建请求头，支持注入 Cookie。"""
    headers = dict(BASE_HEADERS)
    if cookie:
        headers["Cookie"] = cookie
    return headers


def _resolve_cookie(payload: dict) -> str | None:
    """从 payload 或环境变量获取 B 站 Cookie。"""
    cookie = payload.get("cookie") or payload.get("SESSDATA")
    if not cookie:
        cookie = os.getenv("BILIBILI_COOKIE") or os.getenv("SESSDATA")
    return cookie


async def fetch_user_videos(
    mid: int,
    ps: int = 30,
    pn: int = 1,
    cookie: str | None = None,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    """抓取用户视频列表。

    策略：
    1. 如果提供了 keyword（UP 主昵称），直接用搜索 API
    2. 否则先尝试空间 API（wbi 签名），失败后回退到搜索 API

    Args:
        mid: UP 主 UID
        ps: 每页数量
        pn: 页码
        cookie: B 站 Cookie
        keyword: UP 主昵称（可选，用于搜索 API 回退）
    """
    headers = _build_headers(cookie)
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15.0) as client:
        # ---- 策略 A: 直接搜索（如果提供了 keyword）----
        if keyword:
            logger.info("Using search API with keyword=%s for mid=%s", keyword, mid)
            search_headers = dict(headers)
            search_headers["Referer"] = "https://search.bilibili.com"
            search_resp = await client.get(
                "https://api.bilibili.com/x/web-interface/search/type",
                params={
                    "keyword": keyword,
                    "search_type": "video",
                    "page": pn,
                    "order": "totalrank",
                },
                headers=search_headers,
            )
            search_data = search_resp.json()
            if search_data.get("code") == 0:
                videos = search_data.get("data", {}).get("result", [])
                filtered = [v for v in videos if str(v.get("mid")) == str(mid)]
                logger.info("Search API success: %d videos (filtered %d for mid=%s)", len(videos), len(filtered), mid)
                return filtered
            logger.warning("Search API failed: %s", search_data)

        # ---- 策略 B: 空间 API（wbi 签名） ----
        nav_resp = await client.get("https://api.bilibili.com/x/web-interface/nav")
        nav_data = nav_resp.json()
        wbi_img = nav_data.get("data", {}).get("wbi_img", {})
        img_key = _extract_filename(wbi_img.get("img_url", ""))
        sub_key = _extract_filename(wbi_img.get("sub_url", ""))

        if img_key and sub_key:
            params = {"mid": mid, "ps": ps, "pn": pn, "order": "pubdate", "tid": 0}
            signed_params = encode_wbi(params, img_key, sub_key)
            resp = await client.get(
                "https://api.bilibili.com/x/space/wbi/arc/search",
                params=signed_params,
            )
            data = resp.json()
            if data.get("code") == 0:
                vlist = data.get("data", {}).get("list", {}).get("vlist", [])
                logger.info("Space API success for user %s: %d videos", mid, len(vlist))
                return vlist
            logger.warning("Space API failed: %s", data.get("message"))

        # ---- 策略 C: 搜索 API 回退（从 acc_info 获取昵称）----
        # 增加延时避免频率限制
        await __import__("asyncio").sleep(0.5)
        info_resp = await client.get(
            "https://api.bilibili.com/x/space/acc/info",
            params={"mid": mid},
        )
        info_data = info_resp.json()
        name = info_data.get("data", {}).get("name", "")
        if name:
            logger.info("Fallback to search API for user %s (%s)", mid, name)
            search_headers = dict(headers)
            search_headers["Referer"] = "https://search.bilibili.com"
            search_resp = await client.get(
                "https://api.bilibili.com/x/web-interface/search/type",
                params={
                    "keyword": name,
                    "search_type": "video",
                    "page": pn,
                    "order": "totalrank",
                },
                headers=search_headers,
            )
            search_data = search_resp.json()
            if search_data.get("code") == 0:
                videos = search_data.get("data", {}).get("result", [])
                filtered = [v for v in videos if str(v.get("mid")) == str(mid)]
                logger.info("Search API fallback success: %d videos", len(filtered))
                return filtered
        else:
            logger.error("Cannot fetch user name for mid=%s", mid)

        return []


async def fetch_user_space_info(
    mid: int,
    cookie: str | None = None,
) -> dict[str, Any]:
    """获取用户空间基本信息（昵称、签名、头像等）。"""
    headers = _build_headers(cookie)
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=10.0) as client:
        resp = await client.get(
            "https://api.bilibili.com/x/space/acc/info",
            params={"mid": mid},
        )
        data = resp.json()
        if data.get("code") != 0:
            return {}
        return data.get("data", {})
