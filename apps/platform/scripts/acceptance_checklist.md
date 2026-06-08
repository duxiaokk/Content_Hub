# Ado_Jk Platform 验收测试检查清单

> 基于优化计划制定的全平台验收标准，覆盖容器化、数据库迁移、Agent 集群、可观测性、前端和性能六大维度。

---

## 一、容器化 (Containerization)

| # | 类别 | 检查项 | 目标 | 状态 | 备注 |
|---|------|--------|------|------|------|
| 1 | 容器化 | 平台主服务 Dockerfile 可构建 | `docker build -f Dockerfile .` 构建成功 | [ ] | `Dockerfile` 位于项目根目录 |
| 2 | 容器化 | 调度中心 Dockerfile 可构建 | `docker build -f scheduler_center/Dockerfile .` 构建成功 | [ ] | 独立调度中心镜像 |
| 3 | 容器化 | Agent Dockerfile 可构建 | `docker build -f docker/agent.Dockerfile .` 构建成功 | [ ] | P4 Agent 集群通用镜像 |
| 4 | 容器化 | Audit Agent Dockerfile 可构建 | `docker build -f docker/audit-agent.Dockerfile .` 构建成功 | [ ] | 审计 Agent 独立镜像 |
| 5 | 容器化 | docker-compose 一键启动 | `docker compose up -d` 所有服务正常启动 | [ ] | 含 15+ 服务: Postgres, Redis, Jaeger, Prometheus, Loki, Grafana, Platform, Scheduler, Agents |
| 6 | 容器化 | 服务健康检查已配置 | 所有关键容器配置 `healthcheck` | [ ] | Postgres(pg_isready), Redis(redis-cli ping), HTTP 服务(curl) |
| 7 | 容器化 | 数据持久化卷已配置 | 所有有状态服务挂载 named volume | [ ] | postgres-data, redis-data, scheduler-data, jaeger-data, prometheus-data, loki-data, grafana-data |
| 8 | 容器化 | 资源限制已设置 | 每个容器配置 CPU/Memory limits + reservations | [ ] | deploy-small(256M/0.5CPU), deploy-medium(512M/1CPU), deploy-large(1G/2CPU) |
| 9 | 容器化 | 日志驱动已配置 | json-file + max-size=20m + max-file=5 | [ ] | 防止容器日志撑满磁盘 |
| 10 | 容器化 | 独立网桥网络 | `blog-net` bridge 网络隔离 | [ ] | 容器间通过服务名通信 |
| 11 | 容器化 | entrypoint 脚本正常 | `docker/entrypoint.sh`, `docker/agent_entrypoint.sh` 可执行 | [ ] | 数据库等待、迁移执行、服务启动 |
| 12 | 容器化 | 环境变量注入正确 | `.env` 文件变量被 `docker compose` 加载 | [ ] | SECRET_KEY, DATABASE_URL, LLM_API_KEY 等 |

## 二、数据库迁移 (Database Migration)

| # | 类别 | 检查项 | 目标 | 状态 | 备注 |
|---|------|--------|------|------|------|
| 13 | 数据库迁移 | SQLite 到 PostgreSQL 迁移脚本可用 | `python scripts/db_migrate_sqlite_to_pg.py` 执行成功 | [ ] | 处理 blog.db -> PostgreSQL 全量迁移 |
| 14 | 数据库迁移 | Alembic 迁移版本完整 | `alembic upgrade head` 无报错 | [ ] | `migrations/versions/0001_initial.py`, `0002_postgresql_compat.py` |
| 15 | 数据库迁移 | PostgreSQL 连接配置正确 | `DATABASE_URL=postgresql://...` 格式正确 | [ ] | 用户、密码、主机、端口、数据库名 |
| 16 | 数据库迁移 | 迁移后数据完整性校验 | Row count 与原 SQLite 一致 | [ ] | posts, users, comments 表行数对比 |
| 17 | 数据库迁移 | 迁移后外键关系完整 | `posts.user_id` -> `users.id` 关系正确 | [ ] | PostgreSQL FOREIGN KEY 约束 |
| 18 | 数据库迁移 | 迁移后索引已创建 | 常用查询字段索引 (created_at, user_id, post_id) | [ ] | 查询性能不低于 SQLite 水平 |
| 19 | 数据库迁移 | 调度中心数据库配置 | `SCHEDULER_DATABASE_URL` 指向 PostgreSQL | [ ] | 共享 blog_db 或独立数据库 |
| 20 | 数据库迁移 | SQLite 回退方案可用 | 不设置 DATABASE_URL 时回退到 SQLite | [ ] | 开发环境兼容性 |
| 21 | 数据库迁移 | 数据库连接池配置合理 | pool_size + max_overflow 符合预期并发量 | [ ] | `SCHEDULER_DB_POOL_SIZE=10`, `SCHEDULER_DB_MAX_OVERFLOW=20` |
| 22 | 数据库迁移 | busy_timeout 已配置（SQLite 模式） | `SCHEDULER_SQLITE_BUSY_TIMEOUT_SECONDS=30` | [ ] | 减少 "database is locked" 错误 |

