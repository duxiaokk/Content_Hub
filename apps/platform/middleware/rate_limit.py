"""请求限流中间件

基于内存的滑动窗口限流，支持：
  - 全局速率限制（所有 API 请求）
  - 每端点速率限制
  - 用户级别速率限制（基于 Cookie/Token 用户）

配置:
  RATE_LIMIT_ENABLED=true
  RATE_LIMIT_GLOBAL_RPS=100       # 全局每秒请求数
  RATE_LIMIT_PER_ENDPOINT_RPS=20  # 每端点每秒请求数
  RATE_LIMIT_PER_USER_RPS=10      # 每用户每秒请求数
  RATE_LIMIT_WINDOW_SECONDS=1     # 滑动窗口大小
"""
from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Callable

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from core.error_codes import ErrorCode

RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "false").lower() == "true"
GLOBAL_RPS = int(os.getenv("RATE_LIMIT_GLOBAL_RPS", "100"))
PER_ENDPOINT_RPS = int(os.getenv("RATE_LIMIT_PER_ENDPOINT_RPS", "20"))
PER_USER_RPS = int(os.getenv("RATE_LIMIT_PER_USER_RPS", "10"))
WINDOW_SECONDS = float(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "1"))

# 滑动窗口存储: 每个 key 对应一个时间戳列表
_windows: dict[str, list[float]] = defaultdict(list)


def _clean_window(key: str, now: float) -> list[float]:
    """清理过期的请求记录。"""
    window = _windows[key]
    cutoff = now - WINDOW_SECONDS
    while window and window[0] < cutoff:
        window.pop(0)
    return window


def is_rate_limited(key: str, max_rps: int) -> bool:
    """检查是否超出速率限制。"""
    now = time.time()
    window = _clean_window(key, now)
    if len(window) >= max_rps:
        return True
    window.append(now)
    return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """API 请求限流中间件。"""
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not RATE_LIMIT_ENABLED or not request.url.path.startswith("/api/"):
            return await call_next(request)

        # 用户标识
        user = _extract_user(request)

        # 检查三层限制
        if is_rate_limited("global", GLOBAL_RPS):
            raise HTTPException(
                status_code=429,
                detail={"code": ErrorCode.RATE_LIMITED, "data": None, "message": "请求过于频繁，请稍后再试"},
            )

        endpoint_key = f"endpoint:{request.url.path}"
        if is_rate_limited(endpoint_key, PER_ENDPOINT_RPS):
            raise HTTPException(
                status_code=429,
                detail={"code": ErrorCode.RATE_LIMITED, "data": None, "message": "该接口请求过于频繁"},
            )

        if user:
            user_key = f"user:{user}:{request.url.path}"
            if is_rate_limited(user_key, PER_USER_RPS):
                raise HTTPException(
                    status_code=429,
                    detail={"code": ErrorCode.RATE_LIMITED, "data": None, "message": "您的请求过于频繁"},
                )

        return await call_next(request)


def _extract_user(request: Request) -> str:
    """从请求中提取用户标识。"""
    # 尝试从 Cookie 中提取
    token = request.cookies.get("access_token")
    if token:
        return f"cookie:{token[-8:]}"

    # 尝试从 Authorization 头提取
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return f"bearer:{auth[-8:]}"

    # 使用客户端 IP
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
