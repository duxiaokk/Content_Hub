"""编排客户端 SDK

扩展 SchedulerClient，增加编排运行管理方法。
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from scheduler_client import SchedulerClient, SchedulerClientConfig, get_scheduler_client


class OrchestrationClient:
    """编排客户端 — 在 SchedulerClient 基础上增加编排运行管理。"""

    def __init__(self, scheduler_client: SchedulerClient | None = None) -> None:
        self._scheduler = scheduler_client or get_scheduler_client()

    @property
    def base_url(self) -> str:
        return self._scheduler.base_url

    # ------------------------------------------------------------------
    # 编排运行
    # ------------------------------------------------------------------

    def submit_run(
        self,
        *,
        intent: str,
        name: str | None = None,
        context: dict[str, Any] | None = None,
        constraints: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """提交编排运行。"""
        url = self.base_url + "/api/internal/orchestration/runs"
        headers: dict[str, str] = {"x-internal-token": self._scheduler._config.internal_token}
        if trace_id:
            headers["x-trace-id"] = str(trace_id)

        body: dict[str, Any] = {"intent": str(intent)}
        if name:
            body["name"] = str(name)
        if context:
            body["context"] = context
        if constraints:
            body["constraints"] = constraints

        timeout = httpx.Timeout(float(self._scheduler._config.timeout_seconds))
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {"value": data}

    def get_run_status(self, run_id: str) -> dict[str, Any]:
        """查询编排运行状态。"""
        url = self.base_url + f"/api/internal/orchestration/runs/{run_id}"
        headers = {"x-internal-token": self._scheduler._config.internal_token}
        timeout = httpx.Timeout(float(self._scheduler._config.timeout_seconds))
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {"value": data}

    def list_runs(self, *, status: str | None = None, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        """查询运行列表。"""
        url = self.base_url + "/api/internal/orchestration/runs"
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        headers = {"x-internal-token": self._scheduler._config.internal_token}
        timeout = httpx.Timeout(float(self._scheduler._config.timeout_seconds))
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {"value": data}

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        """取消编排运行。"""
        url = self.base_url + f"/api/internal/orchestration/runs/{run_id}/cancel"
        headers = {"x-internal-token": self._scheduler._config.internal_token}
        timeout = httpx.Timeout(float(self._scheduler._config.timeout_seconds))
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {"value": data}

    async def submit_run_async(
        self,
        *,
        intent: str,
        name: str | None = None,
        context: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """异步提交编排运行。"""
        url = self.base_url + "/api/internal/orchestration/runs"
        headers: dict[str, str] = {"x-internal-token": self._scheduler._config.internal_token}
        if trace_id:
            headers["x-trace-id"] = str(trace_id)
        body: dict[str, Any] = {"intent": str(intent)}
        if name:
            body["name"] = str(name)
        if context:
            body["context"] = context

        timeout = httpx.Timeout(float(self._scheduler._config.timeout_seconds))
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {"value": data}


def get_orchestration_client() -> OrchestrationClient:
    return OrchestrationClient()
