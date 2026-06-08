from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


def _env(*keys: str) -> str | None:
    for key in keys:
        value = os.getenv(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return None


@dataclass(frozen=True, slots=True)
class SchedulerClientConfig:
    base_url: str
    internal_token: str
    timeout_seconds: float = 8.0


class SchedulerClient:
    def __init__(self, config: SchedulerClientConfig) -> None:
        self._config = config

    @property
    def base_url(self) -> str:
        return self._config.base_url.rstrip("/")

    def submit_task(
        self,
        *,
        task_type: str,
        payload: dict[str, Any] | None = None,
        trace_id: str | None = None,
        idempotency_key: str | None = None,
        max_retries: int | None = None,
        retry_delay_seconds: float | None = None,
    ) -> dict[str, Any]:
        url = self.base_url + "/api/internal/scheduler/tasks"
        headers: dict[str, str] = {"x-internal-token": self._config.internal_token}
        if trace_id:
            headers["x-trace-id"] = str(trace_id)
        if idempotency_key:
            headers["x-idempotency-key"] = str(idempotency_key)

        body: dict[str, Any] = {"task_type": str(task_type), "payload": payload or {}}
        if max_retries is not None:
            body["max_retries"] = int(max_retries)
        if retry_delay_seconds is not None:
            body["retry_delay_seconds"] = float(retry_delay_seconds)

        timeout = httpx.Timeout(float(self._config.timeout_seconds))
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {"value": data}

    async def submit_task_async(
        self,
        *,
        task_type: str,
        payload: dict[str, Any] | None = None,
        trace_id: str | None = None,
        idempotency_key: str | None = None,
        max_retries: int | None = None,
        retry_delay_seconds: float | None = None,
    ) -> dict[str, Any]:
        url = self.base_url + "/api/internal/scheduler/tasks"
        headers: dict[str, str] = {"x-internal-token": self._config.internal_token}
        if trace_id:
            headers["x-trace-id"] = str(trace_id)
        if idempotency_key:
            headers["x-idempotency-key"] = str(idempotency_key)

        body: dict[str, Any] = {"task_type": str(task_type), "payload": payload or {}}
        if max_retries is not None:
            body["max_retries"] = int(max_retries)
        if retry_delay_seconds is not None:
            body["retry_delay_seconds"] = float(retry_delay_seconds)

        timeout = httpx.Timeout(float(self._config.timeout_seconds))
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {"value": data}


def get_scheduler_client() -> SchedulerClient:
    base_url = _env("SCHEDULER_CENTER_URL") or "http://127.0.0.1:9001"
    token = _env("SCHEDULER_INTERNAL_TOKEN") or "local-dev-scheduler-token"
    timeout_raw = _env("SCHEDULER_CLIENT_TIMEOUT_SECONDS")
    try:
        timeout_seconds = float(timeout_raw) if timeout_raw is not None else 8.0
    except ValueError:
        timeout_seconds = 8.0
    return SchedulerClient(
        SchedulerClientConfig(
            base_url=base_url,
            internal_token=token,
            timeout_seconds=timeout_seconds,
        )
    )