## 三、Agent 集群 (Agent)

| # | 类别 | 检查项 | 目标 | 状态 | 备注 |
|---|------|--------|------|------|------|
| 23 | Agent | Agent 注册链路正常 | Agent 启动后自动注册到调度中心 | [ ] | `POST /api/internal/scheduler/agents/register` 返回 2xx |
| 24 | Agent | Agent 心跳机制工作 | 调度中心定期检查 Agent 健康状态 | [ ] | `SCHEDULER_AGENT_HEARTBEAT_TTL_SECONDS=120` |
| 25 | Agent | 任务提交 -> 分发 -> 执行 -> 回写全链路 | 提交 `comment.moderate` 任务后完整执行 | [ ] | status: PENDING -> RUNNING -> SUCCEEDED |
| 26 | Agent | 任务重试机制 | 失败任务在 `max_retries` 次数内自动重试 | [ ] | 默认 max_retries=2, retry_delay=3s |
| 27 | Agent | 任务取消机制 | `POST /tasks/{id}/cancel` 终止运行中任务 | [ ] | status 最终为 CANCELED |
| 28 | Agent | 任务幂等性 | 相同 `x-idempotency-key` + payload 返回同一 task_id | [ ] | 防止重复提交 |
| 29 | Agent | 任务幂等冲突检测 | 相同 key + 不同 payload 返回 409 | [ ] | 提交方感知冲突 |
| 30 | Agent | 内部鉴权 | 缺失/错误 `x-internal-token` 返回 401 | [ ] | 调度中心 API 安全 |
| 31 | Agent | Agent 集群注册完整性 | 所有 P4 Agent 均成功注册 | [ ] | planner, data-processor, tool-calling, content-generator, aggregator, audit |
| 32 | Agent | Agent 健康检查端点 | 每个 Agent 的 `/health` 返回 200 | [ ] | `{"status":"ok"}` |
| 33 | Agent | 编排层 Planner -> Aggregator 链路 | 提交编排运行后完成规划 + 聚合 | [ ] | Run status: SUCCEEDED |
| 34 | Agent | Shared Memory Pool 读写 | Agent 间通过 Redis/SQLite Memory Pool 共享数据 | [ ] | RunNaming, TaskNaming 键空间隔离 |
| 35 | Agent | Agent Simulator 可用 | `python scripts/agent_simulator.py` 模拟多 Agent 行为 | [ ] | 用于开发/测试环境 |
| 36 | Agent | 编排 Checkpoint 恢复 | 中断的编排运行可从 checkpoint 恢复 | [ ] | `resume_from_checkpoint()` 功能验证 |

## 四、可观测性 (Observability)

