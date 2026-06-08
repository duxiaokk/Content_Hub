# Task7 持久化方案评估报告（Redis/SQLite → PostgreSQL/MySQL）

## 1. 背景与目标

当前调度中心在开启 `SCHEDULER_FAST_SUBMIT_ENABLED=true` 后，提交链路采用 Redis 快速投递（写 Redis KV + 入 Redis 队列），由 `ingest_worker` 异步落库，再由 dispatcher 执行任务。目标是提升 `/tasks` 提交吞吐并降低 submit P95。

本报告基于本次 Redis fast_submit 全链路压测数据与现有实现，对任务元数据持久化方案进行系统性评估，并论证是否需要升级到 PostgreSQL/MySQL 等关系型数据库。

压测报告与数据目录：
- 报告：`scheduler_center/docs/TASK7_FAST_SUBMIT_REDIS_PERF_REPORT_20260602.md`
- 原始数据：`scheduler_center/perf_runs/20260602_205310/`

## 2. 当前方案概述（Redis + SQLite）

### 2.1 数据职责划分

- Redis
  - submit 阶段的任务临时状态缓存：`{prefix}:task:{task_id}`（带 TTL）
  - 幂等映射：`{prefix}:idem:{idempotency_key}`（带 TTL）
  - submit 队列：`{prefix}:submit_queue`（list）
- SQLite（SQLAlchemy）
  - SchedulerTask / Attempt / Event / Log / Agent 注册等全量元数据持久化
  - dispatcher 查询 pending 任务、写 attempt/event/log、更新状态

### 2.2 压测表现（与持久化相关的信号）

在 fast_submit 模式下，submit 路径不再同步写 SQLite，但在 100/200 并发下仍出现明显 submit p95 上升：
- 100 并发：submit p95≈800ms（未达 500ms 目标）
- 200 并发：submit p95≈5.3s（出现显著排队/拥塞）

结论：仅“把 SQLite 写移出 submit 同步路径”不足以保障更高并发下的 submit P95；需要进一步减少 Redis 往返、降低 API 线程池排队、并提升 ingest/dispatcher 的整体吞吐以避免系统反压。

## 3. 现有 Redis/SQLite 的局限性

### 3.1 Redis 作为“提交队列 + 临时元数据”的局限

- 可靠性（数据丢失窗口）
  - 本次环境 Redis `aof_enabled=0`（见 `redis_info_before/after.json`），如 Redis 进程重启/崩溃，未 ingest 的任务可能直接丢失。
  - list 队列缺少消费确认/重放语义，难以做到可观测的 at-least-once（除非引入 stream/group 或额外的 ack 机制）。
- 容量与淘汰风险
  - Redis 内存容量是硬上限；任务缓存（task/idem）随压测增长明显：`used_memory_human 1.00M → 8.00M`，`db0.keys 10602`。
  - 若未来开启 maxmemory + eviction，可能导致“未落库任务”被淘汰，造成状态不可追溯。
- 查询与治理能力弱
  - 复杂过滤/分页/统计需额外建索引结构或回落到 DB；对长期审计（events/attempts）不适合放 Redis。

### 3.2 SQLite 作为任务元数据持久化的局限

- 并发写天然瓶颈
  - SQLite 单写者模型决定了在高并发写（attempt/event/log 持续写入）时容易形成写锁竞争。
  - 即使开启 WAL 与 busy_timeout，吞吐上限仍受限于单机单文件写入能力。
- 扩展性限制
  - 多实例（多 API + 多 worker）扩容难度高：共享同一 SQLite 文件需要共享盘/网络盘，可靠性与锁语义风险显著。
- 运维与数据治理能力有限
  - 备份、增量恢复、报表统计、索引/分区能力较弱；数据规模增长后 VACUUM/迁移成本变高。

## 4. 升级到 PostgreSQL / MySQL 的收益与可行性

### 4.1 预期收益

