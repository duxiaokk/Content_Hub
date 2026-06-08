# Task7 压测 / 故障演练结果记录模板

## 1. 基本信息

| 项 | 值 |
|---|---|
| 日期 |  |
| 执行人 |  |
| 环境 | 本地 / 测试 / 预发 / 生产 |
| Scheduler Center 地址 | http://127.0.0.1:8010 |
| Agent 地址 | http://127.0.0.1:8020 |
| Token（脱敏） |  |
| 机器配置 | CPU / 内存 / 磁盘 / 网络 |
| Python 版本 |  |
| 代码版本 | （git commit / tag / 包版本 / zip hash） |

## 2. 压测（scheduler_center/scripts/load_test.py）

### 2.1 测试参数

| 参数 | 值 |
|---|---|
| scheduler-url |  |
| task-type | comment.moderate |
| concurrency |  |
| total |  |
| timeout (E2E) |  |
| poll-interval |  |
| SCHEDULER_MAX_CONCURRENCY |  |
| SCHEDULER_HTTP_TIMEOUT_SECONDS |  |

### 2.2 执行命令与原始输出

执行命令：

```bash
python scheduler_center\scripts\load_test.py --scheduler-url http://127.0.0.1:8010 --token <TOKEN> --concurrency <N> --total <M> --task-type comment.moderate --timeout <SECONDS>
```

原始输出（粘贴脚本输出全文）：

```text
```

### 2.3 指标摘录（从脚本输出填写）

| 指标 | 值 |
|---|---|
| submit_window_s |  |
| succeeded |  |
| failed |  |
| timeout |  |
| submit p50/p95/max (ms) |  |
| e2e p50/p95/max (ms) |  |
| e2e mean/stdev (ms) |  |
| 退出码 |  |
| 结论 | PASS / FAIL |

### 2.4 观测与问题记录

| 项 | 内容 |
|---|---|
| CPU/内存/IO 峰值 |  |
| 错误聚类（last_error/HTTP 状态码） |  |
| 可能瓶颈 |  |
| 结论与建议 |  |

## 3. 故障演练（scheduler_center/scripts/fault_drill.py）

### 3.1 执行命令与原始输出

执行命令：

```bash
python scheduler_center\scripts\fault_drill.py --scheduler-url http://127.0.0.1:8010 --token <TOKEN> --stub-delay 2
```

原始输出（粘贴脚本输出全文）：

```text
```

### 3.2 用例结果

| 用例 | 期望 | 实际 | 结论 |
|---|---|---|---|
| Agent 不可达（agent-down） | 任务失败且 attempt_count ≥ 2 |  | PASS / FAIL |
| 网络超时（network-timeout） | 任务失败且 attempt_count ≥ 2 |  | PASS / FAIL |
| Redis 不可用（redis-unavailable） | mempool redis_ok=false 且 Agent 仍可执行 |  | PASS / FAIL |

### 3.3 关键定位信息（可选）

| 项 | 内容 |
|---|---|
| fault_drill 产生的 task_id 列表 |  |
| 对应 task detail 的 last_error |  |
| 关键日志/trace_id |  |

## 4. 总结

| 项 | 内容 |
|---|---|
| 结论 | PASS / FAIL |
| 遗留问题 |  |
| 风险点 |  |
| 后续动作 |  |

