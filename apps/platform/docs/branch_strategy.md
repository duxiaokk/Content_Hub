# 实施分支策略 (Branch Strategy)

> P0 基线 — 定义 feature 分支及实施约定，确保多线开发有序推进。

---

## 1. 分支模型

```
main ────────────────────────────────────────────────────── (稳定发布)
  │
  ├── feature/infra ────── (基础设施 & 部署)
  ├── feature/db ───────── (数据库迁移 & 持久化)
  ├── feature/agent ────── (Agent 系统)
  ├── feature/observability (可观测性)
  └── feature/frontend ─── (前端重构)
```

### 核心规则

| 规则 | 说明 |
|------|------|
| **主线** | `main` 分支始终保持可部署状态 |
| **命名** | `feature/<domain>`，小写字母 + 连字符 |
| **基线** | 所有 feature 分支从 `main` 的同一 P0 基线 commit 创建 |
| **合并** | `feature/*` → `main` 需通过 PR + Code Review |
| **禁止** | 不直接在 `main` 上提交、不跨 feature 分支合并 |

---

## 2. feature 分支职责矩阵

### 2.1 `feature/infra` — 基础设施 & 部署

| 维度 | 内容 |
|------|------|
| **目标** | 统一项目基础设施，确保可重复部署 |
| **范围** | `.env.example` 规范、Docker 多服务编排、CI/CD 流水线、Vercel/服务器部署脚本 |
| **涉及文件** | `.env.example`, `Dockerfile`, `docker-compose.yml` (新增), `.github/workflows/` (新增), `vercel.json`, `scheduler_center/.env.example` |
| **不涉及** | 业务代码逻辑变更 |
| **完成标准** | `docker compose up` 一键启动全部服务；CI 自动 lint + test |

### 2.2 `feature/db` — 数据库迁移 & 持久化

| 维度 | 内容 |
|------|------|
| **目标** | 数据库从 SQLite 迁移到 PostgreSQL，确保数据安全与性能 |
| **范围** | PostgreSQL 支持、Alembic 迁移脚本整理、连接池调优、备份策略 |
| **涉及文件** | `database.py`, `core/config.py`, `scheduler_center/database.py`, `scheduler_center/config.py`, `migrations/`, `requirements.txt` (添加 `psycopg2`) |
| **不涉及** | ORM 模型结构变更（Schema 不变，只换后端） |
| **完成标准** | 同一套代码通过 `DATABASE_URL` 在 SQLite / PostgreSQL 上全部测试通过 |

### 2.3 `feature/agent` — Agent 系统

| 维度 | 内容 |
|------|------|
| **目标** | 完善 Agent 生命周期管理，补充缺失的 Agent 实现 |
| **范围** | Comment Agent 实现、Agent 错误处理增强、Agent 注册/心跳/健康检查完善、Agent Stub 升级、Agent 模板文档更新 |
| **涉及文件** | `audit_agent.py`, (新增 Comment Agent), `scheduler_center/agent_stub.py`, `scheduler_center/dispatcher.py`, `services/agent_service.py`, `scheduler_center/AGENT_TEMPLATE.md` |
| **不涉及** | 调度中心核心调度逻辑重构 |
| **完成标准** | 全部 3 种 task_type 的 Agent 可正常注册、执行、回写结果 |

### 2.4 `feature/observability` — 可观测性

| 维度 | 内容 |
|------|------|
| **目标** | 接入结构化日志、指标采集、链路追踪 |
| **范围** | 日志 JSON 格式化、Prometheus metrics 端点、请求 tracing (trace_id 传递)、健康检查增强、告警规则草案 |
| **涉及文件** | `main.py` (添加 `/health`, `/metrics`), `core/config.py` (日志配置), `scheduler_center/main.py`, `requirements.txt` (添加 `prometheus-client`, `python-json-logger`) |
| **不涉及** | 业务逻辑变更 |
| **完成标准** | 每个服务暴露 `/health` + `/metrics`；日志 JSON 结构化；trace_id 跨服务传递 |

### 2.5 `feature/frontend` — 前端重构

| 维度 | 内容 |
|------|------|
| **目标** | 前端从 Jinja2 服务端渲染迁移到前后端分离架构 |
| **范围** | 前端框架选型与初始化、API 调用层封装、页面组件开发、静态资源构建流程 |
| **涉及文件** | 新增前端项目目录, `routers/pages.py` (保留兼容), `main.py` (CORS 调整), `templates/` (保留兼容), `static/` (重构) |
| **不涉及** | 后端 API 契约变更（API 保持向后兼容） |
| **完成标准** | 核心页面 (首页/详情/创作) 在前后端分离模式下正常工作 |

---

## 3. 分支依赖关系

```
feature/infra ──────── 无依赖，可最先启动
feature/db ─────────── 依赖 infra (配置规范)
feature/observability ─ 依赖 infra (端口/健康检查规范)
feature/agent ──────── 依赖 infra + db
feature/frontend ───── 依赖 infra (API 规范)
```

### 推荐启动顺序

```
Phase 1: feature/infra      (1 周)
Phase 2: feature/db + feature/observability  (并行，1-2 周)
Phase 3: feature/agent + feature/frontend     (并行，2-3 周)
```

---

## 4. 开发约定

### Commit 规范

```
<type>(<scope>): <简短描述>

类型：
  feat     — 新功能
  fix      — 修复
  refactor — 重构
  docs     — 文档
  test     — 测试
  chore    — 构建/工具

示例：
  feat(agent): add Comment Agent implementation
  fix(db): resolve PostgreSQL connection pool leak
  docs(infra): add docker-compose deployment guide
```

### Code Review 必查项

- [ ] 环境变量变更是否同步到 `.env.example`
- [ ] 新增 API 是否更新 `docs/api_contract_v1.md`
- [ ] 端口/健康检查变更是否更新 `docs/deployment_checklist.md`
- [ ] 是否通过 `python tasks.py lint` 和 `python tasks.py test`
- [ ] 数据库迁移是否包含回滚路径

### 分支生命周期

```
1. git checkout main && git pull
2. git checkout -b feature/<name>
3. 开发 → 自测 → lint → 提交
4. 发起 PR → Code Review → 通过
5. 合并到 main → 删除 feature 分支
```

---

## 5. 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| feature 分支长期不合并导致冲突 | 定期从 `main` rebase，每个 feature 周期不超过 3 周 |
| infra 变更影响所有 feature | `feature/infra` 优先完成并合并，其他分支 rebase |
| 前端重构破坏现有页面 | Jinja2 页面保留兼容，新前端通过路径/子域名区分 |
| PostgreSQL 迁移导致数据丢失 | 先在测试环境充分验证，编写数据迁移脚本 + 回滚脚本 |
