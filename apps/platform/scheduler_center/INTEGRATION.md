## 组件与默认端口建议

- Scheduler Center：`http://127.0.0.1:8010`
- Comment Agent（示例 Agent）：`http://127.0.0.1:8020`
- Redis（可选，用于 Shared Memory 加速）：`redis://127.0.0.1:6379/0`

## 鉴权对齐（Scheduler ↔ Agent）

- 所有 Scheduler 内部接口与 Agent 内部执行接口统一使用请求头：
  - `x-internal-token: <TOKEN>`
- Scheduler Center 校验 `SCHEDULER_INTERNAL_TOKEN`。
- Agent 侧校验 `COMMENT_AGENT_INTERNAL_TOKEN`（兼容 `SCHEDULER_INTERNAL_TOKEN` 作为兜底）。
- Scheduler 调用 Agent 时，优先使用 `SCHEDULER_AGENT_TOKEN`；未设置则回退使用 `SCHEDULER_INTERNAL_TOKEN`。

## Scheduler Center 环境变量

- `SCHEDULER_DB_PATH` / `SCHEDULER_DATABASE_URL`：调度中心 DB（默认 SQLite）。
- `SCHEDULER_INTERNAL_TOKEN`：Scheduler 内部鉴权 token。
- `SCHEDULER_AGENT_ENDPOINTS`：Agent 基地址列表（逗号分隔），例如 `http://127.0.0.1:8020,http://127.0.0.1:8021`。
- `SCHEDULER_AGENT_REQUEST_PATH`：Agent 执行接口路径（默认 `/api/internal/agent/run`）。
- `SCHEDULER_AGENT_TOKEN`：Scheduler 调用 Agent 使用的 token（可与 `SCHEDULER_INTERNAL_TOKEN` 相同）。
- `SCHEDULER_MAX_CONCURRENCY`：分发并发上限（压测建议 ≥ 100）。
- `SCHEDULER_DEFAULT_MAX_RETRIES` / `SCHEDULER_DEFAULT_RETRY_DELAY_SECONDS`：默认重试策略。
- `SCHEDULER_HTTP_TIMEOUT_SECONDS`：调用 Agent 的超时。
- `SCHEDULER_CORS_ALLOW_ORIGINS`：CORS 白名单（逗号分隔），为空表示不启用 CORS。

## Agent（Comment Agent）环境变量

- `COMMENT_AGENT_INTERNAL_TOKEN`：Agent 内部鉴权 token（兼容 `SCHEDULER_INTERNAL_TOKEN`）。
- `COMMENT_AGENT_CORS_ALLOW_ORIGINS` / `CORS_ALLOW_ORIGINS`：CORS 白名单（逗号分隔），为空表示不启用 CORS。
- `DATABASE_URL`：Agent DB（默认 SQLite）。
- Shared Memory（Redis 可选，SQLite 必选）：
  - `MEMPOOL_REDIS_URL`：Redis 不可用时会自动降级到 SQLite。
  - `MEMPOOL_SQLITE_PATH`
  - `MEMPOOL_NAMESPACE`

## 探活端点

- Scheduler Center
  - `GET /health`：进程存活
  - `GET /ready`：DB 连通性（`SELECT 1`）
- Comment Agent
  - `GET /health`：进程存活
  - `GET /ready`：DB 连通性（`SELECT 1`）
  - `GET /mempool/health`：Shared Memory（Redis/SQLite）健康状态

## 本地启动（示例）

说明：以下示例命令默认以 Windows CMD 语法编写（`set` 设置环境变量、`^` 续行）。如使用 PowerShell，请改用 `$env:VAR="..."` 设置环境变量、使用反引号 `` ` `` 续行。

Scheduler Center：

```bash
cd "d:\Python\Personal Blog"
set SCHEDULER_INTERNAL_TOKEN=local-dev-scheduler-token
set SCHEDULER_AGENT_ENDPOINTS=http://127.0.0.1:8020
uvicorn scheduler_center.main:app --host 127.0.0.1 --port 8010
```

多 worker（提升提交吞吐，推荐用于 submit P95 优化）：

- API（禁用 dispatcher，开多 worker）

```bash
cd "d:\Python\Personal Blog"
set SCHEDULER_INTERNAL_TOKEN=local-dev-scheduler-token
set SCHEDULER_DISABLE_DISPATCHER=true
uvicorn scheduler_center.main:app --host 127.0.0.1 --port 8010 --workers 4
```

- Worker（单进程跑 dispatcher）

```bash
cd "d:\Python\Personal Blog"
set SCHEDULER_INTERNAL_TOKEN=local-dev-scheduler-token
python -m scheduler_center.worker
```

Redis 快速投递（目标：降低 /tasks submit P95）

- 说明：开启后，`POST /tasks` 先写 Redis（幂等也在 Redis 中判定），由 ingest_worker 异步落库到 SQLite，再由 dispatcher 执行。
- 运行前置：本机需有可用 Redis（建议 `redis://127.0.0.1:6379/0`）。

