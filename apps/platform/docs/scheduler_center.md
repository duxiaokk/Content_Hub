# Scheduler Center

## 启动

在项目根目录执行：

```powershell
$env:SECRET_KEY="dev"
$env:SCHEDULER_INTERNAL_TOKEN="local-dev-scheduler-token"
$env:SCHEDULER_AGENT_ENDPOINTS="http://127.0.0.1:9002"
uvicorn scheduler_center.main:app --host 127.0.0.1 --port 9001 --reload
```

## 本地 Agent Stub（用于自测）

```powershell
$env:SCHEDULER_AGENT_TOKEN="local-dev-scheduler-token"
uvicorn scheduler_center.agent_stub:app --host 127.0.0.1 --port 9002 --reload
```

## API

### 提交任务

```bash
curl -X POST "http://127.0.0.1:9001/api/internal/scheduler/tasks" ^
  -H "Content-Type: application/json" ^
  -H "x-internal-token: local-dev-scheduler-token" ^
  -d "{\"task_type\":\"demo\",\"payload\":{\"hello\":\"world\"},\"max_retries\":2,\"retry_delay_seconds\":3}"
```

### 查询任务

```bash
curl "http://127.0.0.1:9001/api/internal/scheduler/tasks/<task_id>" ^
  -H "x-internal-token: local-dev-scheduler-token"
```

### 取消任务

```bash
curl -X POST "http://127.0.0.1:9001/api/internal/scheduler/tasks/<task_id>/cancel" ^
  -H "x-internal-token: local-dev-scheduler-token"
```

### 查看日志

```bash
curl "http://127.0.0.1:9001/api/internal/scheduler/tasks/<task_id>/logs?limit=200&offset=0" ^
  -H "x-internal-token: local-dev-scheduler-token"
```

## Agent 请求协议

调度中心会对每个 Agent 发起：

- Method: POST
- URL: `{agent_base}{SCHEDULER_AGENT_REQUEST_PATH}`
- Header: `x-internal-token: {SCHEDULER_AGENT_TOKEN 或 SCHEDULER_INTERNAL_TOKEN}`
- Body:
  - `task_id`: string
  - `task_type`: string
  - `payload`: object
  - `attempt_no`: number

2xx 视为成功，响应体会写入 `result_json`（JSON 解析失败会落为 `{"raw": "..."}"`）。