| # | 类别 | 检查项 | 目标 | 状态 | 备注 |
|---|------|--------|------|------|------|
| 37 | 可观测性 | OpenTelemetry Tracing 已启用 | `OTEL_ENABLED=true` 生效 | [ ] | 自动埋点 FastAPI 路由 |
| 38 | 可观测性 | Jaeger UI 可访问 | `http://localhost:16686` 可打开 | [ ] | 搜索服务 `platform`, `scheduler-api` |
| 39 | 可观测性 | Trace 数据已上报 | Jaeger 服务列表包含平台服务 | [ ] | 每次 HTTP 请求产生 Span |
| 40 | 可观测性 | Trace 跨服务传播 | `x-trace-id` 在 Platform -> Scheduler -> Agent 链路上传递 | [ ] | 同一 Trace 包含所有子 Span |
| 41 | 可观测性 | Prometheus Metrics 已启用 | `METRICS_ENABLED=true` 生效，`/metrics` 端点返回数据 | [ ] | HTTP 请求计数、延迟直方图等 |
| 42 | 可观测性 | Prometheus UI 可访问 | `http://localhost:9090` 可打开 | [ ] | targets 列表包含 platform 和 scheduler-api |
| 43 | 可观测性 | Prometheus 告警规则已配置 | `configs/alerting_rules.yml` 加载 | [ ] | 高错误率、高延迟告警 |
| 44 | 可观测性 | Loki 日志聚合 | `http://localhost:3100/ready` 返回 200 | [ ] | Promtail 采集容器日志 |
| 45 | 可观测性 | Grafana UI 可访问 | `http://localhost:3000` 可登录 | [ ] | admin/admin 或自定义 |
| 46 | 可观测性 | Grafana 数据源已配置 | Prometheus + Loki 数据源自动配置 | [ ] | `configs/grafana-datasources.yml` 预置 |
| 47 | 可观测性 | Grafana 仪表板已预置 | 预置 Dashboard JSON 加载 | [ ] | Platform Overview, Scheduler Metrics 等 |
| 48 | 可观测性 | 结构化日志格式 | `LOG_FORMAT=json` 输出 JSON 格式日志 | [ ] | 便于 Loki 索引和查询 |
| 49 | 可观测性 | 日志包含 trace_id | 每条日志自动注入 trace_id | [ ] | 关联 Trace 和 Log |
| 50 | 可观测性 | 烟雾测试脚本通过 | `python scripts/smoke_test.py` 验证所有组件可达 | [ ] | 基础设施 + 应用 + 可观测性全量检测 |
| 51 | 可观测性 | 可观测性验证脚本通过 | `python scripts/verify_observability.py` 无失败项 | [ ] | 专项验证 Tracing/Metrics/Logging |

## 五、前端 (Frontend)