API（多 worker）：

```bash
cd "d:\Python\Personal Blog"
set SCHEDULER_INTERNAL_TOKEN=local-dev-scheduler-token
set SCHEDULER_DISABLE_DISPATCHER=true
set SCHEDULER_REDIS_URL=redis://127.0.0.1:6379/0
set SCHEDULER_FAST_SUBMIT_ENABLED=true
uvicorn scheduler_center.main:app --host 127.0.0.1 --port 8010 --workers 4
```

Ingest Worker（异步落库）：

```bash
cd "d:\Python\Personal Blog"
set SCHEDULER_INTERNAL_TOKEN=local-dev-scheduler-token
set SCHEDULER_REDIS_URL=redis://127.0.0.1:6379/0
set SCHEDULER_FAST_SUBMIT_ENABLED=true
python -m scheduler_center.ingest_worker
```

Dispatcher Worker（执行任务）：

```bash
cd "d:\Python\Personal Blog"
set SCHEDULER_INTERNAL_TOKEN=local-dev-scheduler-token
python -m scheduler_center.worker
```

Comment Agent：

```bash
cd "d:\Python\Comment_Agent"
set COMMENT_AGENT_INTERNAL_TOKEN=local-dev-scheduler-token
uvicorn app.main:app --host 127.0.0.1 --port 8020
```

## Task6：联调步骤（Scheduler ↔ Agent）

### 0. 前置检查

- 确保 Scheduler Center、Comment Agent 的 token 一致（示例均使用 `local-dev-scheduler-token`）
- 端口未被占用：`8010`（Scheduler）、`8020`（Agent）
- Scheduler Center 已启动且 dispatcher 未关闭（默认开启）

### 1. 探活与就绪

Scheduler Center：

```bash
curl -s http://127.0.0.1:8010/health
curl -s http://127.0.0.1:8010/ready
```

Comment Agent：

```bash
curl -s http://127.0.0.1:8020/health
curl -s http://127.0.0.1:8020/ready
curl -s http://127.0.0.1:8020/mempool/health
```

### 2. 注册 Agent（推荐；用于验证 Agent Registry 链路）

说明：

- Scheduler 默认优先使用 DB 中已注册 Agent（`SCHEDULER_AGENT_REGISTRY_PREFER_DB=true`）
- 若不注册，也可仅依赖 `SCHEDULER_AGENT_ENDPOINTS`（用于快速联调）

注册 Comment Agent 示例：

```bash
curl -s -X POST "http://127.0.0.1:8010/api/internal/scheduler/agents/register" ^
  -H "content-type: application/json" ^
  -H "x-internal-token: local-dev-scheduler-token" ^
  -d "{\"agent_key\":\"comment-agent\",\"name\":\"Comment Agent\",\"base_url\":\"http://127.0.0.1:8020\",\"task_types\":[\"comment.moderate\"],\"health_path\":\"/health\",\"capabilities\":{\"service\":\"comment-agent\"},\"status\":1}"
```

验证已注册（可选）：

```bash
curl -s "http://127.0.0.1:8010/api/internal/scheduler/agents?limit=50" -H "x-internal-token: local-dev-scheduler-token"
```

### 3. 提交任务（E2E）

提交一个 `comment.moderate` 任务：

```bash
curl -s -X POST "http://127.0.0.1:8010/api/internal/scheduler/tasks" ^
  -H "content-type: application/json" ^
  -H "x-internal-token: local-dev-scheduler-token" ^
  -H "x-trace-id: task6-demo-trace" ^
  -H "x-idempotency-key: task6-demo-1" ^
  -d "{\"task_type\":\"comment.moderate\",\"payload\":{\"comment_id\":1,\"content\":\"hello\"},\"max_retries\":2,\"retry_delay_seconds\":1}"
```

预期：

- 返回 JSON 中包含 `id`（任务 ID）
- 短时间内任务状态由 `PENDING` -> `RUNNING` -> `SUCCEEDED`（或失败并按策略重试）

### 4. 查询任务状态 / attempts / events

将 `<TASK_ID>` 替换为上一步返回的任务 ID：

```bash
curl -s "http://127.0.0.1:8010/api/internal/scheduler/tasks/<TASK_ID>" -H "x-internal-token: local-dev-scheduler-token"
```

重点核对字段：

- `status`：最终状态（`SUCCEEDED/FAILED/CANCELED`）
- `attempt_count`：尝试次数
- `attempts[].agent` / `attempts[].http_status` / `attempts[].error`
- `events[]` 是否包含 `SUBMITTED/ATTEMPT_STARTED/ATTEMPT_FINISHED/STATUS_CHANGED`

### 5. 查询任务日志

