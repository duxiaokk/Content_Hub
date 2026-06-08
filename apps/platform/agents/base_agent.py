"""Agent 基础框架

提供标准化的 Agent 生命周期管理：
  - FastAPI 服务创建
  - 自动注册到调度中心
  - 定时心跳上报
  - 异常上报与协同重试
  - 负载信息暴露
  - 统一错误处理
"""
from __future__ import annotations

import asyncio
import os
import time
import traceback
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any, Callable, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, status

from core.observability import init_observability
from agents.schemas import (
    AgentErrorReport,
    AgentHeartbeat,
)


def _env(key: str, default: str = "") -> str:
    return str(os.getenv(key, default)).strip()


class AgentConfig:
    """Agent 配置。"""

    def __init__(self, **kwargs: Any) -> None:
        self.agent_key: str = kwargs.get("agent_key", _env("AGENT_KEY", "unknown-agent"))
        self.agent_name: str = kwargs.get("agent_name", _env("AGENT_NAME", self.agent_key))
        self.base_url: str = kwargs.get("base_url", _env("AGENT_BASE_URL", "http://127.0.0.1:8000"))
        self.task_types: list[str] = kwargs.get("task_types", [])
        self.health_path: str = kwargs.get("health_path", "/health")
        self.capabilities: dict[str, Any] = kwargs.get("capabilities", {})
        self.max_concurrency: int = int(kwargs.get("max_concurrency", 10))
        self.heartbeat_interval_seconds: float = float(kwargs.get("heartbeat_interval_seconds", 30.0))

        self.scheduler_url: str = kwargs.get("scheduler_url", _env("SCHEDULER_CENTER_URL", "http://127.0.0.1:8010"))
        self.internal_token: str = kwargs.get("internal_token", _env("SCHEDULER_INTERNAL_TOKEN", "local-dev-scheduler-token"))

        self.llm_api_key: str = kwargs.get("llm_api_key", _env("LLM_API_KEY", ""))
        self.llm_base_url: str = kwargs.get("llm_base_url", _env("LLM_BASE_URL", "https://api.deepseek.com"))
        self.llm_model: str = kwargs.get("llm_model", _env("LLM_MODEL", "deepseek-v4-flash"))
        self.mock_llm: bool = str(kwargs.get("mock_llm", _env("MOCK_LLM", "false"))).lower() == "true"


