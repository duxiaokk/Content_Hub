# 新增 Agent 接入模板（Scheduler Center）

## 1. 接入约定

### 1.1 Agent 必须提供的 HTTP 接口

- 健康检查：`GET /health`
  - 返回 2xx 视为健康
  - 建议返回：`{"status":"ok"}`
- 执行入口：`POST /api/internal/agent/run`
  - Header：`X-Internal-Token: <token>`（调度中心会发送）
  - Body（调度中心固定字段）：

```json
{
  "task_id": "uuid",
  "task_type": "ado_repost.run_once",
  "payload": {},
  "attempt_no": 1,
  "trace_id": "uuid-or-string"
}
```

### 1.2 调度中心对 Agent 的成功/失败判定

- `2xx`：成功，任务标记为 `SUCCEEDED`，响应 JSON 会被保存为 `result_json`
- `4xx`：失败且不重试
- `5xx` 或网络超时：失败且按任务重试策略重试

## 2. Agent 注册（能力描述）

调度中心提供 Agent 注册表（SQLite）与 API。Agent 启动后应主动注册，并定期（例如 30~60 秒）重发注册请求当作心跳。

### 2.1 注册 API

- `POST /api/internal/scheduler/agents/register`
- Header：`X-Internal-Token: <SCHEDULER_INTERNAL_TOKEN>`

请求示例：

```json
{
  "agent_key": "ado-repost",
  "name": "Ado Repost Agent",
  "base_url": "http://127.0.0.1:9010",
  "task_types": ["ado_repost.run_once"],
  "health_path": "/health",
  "capabilities": {
    "version": "0.1.0",
    "owner": "team-a",
    "notes": "执行一次搬运并返回摘要"
  },
  "status": 1
}
```

### 2.2 task_type 匹配规则

- 调度中心按 `task_type` 过滤可用 Agent
- `task_types` 中包含 `"*"` 表示接收全部任务类型

## 3. FastAPI Agent 最小模板

```python
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status

app = FastAPI(title="My Agent", version="0.1.0")

def verify_token(request: Request) -> None:
    expected = os.getenv("MY_AGENT_INTERNAL_TOKEN") or os.getenv("SCHEDULER_INTERNAL_TOKEN") or "local-dev-scheduler-token"
    token = request.headers.get("x-internal-token")
    if not token or token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

@app.post("/api/internal/agent/run")
def run(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    verify_token(request)
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
    return {"ok": True, "task_id": body.get("task_id"), "task_type": body.get("task_type"), "result": payload}
```

## 4. 本地联调建议

- 启动调度中心（示例）：`uvicorn scheduler_center.main:app --host 127.0.0.1 --port 9000`
- 启动 Agent（示例）：`uvicorn my_agent.server:app --host 127.0.0.1 --port 9010`
- 注册 Agent 后提交任务：
  - `POST /api/internal/scheduler/tasks`
  - `{"task_type":"ado_repost.run_once","payload":{}}`

