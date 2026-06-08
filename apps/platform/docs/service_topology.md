# 服务拓扑文档 (Service Topology)

> P0 基线 — 明确各服务/组件的职责边界、交互关系、数据流向。

---

## 1. 总体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                         用户 / 客户端                              │
│                    (Browser, API Client, CLI)                     │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│              平台主服务 (Platform Main Service)                     │
│              端口: 8000  |  FastAPI + Jinja2                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────────┐ │
│  │ 页面渲染  │ │ REST API │ │ AI 服务  │ │ SchedulerClient SDK  │ │
│  │(pages.py)│ │(posts,   │ │(ai.py,   │ │(scheduler_client.py) │ │
│  │          │ │ comments,│ │ agent_)   │ │                      │ │
│  │          │ │ auth)    │ │          │ │                      │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┬───────────┘ │
│                                                     │             │
│  数据库: blog.db (SQLite)   缓存: Redis (可选)       │             │
│  文件: content/agent_drafts/  静态: static/ image/   │             │
└─────────────────────────────────────────────────────┼─────────────┘
                                                      │
                              ┌───────────────────────┤
                              │ 内部 HTTP (x-internal-token)
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│              调度中心 (Scheduler Center)                           │
│              端口: 8010  |  FastAPI                                │
│  ┌──────────────┐ ┌──────────────┐ ┌───────────────────────────┐  │
│  │ Task Submit  │ │  Dispatcher  │ │  Ingest Worker            │  │
│  │ API          │ │  (状态机调度) │ │  (Redis → SQLite 落库)    │  │
│  │ (router.py)  │ │(dispatcher.py)│ │  (ingest_worker.py)       │  │
│  └──────────────┘ └──────┬───────┘ └───────────────────────────┘  │
│                          │                                        │
│  数据库: scheduler.db (SQLite WAL)   Redis (可选, Fast Submit)     │
│  Agent 注册表: scheduler_agents 表                                 │
└──────────────────────────┼────────────────────────────────────────┘
                           │ HTTP 回调 (POST /api/internal/agent/run)
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────────┐
│ Audit Agent  │ │Comment Agent │ │ Ado Repost Agent │
│ 端口: 动态    │ │ 端口: 8020   │ │ 端口: 动态        │
│ task_type:   │ │ task_type:   │ │ task_type:       │
│ audit.draft  │ │comment.      │ │ ado_repost.run   │
│              │ │  moderate    │ │                  │
│ DB: 无       │ │ DB: 无       │ │ DB: 无           │
│ 依赖: LLM    │ │ 依赖: LLM    │ │ 依赖: 外部 API    │
│ + Shared     │ │              │ │                  │
│   Memory     │ │              │ │                  │
└──────┬───────┘ └──────────────┘ └──────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────┐
│          共享记忆池 (Shared Memory Pool)                           │
│  ┌────────────────┐  ┌──────────────────┐                        │
│  │ Redis Store    │  │ SQLite Store     │                        │
│  │ (热数据/分布式锁)│  │ (冷数据/本地存储) │                        │
│  └────────────────┘  └──────────────────┘                        │
│  依赖: Redis (可选)                                                │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. 各服务职责边界

### 2.1 平台主服务 (Platform Main Service)

| 维度 | 描述 |
|------|------|
| **文件** | `main.py`, `routers/`, `services/`, `crud/`, `schemas/`, `core/` |
| **端口** | `8000` (默认) |
| **职责** | 面向用户的 Web 服务，提供页面渲染、REST API、AI 交互入口 |
| **拥有数据** | `blog.db` — 用户、文章、评论、Agent 草稿、事件日志 |
| **不负责** | 异步任务调度、Agent 生命周期管理、跨服务数据共享 |
| **对外接口** | REST API (JSON + HTML), SSE 流式响应, Swagger UI `/docs` |
| **依赖服务** | 调度中心 (投递审核/搬运任务), Redis (评论 SSE 缓存), LLM API |
| **关键限制** | 不直接执行 Agent 任务，只通过 SchedulerClient SDK 投递 |

### 2.2 调度中心 (Scheduler Center)

| 维度 | 描述 |
|------|------|
| **文件** | `scheduler_center/main.py`, `router.py`, `dispatcher.py`, `ingest_worker.py` |
| **端口** | `8010` (默认) |
| **职责** | 统一异步任务调度中枢，负责任务队列、分发、重试、状态追踪 |
| **拥有数据** | `scheduler.db` — 任务、执行记录、事件、Agent 注册信息 |
| **不负责** | 业务逻辑执行（由 Agent 负责）、用户交互、页面渲染 |
| **对外接口** | 内部 REST API (`/api/internal/scheduler/*`)，需 `x-internal-token` 鉴权 |
| **依赖服务** | Redis (快速投递模式), Agent 服务 (HTTP 回调) |
| **关键限制** | 不感知业务语义，仅关注任务生命周期管理 |

#### 2.2.1 Dispatcher (调度器)

