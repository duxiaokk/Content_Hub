"""Demo API: /demo 页的交互式任务提交流程。

- POST /api/demo/submit  → 提交任务（真实调用 Scheduler Center，或降级模拟）
- GET  /api/demo/status/{task_id} → 轮询任务状态（从 Scheduler Center 查询）
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from scheduler_client import SchedulerClient, get_scheduler_client
from web_deps import get_optional_user


class DemoSubmitRequest(BaseModel):
    task_type: str = "demo.echo"
    payload: Optional[dict] = None

router = APIRouter()

# 内存模拟存储（Scheduler Center 未运行时的降级方案）
_mock_store: dict[str, dict] = {}


def _is_scheduler_reachable(client: SchedulerClient) -> bool:
    try:
        import httpx
        r = httpx.get(client.base_url + "/health", timeout=httpx.Timeout(2.0))
        return r.status_code == 200
    except Exception:
        return False


@router.post("/api/demo/submit")
def demo_submit(
    body: DemoSubmitRequest,
    _user: Optional[str] = Depends(get_optional_user),
):
    """提交一个演示任务。优先调真实 Scheduler，失败则降级为内存模拟。"""
    task_type = body.task_type
    payload = body.payload

    client = get_scheduler_client()
    live = _is_scheduler_reachable(client)

    if live and task_type != "demo.echo":
        try:
            result = client.submit_task(
                task_type=task_type,
                payload=payload or {},
                trace_id=str(uuid.uuid4())[:8],
            )
            return {
                "mode": "live",
                "task_id": result.get("task_id", "unknown"),
                "status": result.get("status", "pending"),
            }
        except Exception:
            pass  # 降级到 mock

    # Mock 模式
    task_id = str(uuid.uuid4())[:12]
    _mock_store[task_id] = {
        "task_type": task_type,
        "payload": payload or {},
        "status": "pending",
        "logs": [
            "task created (mock)",
        ],
        "result": None,
        "memory_key": None,
    }
    return {
        "mode": "mock",
        "task_id": task_id,
        "status": "pending",
    }


@router.get("/api/demo/status/{task_id}")
def demo_status(task_id: str):
    """轮询任务状态。"""
    # 先查 mock store
    if task_id in _mock_store:
        task = _mock_store[task_id]
        # 模拟进度推进
        statuses = ["pending", "running", "succeeded"]
        idx = statuses.index(task["status"]) if task["status"] in statuses else 0
        if idx < len(statuses) - 1:
            task["status"] = statuses[idx + 1]
            task["logs"].append(f"mock: {task['status']}")
            if task["status"] == "succeeded":
                task["result"] = {
                    "approved": True,
                    "score": 0.92,
                    "summary": f"Mock execution completed for {task['task_type']}",
                }
                task["memory_key"] = f"demo:result:{task_id}"
        return task

    # 尝试查真实 Scheduler
    client = get_scheduler_client()
    if _is_scheduler_reachable(client):
        try:
            import httpx
            r = httpx.get(
                client.base_url + f"/api/internal/scheduler/tasks/{task_id}",
                headers={"x-internal-token": client._config.internal_token},
                timeout=httpx.Timeout(5.0),
            )
            if r.status_code == 200:
                data = r.json()
                return {
                    "mode": "live",
                    "task_id": task_id,
                    "status": data.get("status", "unknown"),
                    "logs": data.get("logs", []),
                    "result": data.get("result"),
                    "memory_key": data.get("memory_key"),
                }
        except Exception:
            raise HTTPException(404, "task not found")
    raise HTTPException(404, "task not found")
