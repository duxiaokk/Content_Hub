"""请求超时 + 降级中间件

超时控制:
  TIMEOUT_ENABLED=true
  API_TIMEOUT_SECONDS=30     # API 请求超时时间
  AI_TIMEOUT_SECONDS=120     # AI/LLM 请求超时时间

降级策略:
  DEGRADATION_ENABLED=true
  CIRCUIT_BREAKER_THRESHOLD=5  # 连续失败 N 次后熔断
  CIRCUIT_BREAKER_TIMEOUT=60   # 熔断恢复时间
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Callable

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.error_codes import ErrorCode

TIMEOUT_ENABLED = os.getenv("TIMEOUT_ENABLED", "false").lower() == "true"
API_TIMEOUT = int(os.getenv("API_TIMEOUT_SECONDS", "30"))
AI_TIMEOUT = int(os.getenv("AI_TIMEOUT_SECONDS", "120"))

DEGRADATION_ENABLED = os.getenv("DEGRADATION_ENABLED", "false").lower() == "true"
CB_THRESHOLD = int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "5"))
CB_TIMEOUT = int(os.getenv("CIRCUIT_BREAKER_TIMEOUT", "60"))


# ------------------------------------------------------------------
# 熔断器
# ------------------------------------------------------------------

class CircuitBreaker:
    """简单的熔断器实现。"""

    def __init__(self, name: str, threshold: int = 5, recovery_timeout: int = 60) -> None:
        self.name = name
        self.threshold = threshold
        self.recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._open = False

    @property
    def is_open(self) -> bool:
        """熔断器是否打开。"""
        if not self._open:
            return False
        if time.time() - self._last_failure_time > self.recovery_timeout:
            # 半开状态，允许一次请求
            self._open = False
            self._failure_count = 0
            return False
        return True

    def success(self) -> None:
        self._failure_count = 0
        self._open = False

    def failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.threshold:
            self._open = True


# 全局熔断器实例
_breakers: dict[str, CircuitBreaker] = {}

def get_circuit_breaker(name: str) -> CircuitBreaker:
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(name, CB_THRESHOLD, CB_TIMEOUT)
    return _breakers[name]


# ------------------------------------------------------------------
# 超时中间件
# ------------------------------------------------------------------

class TimeoutMiddleware(BaseHTTPMiddleware):
    """API 请求超时控制中间件。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        if not TIMEOUT_ENABLED or not request.url.path.startswith("/api/"):
            return await call_next(request)

        # AI 接口使用更长的超时
        timeout = AI_TIMEOUT if "/api/v1/ai" in request.url.path else API_TIMEOUT

        try:
            return await asyncio.wait_for(call_next(request), timeout=timeout)
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail={"code": ErrorCode.TIMEOUT, "data": None, "message": f"请求超时 ({timeout}s)"},
            )