| # | 类别 | 检查项 | 目标 | 状态 | 备注 |
|---|------|--------|------|------|------|
| 52 | 前端 | React 前端可构建 | `cd frontend && npm run build` 成功 | [ ] | Vite 构建无报错 |
| 53 | 前端 | 前端开发服务器可启动 | `npm run dev` 正常启动 | [ ] | 默认 http://localhost:5173 |
| 54 | 前端 | 前端 API 代理配置正确 | `/api` 请求代理到 Platform 后端 | [ ] | vite.config.ts 中 proxy 配置 |
| 55 | 前端 | 文章列表页加载 | GET /api/v1/posts 返回分页数据并渲染 | [ ] | 文章卡片、分页组件 |
| 56 | 前端 | 文章详情页加载 | 单篇文章 GET /api/v1/posts/{id} 正常渲染 | [ ] | Markdown 内容渲染 |
| 57 | 前端 | 登录/注册功能 | POST /api/v1/auth/login 成功后跳转 | [ ] | Token 存储、Cookie 管理 |
| 58 | 前端 | 认证状态持久化 | 刷新页面后保持登录状态 | [ ] | Cookie-based JWT |
| 59 | 前端 | 文章创建/编辑（管理员） | 管理员登录后可创建和编辑文章 | [ ] | Markdown 编辑器 |
| 60 | 前端 | 评论功能 | 登录用户可发表评论 | [ ] | 评论列表 + 提交表单 |
| 61 | 前端 | 点赞功能 | 可对文章点赞/取消点赞 | [ ] | 实时更新 like_count |
| 62 | 前端 | AI 辅助写作 | AI 大纲生成/润色/草稿接口可调用 | [ ] | 前端连接到 /api/v1/ai/* |
| 63 | 前端 | 响应式布局 | 移动端/平板/桌面端自适应 | [ ] | Ant Design 响应式组件 |
| 64 | 前端 | 错误提示 | API 错误在前端显示友好提示 | [ ] | 统一错误码映射用户提示 |
| 65 | 前端 | 加载状态 | 数据加载中显示 Skeleton/Spin | [ ] | 避免白屏或空白 |

## 六、性能 (Performance)

| # | 类别 | 检查项 | 目标 | 状态 | 备注 |
|---|------|--------|------|------|------|
| 66 | 性能 | API 压力测试脚本可用 | `python scripts/stress_test_api.py` 正常运行 | [ ] | 零外部依赖，stdlib 实现 |
| 67 | 性能 | 编排压力测试脚本可用 | `python scripts/stress_test_orchestration.py` 正常运行 | [ ] | 需要 httpx 依赖 |
| 68 | 性能 | 调度中心负载测试脚本可用 | `python scheduler_center/scripts/load_test.py` 正常运行 | [ ] | Task 提交 + 等待终态 |
| 69 | 性能 | 调度中心故障演练脚本可用 | `python scheduler_center/scripts/fault_drill.py` 正常运行 | [ ] | 断连/恢复场景 |
| 70 | 性能 | REST API GET 请求吞吐达标 | GET /api/v1/posts：p95 < 100ms @ 100 并发 | [ ] | 数据库查询 + 缓存 |
| 71 | 性能 | REST API POST 请求延迟达标 | POST /api/v1/auth/login：p95 < 500ms @ 50 并发 | [ ] | 含密码哈希验证 |
| 72 | 性能 | 健康检查端点延迟达标 | GET /health：p95 < 50ms @ 200 并发 | [ ] | 轻量端点，含 DB 检查 |
| 73 | 性能 | 调度中心提交 P95 达标 | Task submit P95 < 500ms @ 100 并发 (fast_submit 模式) | [ ] | Redis 快速投递路径 |
| 74 | 性能 | 编排运行端到端成功率达标 | 20 并发编排运行成功率 > 90% | [ ] | 规划 + 任务分发 + 聚合全链路 |
| 75 | 性能 | 数据库连接池不耗尽 | 30 并发持续读写无 "pool exhausted" 错误 | [ ] | 连接泄漏检测 |
| 76 | 性能 | 限流机制触发正确 | 超过阈值请求返回 429 状态码 | [ ] | `RATE_LIMIT_ENABLED=true` 时生效 |
| 77 | 性能 | 高并发下无数据损坏 | 并发创建文章后均可通过 GET 获取 | [ ] | DB 事务完整性 |
| 78 | 性能 | Redis Fast Submit 全链路可用 | Submit -> Redis Queue -> Ingest -> Dispatch -> Execute | [ ] | `SCHEDULER_FAST_SUBMIT_ENABLED=true` |
| 79 | 性能 | Ingest Worker 无消息积压 | fast_submit 队列消费速率 > 生产速率 | [ ] | `submit_queue_llen` 不持续增长 |
| 80 | 性能 | 无内存泄漏 | 压力测试后进程内存使用回归基线 | [ ] | 对比 before/after 快照 |

---

## 汇总统计

| 维度 | 通过 | 失败 | 跳过 | 总计 |
|------|------|------|------|------|
| 容器化 (Containerization) | | | | 12 |
| 数据库迁移 (Database Migration) | | | | 10 |
| Agent 集群 (Agent) | | | | 14 |
| 可观测性 (Observability) | | | | 15 |
| 前端 (Frontend) | | | | 14 |
| 性能 (Performance) | | | | 15 |
| **合计** | | | | **80** |

---

## 验收结论

- **验收日期**: _______________
- **验收人**: _______________
- **总体结论**: [ ] 通过 / [ ] 有条件通过 / [ ] 不通过
- **备注**: _______________

---

> 本检查清单依据 Ado_Jk Platform 优化计划制定，涵盖 Task1-Task7 的所有交付物验收标准。
> 最后更新: 2026-06-07