class BaseAgent(ABC):
    """Agent 基类 — 所有 Agent 服务的抽象基类。"""

    def __init__(self, config: AgentConfig | None = None) -> None:
        self.config = config or AgentConfig()
        self._start_time = time.time()
        self._active_requests = 0
        self._total_requests = 0
        self._error_count = 0
        self._latencies: list[float] = []  # 最近 100 个请求延迟
        self._heartbeat_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # 子类必须实现
    # ------------------------------------------------------------------

    @abstractmethod
    async def execute(self, task_type: str, payload: dict[str, Any], trace_id: str | None) -> dict[str, Any]:
        """执行 Agent 核心逻辑。返回结果 dict。"""
        ...

    def supported_task_types(self) -> list[str]:
        """返回此 Agent 支持的任务类型列表。"""
        return self.config.task_types

    # ------------------------------------------------------------------
    # 负载信息
    # ------------------------------------------------------------------

    def get_heartbeat(self) -> AgentHeartbeat:
        """获取当前心跳/负载信息。"""
        avg_latency = sum(self._latencies) / len(self._latencies) if self._latencies else 0.0
        return AgentHeartbeat(
            agent_key=self.config.agent_key,
            status="healthy" if self._error_count < 10 else "degraded",
            current_load=self._active_requests,
            max_load=self.config.max_concurrency,
            avg_latency_ms=avg_latency,
            error_count=self._error_count,
            uptime_seconds=time.time() - self._start_time,
        )

    def get_capability_tags(self) -> dict[str, Any]:
        """返回能力标签。"""
        return {
            "agent_key": self.config.agent_key,
            "name": self.config.agent_name,
            "task_types": self.supported_task_types(),
            "capabilities": self.config.capabilities,
            "max_concurrency": self.config.max_concurrency,
            "current_load": self._active_requests,
        }

    # ------------------------------------------------------------------
    # 注册与心跳
    # ------------------------------------------------------------------

    async def register(self) -> bool:
        """向调度中心注册自身。"""
        url = f"{self.config.scheduler_url}/api/internal/scheduler/agents/register"
        payload = {
            "agent_key": self.config.agent_key,
            "name": self.config.agent_name,
            "base_url": self.config.base_url,
            "task_types": self.supported_task_types(),
            "health_path": self.config.health_path,
            "capabilities": self.config.capabilities,
            "status": 1,
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    url, json=payload,
                    headers={"x-internal-token": self.config.internal_token},
                )
            return 200 <= resp.status_code < 300
        except Exception:
            return False

    async def start_heartbeat(self) -> None:
        """启动定时心跳。"""
        async def _loop():
            while True:
                await asyncio.sleep(self.config.heartbeat_interval_seconds)
                try:
                    await self.register()  # 注册接口即心跳
                except Exception:
                    pass
        self._heartbeat_task = asyncio.create_task(_loop())

    async def stop_heartbeat(self) -> None:
        """停止心跳。"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

    # ------------------------------------------------------------------
    # 异常上报
    # ------------------------------------------------------------------

    async def report_error(self, error: AgentErrorReport) -> bool:
        """向调度中心上报异常。"""
        url = f"{self.config.scheduler_url}/api/internal/scheduler/agents/error"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    url, json=error.model_dump(),
                    headers={"x-internal-token": self.config.internal_token},
                )
            return 200 <= resp.status_code < 300
        except Exception:
            return False

    # ------------------------------------------------------------------
    # 请求追踪装饰器
    # ------------------------------------------------------------------

    def _track_request(self, func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            self._active_requests += 1
            self._total_requests += 1
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                latency = (time.time() - start) * 1000
                self._latencies.append(latency)
                if len(self._latencies) > 100:
                    self._latencies.pop(0)
                return result
            except Exception:
                self._error_count += 1
                raise
            finally:
                self._active_requests -= 1
        return wrapper

    # ------------------------------------------------------------------
    # FastAPI 服务工厂
    # ------------------------------------------------------------------

    def create_app(self) -> FastAPI:
        """创建包含标准端点（/health, /capabilities, /heartbeat, /api/internal/agent/run）的 FastAPI app。"""
        agent = self

        @asynccontextmanager
        async def lifespan(_: FastAPI):
            await agent.register()
            await agent.start_heartbeat()
            try:
                yield
            finally:
                await agent.stop_heartbeat()

        app = FastAPI(
            title=f"{agent.config.agent_name} Agent",
            version="0.1.0",
            lifespan=lifespan,
        )

        # 可观测性初始化
        init_observability(f"agent.{agent.config.agent_key}", app)

        # 鉴权
        def _verify(request: Request) -> None:
            token = request.headers.get("x-internal-token")
            if not token or token != agent.config.internal_token:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")

        @app.get("/health")
        async def health_endpoint() -> dict[str, str]:
            return {"status": "ok", "agent": agent.config.agent_key}

        @app.get("/capabilities")
        async def capabilities_endpoint(request: Request) -> dict[str, Any]:
            _verify(request)
            return agent.get_capability_tags()

        @app.get("/heartbeat")
        async def heartbeat_endpoint(request: Request) -> AgentHeartbeat:
            _verify(request)
            return agent.get_heartbeat()

        @app.post("/api/internal/agent/run")
        async def run_agent_endpoint(request: Request, body: dict[str, Any]) -> dict[str, Any]:
            _verify(request)
            task_type = str(body.get("task_type") or "").strip()
            trace_id = body.get("trace_id")
            payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}

            supported = agent.supported_task_types()
            if supported and task_type not in supported and "*" not in supported:
                await agent.report_error(AgentErrorReport(
                    agent_key=agent.config.agent_key,
                    error_type="unsupported_task_type",
                    error_message=f"Unsupported task_type: {task_type}",
                    task_id=body.get("task_id"),
                    trace_id=trace_id,
                    severity="low",
                ))
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"unsupported task_type: {task_type}",
                )

            execute = agent._track_request(agent.execute)
            try:
                result = await execute(task_type=task_type, payload=payload, trace_id=trace_id)
                return {"ok": True, "task_type": task_type, "result": result}
            except HTTPException:
                raise
            except Exception as exc:
                await agent.report_error(AgentErrorReport(
                    agent_key=agent.config.agent_key,
                    error_type=exc.__class__.__name__,
                    error_message=str(exc)[:500],
                    task_id=body.get("task_id"),
                    trace_id=trace_id,
                    retry_recommended=True,
                    severity="medium",
                    context={"traceback": traceback.format_exc()[-2000:]},
                ))
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Agent error: {exc}",
                ) from exc

        return app


# =========================================================================
# 快捷工厂函数
# =========================================================================


def create_agent_app(agent: BaseAgent, *, title: str | None = None) -> FastAPI:
    """使用 BaseAgent 创建标准 FastAPI 应用。"""
    return agent.create_app()
