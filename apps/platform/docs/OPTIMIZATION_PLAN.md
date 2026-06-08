# Ado_Jk Multi-Agent Orchestration Platform — 全栈优化方案

> 版本: v2.0  
> 日期: 2026-06-07  
> 状态: 执行中

---

## 目录

1. [现状评估](#1-现状评估)
2. [容器化完善](#2-容器化完善)
3. [数据库迁移与调优](#3-数据库迁移与调优)
4. [多 Agent 扩展与闭环](#4-多-agent-扩展与闭环)
5. [可观测体系端到端](#5-可观测体系端到端)
6. [前端架构升级](#6-前端架构升级)
7. [验收指标与压测](#7-验收指标与压测)
8. [执行路线图](#8-执行路线图)

---

## 1. 现状评估

### 1.1 已完成（基础扎实）

| 模块 | 当前状态 | 评分 |
|------|----------|------|
| 平台主服务 (FastAPI) | 完整路由、JWT 认证、中间件、API v1 | ⭐⭐⭐⭐ |
| 数据库层 | SQLite/PostgreSQL 双模式、Alembic 迁移 | ⭐⭐⭐⭐ |
| Agent 基础框架 | BaseAgent 生命周期、注册、心跳、异常上报 | ⭐⭐⭐⭐⭐ |
| 5 个 P4 Agent | Planner, DataProcessor, ToolCalling, ContentGenerator, Aggregator | ⭐⭐⭐ |
| 调度中心 | API、Dispatcher、重试、事件日志 | ⭐⭐⭐⭐ |
| 编排引擎 | DAG、Planner→Aggregator 流水线、checkpoint | ⭐⭐⭐⭐ |
| Docker Compose | 14 容器、持久卷、健康检查 | ⭐⭐⭐⭐ |
| 可观测性代码 | OTel 追踪、Prometheus 指标、结构化日志 | ⭐⭐⭐⭐ |
| React 前端 | Vite + TypeScript + Ant Design 脚手架 | ⭐⭐ |

### 1.2 待补强（本次优化重点）

| 缺口 | 影响 | 优先级 |
|------|------|--------|
| docker-compose 缺少完整启动验证 | 一键编排可能静默失败 | 🔴 P0 |
| SQLite→PG 迁移无回滚/无压测验证 | 生产迁移风险 | 🔴 P0 |
| Agent 功能偏薄（mock/规则降级为主） | 真实场景覆盖不足 | 🟡 P1 |
| Planner 闭环未端到端验证 | 编排链路不可靠 | 🟡 P1 |
| 前端仍以 Jinja2 模板为主 | SPA 未完整体验 | 🟡 P1 |
| 可观测体系未端到端联调 | 生产监控盲区 | 🟡 P1 |
| 无系统级压测与验收 | 无法量化性能 | 🟡 P1 |
| Agent 间负载均衡欠缺 | 扩展性瓶颈 | 🟢 P2 |

---

## 2. 容器化完善

### 2.1 当前问题

docker-compose.yml 定义了 14 个服务，但存在以下完善点：

1. **启动顺序不完整**: Agent 依赖 scheduler-api healthy，但 scheduler-api 内 Alembic 迁移可能失败无感知
2. **缺少一键管理脚本**: 无 `start.sh` / `stop.sh` / `status.sh`
3. **Agent 扩展性不足**: 无 `deploy.replicas` 支持（单 Agent 瓶颈）
4. **缺少 .env 生产模板**: 敏感信息管理不完善
5. **网络隔离不充分**: 所有服务在同一网络

### 2.2 优化方案

#### 2.2.1 增加启动管理脚本 (`scripts/docker-manage.sh`)

```bash
# 功能: start | stop | restart | status | logs | clean
# 包含: 迁移前检查、健康等齐、失败回滚
```

#### 2.2.2 完善 .env.production 模板

```env
# 生产环境模板，与 .env.example 对应
POSTGRES_PASSWORD=<generate-strong>
SECRET_KEY=<generate-strong>
SCHEDULER_INTERNAL_TOKEN=<generate-strong>
INTERNAL_AGENT_TOKEN=<generate-strong>
LLM_API_KEY=sk-***
GRAFANA_PASSWORD=<generate-strong>
```

#### 2.2.3 增加 Agent 副本扩展支持

在 docker-compose.yml 中增加可选的多副本 Agent：

```yaml
# 示例: 3 个 data-processor-agent 实例
data-processor-agent:
  deploy:
    replicas: 3  # Docker Swarm 模式
```

#### 2.2.4 增加启动前验证脚本

```bash
# 检查: Docker 版本、端口占用、磁盘空间、.env 配置
./scripts/preflight-check.sh
```

### 2.3 交付物

- [ ] `scripts/docker-manage.ps1` — 一键管理 PowerShell 脚本
- [ ] `scripts/preflight-check.ps1` — 启动前验证
- [ ] `.env.production` — 生产环境模板
- [ ] 完善 `docker-compose.yml` — depends_on 链 + 重启策略

---

## 3. 数据库迁移与调优

### 3.1 当前问题

1. **迁移脚本无回滚**: `db_migrate_sqlite_to_pg.py` 只做正向迁移
2. **连接池配置单一**: 未区分读写分离/不同服务的连接池需求
3. **无压测验证**: 未验证 PG 在大并发下的表现
4. **Alembic 迁移链待完善**: 6 个迁移版本，需验证新表结构完整性

### 3.2 优化方案

#### 3.2.1 完善迁移脚本

```python
# db_migrate_sqlite_to_pg.py 增强:
# 1. --dry-run 模式: 预检查不写入
# 2. --rollback 模式: 从 PG 回滚到 SQLite (反向迁移)
# 3. --verify-only 模式: 仅校验数据一致性
# 4. 增量迁移: 只迁差异数据
# 5. 迁移进度条 + 预估时间
```

#### 3.2.2 连接池分级调优

| 服务 | pool_size | max_overflow | pool_timeout | 理由 |
|------|-----------|-------------|-------------|------|
| Platform (主服务) | 20 | 40 | 30s | 高并发 Web 请求 |
| Scheduler API | 15 | 30 | 30s | 中并发 API |
| Scheduler Dispatcher | 5 | 10 | 60s | 低并发轮询 |
| Agent (每个) | 5 | 10 | 30s | 低并发单任务 |

#### 3.2.3 压测验收

```bash
# 使用 pgbench 或 locust 进行数据库压测
# 目标: 1000 TPS 读取, 200 TPS 写入, p99 < 50ms
```

#### 3.2.4 新增监控指标

```sql
-- 连接池监控视图
CREATE VIEW v_pool_stats AS
SELECT pid, state, query_start, state_change
FROM pg_stat_activity WHERE datname = 'blog_db';
```

### 3.3 交付物

- [ ] `scripts/db_migrate_v2.py` — 增强版迁移（含 rollback/dry-run/incremental）
- [ ] `scripts/db_benchmark.py` — 数据库压测脚本
- [ ] `scripts/db_pool_tuner.py` — 连接池自动调优建议
- [ ] `database.py` — 分级连接池配置
- [ ] `scheduler_center/database.py` — 分级连接池配置

---

## 4. 多 Agent 扩展与闭环

### 4.1 当前问题

| Agent | 当前能力 | 缺失 |
|-------|----------|------|
| Planner | LLM + 规则降级，基础拆解 | 缺少复杂场景（嵌套拆解、条件分支） |
| DataProcessor | extract/transform/clean/enrich/validate | 缺少大数据分片、流式处理 |
| ToolCalling | web_search(模拟)/translate/http_get/text_stats | web_search 是 mock，缺少更多工具 |
| ContentGenerator | blog_post/outline/summary/social_media/email | 缺少多语言、SEO 优化、A/B 变体 |
| Aggregator | merge/summarize/compose | 缺少冲突解决、置信度评分 |

### 4.2 优化方案

#### 4.2.1 Planner Agent 增强

```python
# 新增能力:
# 1. 条件分支: if task_X.succeeded → path_A else → path_B
# 2. 嵌套拆解: 子任务可递归拆分为更细粒度的子 DAG
# 3. 成本预估: 每个 task 预估 token/time 成本
# 4. 自动回退: 某个 Agent 不可用时自动替换
```

#### 4.2.2 DataProcessor Agent 增强

```python
# 新增能力:
# 1. 分片处理: 大数据集自动分片 (chunk_size 可配)
# 2. 流式处理: 支持 generator 模式
# 3. schema 校验: JSON Schema 严格校验
# 4. 格式转换: CSV/JSON/YAML/XML 互转
```

#### 4.2.3 ToolCalling Agent 增强

```python
# 新增能力:
# 1. web_search → 接入真实搜索引擎 API (SerpAPI/Bing)
# 2. file_io: 读写文件系统
# 3. code_exec: 安全沙箱执行 Python/Shell
# 4. api_call: 通用 REST API 调用（带重试/限流）
# 5. database_query: 只读 SQL 查询
```

#### 4.2.4 ContentGenerator Agent 增强

```python
# 新增能力:
# 1. 多语言支持: 中/英/日/韩
# 2. SEO 优化: meta description、关键词密度
# 3. A/B 变体: 同一主题生成多个版本
# 4. 图片提示词: 生成配图的 DALL-E/Midjourney prompt
```

#### 4.2.5 Aggregator Agent 增强

```python
# 新增能力:
# 1. 置信度评分: 每个子结果附 confidence score
# 2. 冲突解决: 多 Agent 结果冲突时投票/加权
# 3. 增量聚合: 支持 streaming append
# 4. 格式化输出: Markdown/HTML/JSON 多种输出格式
```

#### 4.2.6 Planner 闭环验证

```python
# orchestration_engine.py 增强:
# 1. 端到端测试: 创建→计划→执行→聚合 完整链路测试
# 2. 超时处理: 每个 OrchestrationRun 全局超时
# 3. 部分成功: 支持 partial success (部分任务失败但整体可用)
# 4. 执行摘要: 每次 Run 完成后生成人类可读摘要
```

### 4.3 交付物

- [ ] 5 个 Agent 的增强实现
- [ ] `tests/test_orchestration_e2e.py` — 编排端到端测试
- [ ] `tests/test_agent_capabilities.py` — Agent 能力覆盖测试
- [ ] `scripts/agent_simulator.py` — 50+ Agent 模拟器

---

## 5. 可观测体系端到端

### 5.1 当前问题

1. **已集成但未端到端验证**: OTel/Prometheus/Grafana/Loki/Jaeger 代码已就位但未在完整链路中验证
2. **缺少关键告警**: 无告警规则触发验证
3. **Dashboard 不完整**: 缺少业务级 Dashboard（Agent 健康、编排成功率等）
4. **分布式追踪 ID 传播**: trace_id 在各服务间是否完整传递待验证

### 5.2 优化方案

#### 5.2.1 端到端可观测性验证

```
验证链路:
  用户请求 → Platform (trace_id=xxx)
    → Scheduler API (trace_id=xxx 传递)
      → Dispatcher (trace_id=xxx 传递)
        → Agent (trace_id=xxx 传递)
          → LLM API (trace_id=xxx 传递)

验证点:
  1. Jaeger UI 可见完整调用链
  2. Grafana Dashboard 显示各服务指标
  3. Loki 日志可按 trace_id 关联
  4. Prometheus 指标正确聚合
```

#### 5.2.2 新增告警规则

```yaml
# alerting_rules.yml 完善:
groups:
  - name: agent_alerts
    rules:
      - alert: AgentDown
        expr: up{job=~"agent-.*"} == 0
        for: 2m
        annotations:
          summary: "Agent {{ $labels.job }} is down"
      
      - alert: AgentHighErrorRate
        expr: rate(agent_errors_total[5m]) > 0.1
        for: 5m
        annotations:
          summary: "Agent error rate > 10%"
      
      - alert: OrchestrationRunFailed
        expr: rate(orchestration_runs_failed_total[15m]) > 0.05
        for: 10m
        annotations:
          summary: "Orchestration run failure rate > 5%"
      
      - alert: DatabaseConnectionPoolExhausted
        expr: pg_stat_activity_count > 50
        for: 1m
        annotations:
          summary: "DB connection pool nearing exhaustion"
```

#### 5.2.3 新增业务 Dashboard

```
Dashboard: "Agent Orchestration Overview"
  - Top:    活跃 Agent 数量、队列长度、编排成功率
  - Middle: Agent 延迟分布 (p50/p95/p99)
  - Bottom: 任务执行时间线、失败分布
```

### 5.3 交付物

- [ ] `configs/alerting_rules.yml` — 完善告警规则
- [ ] `configs/dashboards/agent-orchestration.json` — 业务 Dashboard
- [ ] `scripts/verify_observability.py` — 可观测性端到端验证
- [ ] `configs/grafana-dashboards.yml` — 更新 Dashboard 注册

---

## 6. 前端架构升级

### 6.1 当前问题

1. **Jinja2 模板仍为主要渲染方式**: `templates/` 下 7 个 HTML 文件
2. **React SPA 仅为脚手架**: `frontend/src/` 仅 `App.tsx` + `main.tsx`
3. **前后端耦合紧密**: 页面路由在 Python 端渲染
4. **缺少 API 文档/Swagger UI**: FastAPI 自带但未定制

### 6.2 优化方案

#### 6.2.1 技术栈确认

| 层 | 技术 |
|-----|------|
| 前端框架 | React 18 + TypeScript |
| 构建工具 | Vite 5 |
| UI 组件库 | Ant Design 5 |
| 状态管理 | Zustand (轻量) |
| 路由 | React Router 6 |
| HTTP 客户端 | Axios + React Query |
| 图表 | Recharts (Dashboard 页) |

#### 6.2.2 页面迁移计划

| 当前 Jinja2 页面 | React 页面 | 优先级 |
|-----------------|------------|--------|
| `index.html` | 首页 (文章列表) | P0 |
| `detail.html` | 文章详情页 | P0 |
| `login.html` | 登录页 | P0 |
| `register.html` | 注册页 | P0 |
| `create.html` | 创作页 (Markdown 编辑器) | P1 |
| `agent_demo.html` | Agent 控制台 | P1 |
| `base.html` | 全局布局 (Header/Footer) | P0 |

#### 6.2.3 API 对接

```
Platform API (8000):
  GET  /api/v1/posts          → 文章列表
  GET  /api/v1/posts/:id      → 文章详情
  POST /api/v1/posts          → 创建文章
  POST /api/v1/auth/login     → 登录
  POST /api/v1/auth/register  → 注册
  GET  /api/v1/agents         → Agent 状态
  POST /api/v1/ai/generate    → 触发 AI 生成
  GET  /api/v1/orchestration/runs → 编排运行列表

Scheduler API (8010):
  GET  /api/v1/tasks          → 任务列表
  GET  /api/v1/agents         → Agent 列表
  GET  /api/v1/queue          → 队列状态
```

#### 6.2.4 前端项目结构

```
frontend/
├── src/
│   ├── components/       # 通用组件
│   │   ├── Layout/       # Header, Footer, Sidebar
│   │   ├── PostCard/     # 文章卡片
│   │   ├── MarkdownEditor/
│   │   └── AgentPanel/   # Agent 控制面板
│   ├── pages/
│   │   ├── Home/
│   │   ├── PostDetail/
│   │   ├── PostCreate/
│   │   ├── Login/
│   │   ├── Register/
│   │   └── AgentConsole/
│   ├── hooks/            # 自定义 Hooks
│   ├── stores/           # Zustand stores
│   ├── services/         # API 调用封装
│   ├── types/            # TypeScript 类型
│   └── utils/            # 工具函数
├── vite.config.ts
└── tsconfig.json
```

### 6.3 交付物

- [ ] `frontend/` 完整 React SPA 实现
- [ ] Vite 代理配置（开发时转发到 8000/8010）
- [ ] 前后端分离部署配置

---

## 7. 验收指标与压测

### 7.1 验收指标定义

| 指标 | 目标值 | 测量方法 |
|------|--------|----------|
| Platform API p95 延迟 | < 200ms | Locust HTTP 压测 |
| Scheduler API p95 延迟 | < 100ms | Locust HTTP 压测 |
| Agent 任务执行 p95 延迟 | < 5000ms | 编排引擎日志统计 |
| 并发连接数 | 1000 (Platform) | k6/wrk 压测 |
| Agent 并发数 | 50+ Agent 同时运行 | Agent Simulator |
| 数据库 TPS (读) | > 1000 | pgbench |
| 数据库 TPS (写) | > 200 | pgbench |
| 端到端编排成功率 | > 99% | 100 次编排运行 |
| 容器启动时间 | < 60s | stop→start 计时 |
| 跨环境部署 | Docker Compose 一键成功 | 3 次冷启动 |

### 7.2 压测方案

#### 7.2.1 Agent 并发压测 (`scripts/stress_test_agents.py`)

```python
# 场景: 50+ Agent 同时在线，随机提交任务
# 测量: 调度延迟、队列深度、Dispatcher 吞吐
# 输出: CSV 报告 + Grafana 截图
```

#### 7.2.2 端到端编排压测 (`scripts/stress_test_orchestration.py`)

```python
# 场景: 并发创建 20 个编排运行，每个含 3-5 个任务
# 测量: Planner 响应时间、任务分配延迟、聚合时间
# 输出: 时间线报告 + 成功率
```

#### 7.2.3 HTTP API 压测 (`scripts/stress_test_api.py`)

```python
# 场景: 模拟 100 并发用户，持续 5 分钟
# 测量: p50/p90/p99 延迟、错误率、吞吐量
# 输出: Locust HTML 报告
```

### 7.3 交付物

- [ ] `scripts/stress_test_agents.py` — Agent 并发压测
- [ ] `scripts/stress_test_orchestration.py` — 编排压测
- [ ] `scripts/stress_test_api.py` — API 压测 (Locust)
- [ ] `scripts/acceptance_checklist.md` — 验收清单

---

## 8. 执行路线图

### Phase 1: 基础设施加固 (P0)

```
Week 1:
  Day 1-2: 容器化完善
    - 编写 docker-manage.ps1
    - 完善 .env.production
    - 增加 preflight-check.ps1
    - 验证 docker compose up 一键成功
  
  Day 3-5: 数据库迁移与调优
    - 增强 db_migrate_v2.py (rollback/dry-run)
    - 分级连接池配置
    - pgbench 基础压测
```

### Phase 2: 业务能力提升 (P1)

```
Week 2:
  Day 1-3: Agent 能力增强
    - 5 个 Agent 功能补全
    - Planner 闭环端到端验证
    - 50+ Agent 并发模拟器
  
  Day 4-5: 可观测性端到端
    - 全链路 trace 验证
    - 告警规则测试
    - 业务 Dashboard 创建
```

### Phase 3: 体验与验收 (P1)

```
Week 3:
  Day 1-3: 前端 SPA 迁移
    - 核心页面 React 实现
    - API 对接
    - 构建部署配置
  
  Day 4-5: 压测验收
    - 全部压测脚本编写与执行
    - 指标收集与报告
    - 问题修复循环
```

---

## 附录

### A. 关键配置文件清单

| 文件 | 作用 | 状态 |
|------|------|------|
| `docker-compose.yml` | 14 服务编排 | 待完善 |
| `.env.example` | 开发环境变量 | ✅ 完善 |
| `.env.production` | 生产环境变量 | 🔴 待创建 |
| `alembic.ini` | 数据库迁移配置 | ✅ |
| `configs/prometheus.yml` | Prometheus 采集配置 | 待验证 |
| `configs/alerting_rules.yml` | 告警规则 | 待完善 |
| `configs/dashboards/` | Grafana Dashboard | 待新增 |

### B. 端口分配

| 服务 | 端口 | 协议 |
|------|------|------|
| Platform | 8000 | HTTP |
| Scheduler API | 8010 | HTTP |
| Audit Agent | 8000 (容器内部) | HTTP |
| Planner Agent | 8100 | HTTP |
| Data Processor Agent | 8110 | HTTP |
| Tool Calling Agent | 8120 | HTTP |
| Content Generator Agent | 8130 | HTTP |
| Aggregator Agent | 8140 | HTTP |
| PostgreSQL | 5432 | TCP |
| Redis | 6379 | TCP |
| Jaeger UI | 16686 | HTTP |
| Jaeger OTLP | 4317 | gRPC |
| Prometheus | 9090 | HTTP |
| Loki | 3100 | HTTP |
| Grafana | 3000 | HTTP |

### C. 技术负债登记

| 项目 | 描述 | 优先级 |
|------|------|--------|
| Comment_Agent LLM 集成 | 目前返回 mock 数据 | P2 |
| Ado_Repost LLM 格式化 | formatter/translator 可能未接真实 LLM | P2 |
| CI/CD Pipeline | 主项目缺少 GitHub Actions | P2 |
| 测试覆盖率 | 需审查并补充单元测试 | P2 |
