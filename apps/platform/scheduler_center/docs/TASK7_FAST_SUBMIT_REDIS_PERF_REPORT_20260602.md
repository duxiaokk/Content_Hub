# Task7 压测报告（Redis fast_submit 全链路）

## 1. 基本信息

| 项 | 值 |
|---|---|
| 日期 | 2026-06-02 |
| 环境 | Windows（本地联调） |
| Scheduler Center 地址 | http://127.0.0.1:9010 |
| Comment_Agent 地址 | http://127.0.0.1:8020 |
| Token（脱敏） | local-dev-*** |
| Redis | 5.0.14.1（redis://127.0.0.1:6379/0） |
| 采样与原始数据目录 | `scheduler_center/perf_runs/20260602_205310/` |

启动拓扑：
- Scheduler API：uvicorn 4 workers，`SCHEDULER_DISABLE_DISPATCHER=true`
- Ingest Worker：`python -m scheduler_center.ingest_worker`
- Dispatcher Worker：`python -m scheduler_center.worker`（`SCHEDULER_MAX_CONCURRENCY=20`）
- Comment_Agent：uvicorn 单进程（用于 `comment.moderate` 执行）

## 2. 关键配置（本次压测）

| 配置项 | 值 |
|---|---|
| SCHEDULER_FAST_SUBMIT_ENABLED | true |
| SCHEDULER_REDIS_URL | redis://127.0.0.1:6379/0 |
| SCHEDULER_REDIS_PREFIX | perf_20260602_205310 |
| SCHEDULER_DB_PATH | `scheduler_center/perf_runs/20260602_205310/scheduler.db` |
| SCHEDULER_SQLITE_BUSY_TIMEOUT_SECONDS | 30 |
| SCHEDULER_DB_POOL_SIZE / MAX_OVERFLOW | 50 / 100 |
| SCHEDULER_MAX_CONCURRENCY（dispatcher） | 20 |
| task-type | comment.moderate |

## 3. 压测结果（scheduler_center/scripts/load_test.py）

### 3.1 测试矩阵（摘要）

| Case | total / concurrency | submit_window_s | submit p50/p95/max (ms) | succeeded / failed / timeout | e2e p50/p95/max (ms) |
|---|---:|---:|---:|---:|---:|
| A | 200 / 100 | 1.106 | 235.29 / 800.48 / 928.64 | 200 / 0 / 0 | 9518.71 / 15412.29 / 15783.28 |
| B | 500 / 200 | 5.799 | 766.35 / 5327.41 / 5640.82 | 499 / 1 / 0 | 17641.37 / 34041.70 / 36865.90 |

吞吐（submit 窗口内）：  
- Case A：≈ 200 / 1.106 = 180.8 req/s  
- Case B：≈ 500 / 5.799 = 86.2 req/s

### 3.2 原始输出（可追溯）

- Case A：`perf_runs/20260602_205310/load_test_c100_t200.txt`
- Case B：`perf_runs/20260602_205310/load_test_c200_t500.txt`

### 3.3 资源与 Redis 指标（压测前/后）

Redis（INFO 摘要）：
- 压测前 `used_memory_human=1.00M`，`total_commands_processed=5878`，`connected_clients=4`
- 压测后 `used_memory_human=8.00M`，`total_commands_processed=32299`，`db0.keys=10602`（均带 expires），`pref_task_keys=3699`，`pref_idem_keys=3699`，`pref_submit_queue_llen=0`

原始采样文件：
- Redis INFO：`perf_runs/20260602_205310/redis_info_before.json`、`perf_runs/20260602_205310/redis_info_after.json`
- 进程快照：`perf_runs/20260602_205310/process_info_before.txt`、`perf_runs/20260602_205310/process_info_after.txt`

## 4. 观测、瓶颈与结论

### 4.1 观测

- 在 100 并发下，submit p95≈800ms（未达 submit P95≤500ms 目标），且 p95 已接近 1s。
- 在 200 并发下，submit p95≈5.3s，吞吐下降到 ≈86 req/s；说明提交链路在更高并发下出现明显排队/拥塞。
- e2e p95 达到 34s 量级，与 dispatcher 并发上限（20）+ Agent 处理能力叠加后形成 backlog 的现象一致。

### 4.2 错误率

- Case B 存在 1 条 failed（load_test 统计口径：`FAILED` 或 `SUBMIT_FAILED`）；SQLite 中未检索到非 `SUCCEEDED` 任务（说明更可能是 submit 侧请求失败/未落库）。

### 4.3 可能瓶颈（需要进一步拆解验证）

- API 提交路径为同步 handler（FastAPI threadpool 承载），在高并发时可能受线程池排队、上下文切换、GIL 争用影响。
- `redis_submit_queue.enqueue()` 为多次 Redis 往返（写 task、写 idem、LPUSH），在高并发下 RTT 放大明显，建议用 pipeline/transaction 合并。
- e2e 端 backlog：dispatcher 并发上限 + Agent 处理速率限制，导致任务堆积，进而放大轮询查询压力与整体时延。

### 4.4 结论

| 项 | 结论 |
|---|---|
| submit P95≤500ms | FAIL（100 并发 p95≈800ms；200 并发 p95≈5.3s） |
| 全链路可用性（提交→Redis→落库→调度→执行） | PASS（Case A/B 均完成执行；Case B 有 1 条 submit 失败） |

### 4.5 下一步建议（按优先级）

- 提交路径：将 Redis 写入改为 pipeline（减少往返），并评估将 submit handler 改为 async + async redis client（避免 threadpool 排队）。
- Ingest：支持批量出队/批量插入（减少 SQLite commit 次数），并统计 ingest 吞吐/耗时分布。
- 端到端：提升 dispatcher 并发与 Agent 水平扩容（或对 `comment.moderate` 引入更轻量的 stub 任务用于纯调度压测），降低轮询压力。

