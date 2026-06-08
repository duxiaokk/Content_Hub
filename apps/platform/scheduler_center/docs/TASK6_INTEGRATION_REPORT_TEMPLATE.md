# Task6 联调结果记录模板（Scheduler Center ↔ Agent）

## 1. 基本信息

| 项 | 值 |
|---|---|
| 日期 |  |
| 执行人 |  |
| 环境 | 本地 / 测试 / 预发 / 生产 |
| Scheduler Center 地址 | http://127.0.0.1:8010 |
| Agent 地址 | http://127.0.0.1:8020 |
| Token（脱敏） |  |
| 数据库 | Scheduler：SQLite / 其他；Agent：SQLite / 其他 |
| 代码版本 | （git commit / tag / 包版本 / zip hash） |

## 2. 启动与就绪检查

| 检查项 | 执行命令 | 期望 | 实际结果 | 结论 |
|---|---|---|---|---|
| Scheduler /health | `curl -s http://127.0.0.1:8010/health` | 2xx + `{"status":"ok"}` |  | PASS / FAIL |
| Scheduler /ready | `curl -s http://127.0.0.1:8010/ready` | 2xx + `db_ok=true` |  | PASS / FAIL |
| Agent /health | `curl -s http://127.0.0.1:8020/health` | 2xx + `{"status":"ok"}` |  | PASS / FAIL |
| Agent /ready | `curl -s http://127.0.0.1:8020/ready` | 2xx + `db_ok=true` |  | PASS / FAIL |
| Agent /mempool/health | `curl -s http://127.0.0.1:8020/mempool/health` | 2xx + redis/sqlite 状态 |  | PASS / FAIL |

## 3. Agent Registry（注册链路）

| 步骤 | 执行命令 | 期望 | 实际结果 | 结论 |
|---|---|---|---|---|
| 注册 Agent | `POST /api/internal/scheduler/agents/register` | 2xx + 返回 AgentItem |  | PASS / FAIL |
| 查询 Agent 列表 | `GET /api/internal/scheduler/agents` | 能看到已注册 Agent |  | PASS / FAIL |

## 4. 任务链路（提交 → 分发 → 执行 → 回写）

### 4.1 任务提交记录

| 项 | 值 |
|---|---|
| task_type | comment.moderate |
| payload |  |
| x-trace-id |  |
| x-idempotency-key |  |
| max_retries |  |
| retry_delay_seconds |  |
| submit 返回 task_id |  |

### 4.2 任务状态核对（Task Detail）

| 字段 | 期望 | 实际 |
|---|---|---|
| status | SUCCEEDED（或按预期 FAILED/CANCELED） |  |
| attempt_count | ≥ 1 |  |
| last_agent | 期望 Agent base_url |  |
| last_error | 成功为空；失败包含可定位信息 |  |
| result | 成功时保存 Agent 2xx JSON |  |

### 4.3 attempts/events 抽查

| 项 | 期望 | 实际 |
|---|---|---|
| attempts[].http_status | 2xx（成功场景） |  |
| attempts[].retryable | 失败时符合 4xx/5xx/超时判定 |  |
| events 包含关键事件 | SUBMITTED / ATTEMPT_STARTED / ATTEMPT_FINISHED / STATUS_CHANGED |  |

### 4.4 Scheduler 任务日志

| 检查项 | 期望 | 实际 |
|---|---|---|
| logs 包含 submitted/dispatching/succeeded 等 | 有且 trace_id 对齐 |  |

## 5. 取消链路（可选）

| 步骤 | 执行命令 | 期望 | 实际结果 | 结论 |
|---|---|---|---|---|
| 取消任务 | `POST /api/internal/scheduler/tasks/<TASK_ID>/cancel` | cancel_requested=true；状态按实现演进 |  | PASS / FAIL |
| 再查详情 | `GET /api/internal/scheduler/tasks/<TASK_ID>` | cancel_requested=true；status 最终 CANCELED 或 RUNNING→终态 |  | PASS / FAIL |

## 6. 幂等性与鉴权（覆盖安全基线）

| 场景 | 执行命令 | 期望 | 实际结果 | 结论 |
|---|---|---|---|---|
| 幂等：相同 key 相同 payload | 重复 `POST /tasks` | 返回同一 task_id |  | PASS / FAIL |
| 幂等冲突：相同 key 不同 payload | `POST /tasks` | 409 conflict |  | PASS / FAIL |
| 鉴权：缺失 token | `GET /tasks` | 401 |  | PASS / FAIL |
| 鉴权：错误 token | `GET /tasks` | 401 |  | PASS / FAIL |

## 7. 异常与结论

| 项 | 内容 |
|---|---|
| 异常现象 |  |
| 定位信息（日志/trace_id/截图） |  |
| 结论 | PASS / FAIL |
| 后续动作 |  |