```bash
curl -s "http://127.0.0.1:8010/api/internal/scheduler/tasks/<TASK_ID>/logs?limit=200" -H "x-internal-token: local-dev-scheduler-token"
```

### 6. 取消任务（覆盖取消链路）

适用于任务仍在 `PENDING/RUNNING` 时验证取消标记。

```bash
curl -s -X POST "http://127.0.0.1:8010/api/internal/scheduler/tasks/<TASK_ID>/cancel" -H "x-internal-token: local-dev-scheduler-token"
curl -s "http://127.0.0.1:8010/api/internal/scheduler/tasks/<TASK_ID>" -H "x-internal-token: local-dev-scheduler-token"
```

### 7. 幂等性（覆盖重复提交）

使用相同 `x-idempotency-key` 重复提交同一 payload，预期返回同一 `id`：

```bash
curl -s -X POST "http://127.0.0.1:8010/api/internal/scheduler/tasks" ^
  -H "content-type: application/json" ^
  -H "x-internal-token: local-dev-scheduler-token" ^
  -H "x-idempotency-key: task6-demo-1" ^
  -d "{\"task_type\":\"comment.moderate\",\"payload\":{\"comment_id\":1,\"content\":\"hello\"}}"
```

使用相同 `x-idempotency-key` 但 payload 不同，预期 `409 idempotency key conflict`。

### 8. 鉴权失败（覆盖安全基线）

省略/错误 token，预期 `401`：

```bash
curl -i -s "http://127.0.0.1:8010/api/internal/scheduler/tasks?limit=1"
curl -i -s "http://127.0.0.1:8010/api/internal/scheduler/tasks?limit=1" -H "x-internal-token: wrong"
```

### Task6 结果记录模板

- 可直接复制 [TASK6_INTEGRATION_REPORT_TEMPLATE.md](file:///D:/Python/Personal%20Blog/scheduler_center/docs/TASK6_INTEGRATION_REPORT_TEMPLATE.md) 填写

## Task7：压测 / 故障演练

### 压测（并发压测脚本）

脚本：`scheduler_center/scripts/load_test.py`

执行前建议：

- `SCHEDULER_MAX_CONCURRENCY` 设置为与压测并发接近或更高（例如 ≥ 100）
- 确保已启动 Scheduler Center + Agent（并完成注册或配置 `SCHEDULER_AGENT_ENDPOINTS`）

示例（使用默认参数：`concurrency=100 total=200`）：

```bash
cd "d:\Python\Personal Blog"
set SCHEDULER_INTERNAL_TOKEN=local-dev-scheduler-token
python scheduler_center\scripts\load_test.py --scheduler-url http://127.0.0.1:8010 --token %SCHEDULER_INTERNAL_TOKEN%
```

示例（提高压力：`200 并发 / 2000 总量`）：

```bash
cd "d:\Python\Personal Blog"
set SCHEDULER_INTERNAL_TOKEN=local-dev-scheduler-token
python scheduler_center\scripts\load_test.py --scheduler-url http://127.0.0.1:8010 --token %SCHEDULER_INTERNAL_TOKEN% --concurrency 200 --total 2000 --task-type comment.moderate --timeout 120
```

输出与退出码约定（便于 CI/验收）：

- 输出包含 `=== load test summary ===`、吞吐窗口、成功/失败/超时、p50/p95/max 等
- 退出码：
  - `0`：并发 ≥ 100 且无超时
  - `2`：并发 < 100（低于脚本的基线要求）
  - `3`：出现超时（`TIMEOUT > 0`）

### 故障演练（容错/降级验证）

脚本：`scheduler_center/scripts/fault_drill.py`

覆盖项（脚本内置）：

- Agent 不可达（注册一个不可连接的 base_url，验证重试后失败）
- 网络超时（启动 Agent Stub，人为延迟响应，验证超时重试后失败）
- Redis 不可用（启动 Comment Agent，配置不可用 Redis URL，验证 mempool 自动降级且 Agent 仍可执行）

执行命令：

```bash
cd "d:\Python\Personal Blog"
set SCHEDULER_INTERNAL_TOKEN=local-dev-scheduler-token
python scheduler_center\scripts\fault_drill.py --scheduler-url http://127.0.0.1:8010 --token %SCHEDULER_INTERNAL_TOKEN% --stub-delay 20
```

预期输出包含（顺序可能略有差异）：

- `[PASS] agent-down: ...`
- `[PASS] network-timeout: ...`
- `[PASS] redis-unavailable: ...`

### Task7 结果记录模板

- 可直接复制 [TASK7_PERF_FAULT_REPORT_TEMPLATE.md](file:///D:/Python/Personal%20Blog/scheduler_center/docs/TASK7_PERF_FAULT_REPORT_TEMPLATE.md) 填写

## 压测与故障演练脚本

- 并发压测：`scheduler_center/scripts/load_test.py`
- 故障演练：`scheduler_center/scripts/fault_drill.py`
