"""
功能摘要：本文件提供网页开发常用的辅助工具，包括权限检查、限流和跨站请求伪造防护。

初学者指南：
这个文件专门存放"各个路由都可能用到的小工具"。
比如判断当前用户是不是管理员、获取访问者网络地址、防止接口被频繁刷请求等。
如果你要修改后台权限规则或调整请求频率限制，重点关注 is_admin() 和 RateLimiter 类。

主要成员：
- is_admin(): 检查给定用户名是否为系统管理员
- RateLimiter: 内存限流器，防止单个网络地址在短时间内发送过多请求
- get_or_set_csrf_cookie(): 生成并设置跨站请求伪造防护令牌，保护表单提交安全
- verify_csrf(): 校验请求中的令牌与浏览器 Cookie 是否一致
"""
from __future__ import annotations

import secrets
import threading
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, Optional

from fastapi import HTTPException, Request

import security
from core.config import settings

ADMIN_USERNAME = settings.admin_username


def is_admin(username: Optional[str]) -> bool:
    if not username:
        return False
    normalized = str(username).lower().replace("_", "")
    return normalized == ADMIN_USERNAME.lower().replace("_", "")


def get_optional_user(request: Request) -> Optional[str]:
    try:
        return security.get_current_user_from_cookie(request)
    except HTTPException:
        return None


def get_client_ip(request: Request) -> str:
    return (request.client.host if request.client else "") or "unknown"


class RateLimiter:
    """In-memory rate limiter for a single process."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = int(limit)
        self.window_seconds = int(window_seconds)
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: Optional[float] = None) -> bool:
        ts = float(now if now is not None else datetime.now(timezone.utc).timestamp())
        with self._lock:
            q = self._hits[key]
            cutoff = ts - self.window_seconds
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(ts)
            return True


comment_rate_limiter = RateLimiter(limit=60, window_seconds=60)


def get_or_set_csrf_cookie(request: Request, response: Any) -> str:
    token = request.cookies.get("csrf_token")
    if token:
        return token
    token = secrets.token_urlsafe(24)
    response.set_cookie("csrf_token", token, httponly=False, samesite="lax")
    return token


def verify_csrf(request: Request) -> None:
    cookie = request.cookies.get("csrf_token")
    header = request.headers.get("x-csrf-token")
    if not cookie or not header or cookie != header:
        raise HTTPException(status_code=403, detail="CSRF 校验失败")