| 维度 | 描述 |
|------|------|
| **文件** | `scheduler_center/dispatcher.py` |
| **职责** | 核心任务调度引擎：状态机驱动、并发控制、Agent 路由选择、失败重试 |
| **状态流转** | `PENDING → RUNNING → SUCCEEDED / FAILED`；支持 `CANCELED` |
| **启动恢复** | 启动时自动将 `RUNNING` 状态任务重置为 `PENDING` |
| **并发模型** | 线程池 + SQLite WAL，最大并发由 `SCHEDULER_MAX_CONCURRENCY` 控制 |

#### 2.2.2 Ingest Worker (入库 Worker)

| 维度 | 描述 |
|------|------|
| **文件** | `scheduler_center/ingest_worker.py` |
| **职责** | 将 Redis 快速投递队列中的任务异步写入 SQLite 数据库 |
| **激活条件** | `SCHEDULER_FAST_SUBMIT_ENABLED=true` |
| **独立进程** | 可与 API 服务/Dispatcher 分离部署 |

### 2.3 Agent 服务

Agent 是调度中心的任务执行者，每个 Agent 为独立的 FastAPI 服务，通过 HTTP 回调接收任务。

#### 2.3.1 Audit Agent (审计 Agent)

| 维度 | 描述 |
|------|------|
| **文件** | `audit_agent.py` |
| **端口** | 动态（启动时通过 `AUDIT_AGENT_BASE_URL` 环境变量声明） |
| **职责** | 审核 Agent 生成的 Markdown 草稿，调用 LLM 检测风险并输出审核报告 |
| **任务类型** | `audit.draft` |
| **输入** | `draft_id`, `markdown_path`（本地文件路径） |
| **输出** | 审核结果写入 Shared Memory Pool (`audit:draft:{id}`) |
| **依赖** | LLM API, Shared Memory Pool |
| **注册方式** | 启动时自动向调度中心注册 (`_maybe_register()`) |

#### 2.3.2 Comment Agent (评论审核 Agent)

| 维度 | 描述 |
|------|------|
| **端口** | `8020` (约定) |
| **职责** | 审核用户评论内容，检测不当言论 |
| **任务类型** | `comment.moderate` |
| **状态** | 外部服务，本仓库不含其代码 |

#### 2.3.3 Ado Repost Agent (内容搬运 Agent)

| 维度 | 描述 |
|------|------|
| **端口** | 动态 |
| **职责** | 从外部平台搬运内容到博客 |
| **任务类型** | `ado_repost.run` |
| **状态** | 外部服务，本仓库不含其代码 |

### 2.4 Redis

| 维度 | 描述 |
|------|------|
| **端口** | `6379` (默认) |
| **用途** | 1. 平台主服务：评论 SSE 推送缓存、通用缓存<br>2. 调度中心：Fast Submit 快速投递队列<br>3. 共享记忆池：热数据存储、分布式锁 |
| **可选性** | 可降级运行：无 Redis 时，评论 SSE 降级为轮询，Fast Submit 禁用，记忆池仅用 SQLite |

### 2.5 PostgreSQL (规划)

| 维度 | 描述 |
|------|------|
| **用途** | 替代 SQLite，作为生产环境主数据库和调度中心数据库 |
| **当前状态** | 代码已支持 `DATABASE_URL` / `SCHEDULER_DATABASE_URL` 切换，Schema 通过 SQLAlchemy 自动兼容 |

---

## 3. 数据流向

### 3.1 用户评论审核流程

```
User → POST /posts/{id}/comments
  → comment_service.py 创建评论 (blog.db)
  → BackgroundTasks 投递 comment.moderate 任务
    → SchedulerClient SDK → 调度中心 (scheduler.db)
      → Dispatcher 轮询 → 路由到 Comment Agent
        → Agent 审核 → 回调更新评论状态
```

### 3.2 Agent 草稿审核流程

```
外部 Agent → POST /api/internal/agent/drafts
  → agent_ingest_service.py 保存 Markdown + 写入 agent_drafts 表 (blog.db)
  → 投递 audit.draft 任务
    → SchedulerClient SDK → 调度中心
      → Dispatcher → Audit Agent
        → LLM 审核 → 结果写入 Shared Memory
```

### 3.3 内容搬运流程

```
管理员 → POST /api/internal/tasks/ado-repost/run
  → 投递 ado_repost.run 任务
    → 调度中心 → Ado Repost Agent
      → 生成草稿 → POST /api/internal/agent/drafts (回写平台主服务)
```

---

## 4. 关键约束

1. **所有服务间调用必须携带 `x-internal-token` 头进行鉴权**
2. **Agent 必须实现 `GET /health` 端点**，调度中心定期健康检查
3. **调度中心不执行业务逻辑**，仅负责任务生命周期管理
4. **平台主服务不直接执行 Agent 任务**，必须通过调度中心投递
5. **Redis 为可选依赖**，所有功能在无 Redis 时降级运行
6. **数据库文件（.db）不纳入版本控制**，已在 `.gitignore` 中排除