- 并发写能力与可扩展性
  - 行级锁 + 多连接并发写，更适合大量 attempt/event 写入与状态更新。
  - 支持多实例水平扩展（多个 API 与多个 worker 同时工作），更接近生产拓扑。
- 查询与观测能力增强
  - 更强的索引、统计、SQL 分析与可视化生态（慢查询、pg_stat_statements 等），利于定位瓶颈与做 SLA 看板。
- 高可用与可恢复性
  - 主从复制、自动备份、PITR（Postgres）等能力提升数据可靠性与可追溯性。

### 4.2 技术可行性（基于当前代码结构）

- 当前已使用 SQLAlchemy，迁移到 PostgreSQL/MySQL 的改造主要集中在：
  - 配置：提供 `SCHEDULER_DATABASE_URL` 指向 Postgres/MySQL
  - 表结构：保持 models 不变或做少量字段类型调整（如 JSON/时间字段优化）
  - 迁移工具：引入 Alembic（若代码库目前未使用，需要新增依赖与迁移脚本）
- Redis fast_submit 仍可保留（作为削峰/队列/幂等缓存），但建议增强可靠性：
  - Redis Streams + consumer group（替代 list）
  - 或启用 AOF，并增加 ingest 的消费确认与重试机制

### 4.3 成本与风险

- 运维成本
  - 需要部署与维护数据库（账号、网络、备份、监控、容量规划）。
- 迁移成本
  - 引入 schema migration、环境初始化、CI 测试数据库等配套工作。
- 性能收益边界
  - 本次压测中 submit 高并发 p95 主要来自 API/Redis 写入拥塞，而不是 SQLite 同步写（fast_submit 已移除同步落库）。
  - 因此：升级 DB 能显著改善 ingest/dispatcher 写入与可扩展性，但对 submit P95 的直接改善有限；submit 仍需做 Redis pipeline 与 handler 异步化等优化。

## 5. 结论与推荐路线

### 5.1 是否需要升级到 PostgreSQL/MySQL

建议：需要（中长期）。
- 若目标是“稳定承载更高并发 + 多实例扩容 + 强可观测 + 强可追溯”，SQLite 将成为持续瓶颈与扩容阻碍。
- 关系型数据库可显著提升元数据写入吞吐与并发扩展能力，是长期可落地的演进方向。

### 5.2 推荐的落地步骤（可执行）

第一阶段（不换 DB，优先把 submit P95 拉下来）：
- `redis_submit_queue.enqueue()` 改为 pipeline/transaction 合并写（减少往返）。
- submit handler 评估改为 async（降低 threadpool 排队），并对 Redis/JSON 序列化做热点优化。
- ingest/dispatcher 增加关键指标埋点：出队速率、单条/批量落库耗时、dispatcher 扫描耗时与并发队列长度。

第二阶段（引入 PostgreSQL，解决扩展与元数据写入瓶颈）：
- 增加 Postgres 连接配置与迁移脚本（Alembic）。
- 支持 ingest 批量写入（COPY 或批量 insert），减少事务开销。
- 支持多 dispatcher worker 分片/竞争消费（基于 DB 锁或任务分区）。

第三阶段（增强 Redis 队列可靠性）：
- 将 list 队列升级为 Streams + consumer group（支持 ack、pending 重投）。
- 或对 Redis 开启 AOF，并增加 ingest 端“写入确认/幂等落库”的可观测与补偿机制。

## 6. 附录（数据可追溯清单）

| 数据项 | 路径 |
|---|---|
| Case A 原始输出 | `scheduler_center/perf_runs/20260602_205310/load_test_c100_t200.txt` |
| Case B 原始输出 | `scheduler_center/perf_runs/20260602_205310/load_test_c200_t500.txt` |
| Redis INFO（before/after） | `scheduler_center/perf_runs/20260602_205310/redis_info_before.json`、`redis_info_after.json` |
| 进程快照（before/after） | `scheduler_center/perf_runs/20260602_205310/process_info_before.txt`、`process_info_after.txt` |

