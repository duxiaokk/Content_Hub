# Content Hub 端到端打通设计方案

范围：平台主服务 + Console + 调度器 + 抓取/AI/发布  
目标：可启动、可触发、可追踪、可发布  
输出：可落地的分阶段改造

## 问题清单（按阻断程度排序）

- **P0** 平台主服务启动失败：启动脚本未设置 `PYTHONPATH`，且 `SECRET_KEY` 缺失会在配置加载时直接抛错。
- **P0** Console 仍提交 `ado_repost.run`，而调度器已具备本地可执行分支（`content.workflow.run` / `content.pipeline.linear` / `content.pipeline.radar` / `content.publish.approved`），导致端到端依赖旧 agent。
- **P1** 工作流注册表不全：`apps/workflow_engine/registry/bootstrap.py` 仅注册 CNBlogs/Bilibili，线性流水线无法覆盖 RSS/GitHub Trending/Reddit。
- **P1** 抓取-入库-审核-发布链路被拆成两条：旧 content_bridge 写 AgentDraft，新平台 Console 以 ContentItem/Post 为主；数据不统一导致“抓到了但发布不了/审核不了”。
- **P1** 发布默认禁用：`ADO_PUBLISH_ENABLED` 默认为 `false`，会造成“看起来都成功了但外部发布没发生”。
- **P2** 单测仅剩 RSS 边界用例失败：属于可快速修复的正确性问题，但不影响架构打通的总体方案。

## 设计目标与原则

- 一个命令可启动：开发态至少做到“脚本启动即起服务”，不要求手动切目录/手工设置路径。
- 一个入口触发抓取：Console 的“运行数据源”必须落到 `FetchService` 或其等价能力上，避免旧任务类型与旧 agent 依赖。
- 链路可追踪：每次抓取/处理/发布都有统一 `trace_id`，Console 能查到状态、错误、产出条数。
- 数据主干唯一：以 `ContentItem` 作为“内容资产主表”，AgentDraft 仅保留兼容或逐步退役。
- 增量与去重内聚：游标、去重窗口、幂等键在同一条链路里闭环，不依赖前端/人工约定。

## 方案总览（推荐的端到端主链路）

主链路明确为：

Console → Scheduler Center → FetchService → ContentItem 入库 → Radar Pipeline（AI 处理/准备审核） → Console 审核 → 发布（写 Post + 可选外部发布）

说明：

- 优先使用“本地执行”的任务类型（无需 content_bridge agent），并复用已存在的 `content.pipeline.radar` 能力。
- 线性流水线 `content.pipeline.linear` 可作为“快速端到端演示/自动发布”的备用路径。

## 启动与导入路径统一（P0）

### 现状

- `infra/scripts/start_content_hub.ps1` 进入 `apps/platform` 运行 `uvicorn main:app`，但未注入 `PYTHONPATH`。
- `apps/platform/core/config.py` 强制要求 `SECRET_KEY`，缺失时 import 阶段直接报错。

### 设计

- 开发态启动脚本必须注入 `PYTHONPATH=<projectRoot>`，使 `apps.*` 可见。
- 开发态允许脚本兜底设置 `SECRET_KEY`（仅本地），生产/容器化仍要求显式注入。
- 消除“平台代码里混用 `apps.workflow_engine` 与 `workflow_engine`”这种路径隐患：统一改成 `apps.*` 导入（当前已发现点：`apps/platform/services/console_service.py`）。

### 脚本建议（示例）

```powershell
# start_content_hub.ps1（示意）
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$appDir = Join-Path $projectRoot "apps\platform"

$env:PYTHONPATH = $projectRoot
if (-not $env:SECRET_KEY) { $env:SECRET_KEY = "local-dev-secret-key" }  # 仅开发态兜底

Push-Location $appDir
py -3.11 -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
Pop-Location
```

> 若希望彻底消除“必须在 apps/platform 目录运行”的约束，可进一步重构为 `uvicorn apps.platform.main:app` + 平台内部相对导入（`from .core...` / `from .routers...`）。

## 环境变量与配置分层（P0/P1）

### 推荐分层

| 场景 | 加载方式 | 最小必需变量 | 备注 |
|---|---|---|---|
| 本地开发 | 启动脚本设置 + 可选 `.env` | `SECRET_KEY`、`DATABASE_URL`（或 SQLite 路径） | 允许脚本兜底 `SECRET_KEY` |
| CI/单测 | pytest 前统一设置 | `SECRET_KEY=test-*` | 当前多处测试已 `os.environ.setdefault` |
| 容器/生产 | docker compose / secrets 注入 | `SECRET_KEY`、DB/Redis/LLM Key 等 | 严格不兜底，避免误用弱密钥 |

### 发布开关

- 保留 `ADO_PUBLISH_ENABLED` 默认 `false` 的安全策略。
- 在开发文档/示例 `.env` 中显式写出 `ADO_PUBLISH_ENABLED=true`，避免“功能好像没跑”的误解。

## Console → 调度 → 抓取：从旧任务迁移到本地执行（P0/P1）

### 现状

- `/console/sources/{id}/run` 最终调用 `services.console_service.trigger_fetch()`，提交 `task_type=ado_repost.run`。
- 调度器对 `ado_repost.run` 走“挑选 agent”逻辑；若无 agent，就会卡在 “no available agent”。

### 设计（推荐落地路径）

- 将 Console 的“运行数据源”任务类型切换为本地执行：新增或复用一个本地 task_type，完全绕开 agent。
  - 方案 A（推荐）：新增 `content.fetch.batch`（或 `content.source.fetch`）任务，本地执行时直接调用 `apps.fetcher_engine.api.service.FetchService.run_sources()`，由它写入 `ContentItem`（`pipeline_status=fetched`）。
  - 方案 B（备选）：直接用现有 `content.pipeline.linear` 作为 Console 运行入口，但需要先补齐 workflow registry 的抓取器注册，且线性流水线会连带 AI/发布，变更面更大。
- FetchRun 作为 Console 追踪抓取的事实来源：本地任务成功后，把 `fetched/inserted/deduped` 写回 FetchRun，Console 列表即可展示真实产出。

### 兼容旧 ado_repost.run（P1）

- 短期保留旧任务类型：调度器执行 `ado_repost.run` 时，若 payload 含 `source_config_id/source_type` 等平台字段，则自动走本地 `FetchService` 分支；否则仍按旧 agent 路由。
- 这样可以在不立即改前端的情况下先打通链路，同时逐步把 UI/API 迁移到新 task_type。

## 抓取后 AI 处理：复用 Radar Pipeline（P1）

### 为什么选 Radar Pipeline

- `WorkflowEngineService.run_radar_pipeline()` 已能从 DB 读取 `pipeline_status=fetched` 的 ContentItem，并调用 AIProcessingService 处理。
- 支持按 `source_type` 过滤，天然适配“只处理本次抓取的数据源”。

### 落地方式

- 抓取任务完成后由用户手动触发：新增 Console 按钮“AI 处理”，提交 `content.pipeline.radar`，payload 携带 `source_type` 与 `limit`。
- 或由系统自动触发：在抓取任务成功回调（或 FetchRun 状态同步）后，自动追加一次 `content.pipeline.radar` 任务（幂等键：`fetch_run_id`）。

## 审核与发布：统一到 ContentItem/Post（P1）

### 目标形态

- 审核入口：基于 `ContentItem.review_status`（pending/approved/rejected）。
- 发布入口：写 `Post` 表作为“站内博客稿”，再按开关决定是否调用外部发布（publisher_engine）。

### 建议

- Console 的“审核通过→发布”可继续同步写 Post（现在已实现），但建议补齐 PublishRecord（或等价表）记录，以便追踪重复发布/失败重试。
- 如果要走异步发布：直接复用 `content.publish.approved`（调度器已有本地执行分支），Console 点击后提交任务并轮询状态。

> AgentDraft 路径建议仅保留兼容期：要么淘汰，要么做“AgentDraft → ContentItem”的一次性迁移/晋升逻辑，避免内容资产分裂。

## 工作流注册表补齐（P1）

### 现状

`apps/workflow_engine/registry/bootstrap.py` 仅注册 CNBlogs/Bilibili；而 `apps/fetcher_engine/api/registry.py` 已注册 RSS/GitHub Trending/Reddit 等更多 `source_type`。

### 两条补齐策略

- 策略 1（快速）：在 workflow registry 的 bootstrap 中补注册 GitHubTrendingFetcher、RedditFetcher 等“无强配置依赖”的抓取器，让 `content.pipeline.linear` 立即可跑更多源。
- 策略 2（可扩展）：将 RSS 等需要动态参数（feed_url/account 等）的 fetcher 改造成“从 `FetchRequest.options` 取参数”的模式，注册时不绑定具体 URL，从而让一个 fetcher 覆盖多条订阅。

> 如果主链路采用 “FetchService → Radar Pipeline”，workflow registry 的 fetcher 完整性不再是端到端阻断项，但仍建议补齐以避免功能漂移。

## 分阶段落地计划（含回滚）

### Phase 0：让平台先起得来（1 天）

- 修改 `infra/scripts/start_content_hub.ps1`：注入 `PYTHONPATH`，开发态兜底 `SECRET_KEY`。
- 修正平台内不一致导入：把 `apps/platform/services/console_service.py` 的 `workflow_engine.*` 统一改为 `apps.workflow_engine.*`。
- 回滚方式：仅脚本与少量 import 改动，随时可撤回；不改数据库结构。

### Phase 1：Console 触发抓取改为本地执行（2-3 天）

- 新增本地 task_type（如 `content.fetch.batch`）并在 scheduler_center 增加本地执行分支：调用 `FetchService.run_sources()`，并把统计写回任务结果与 FetchRun。
- 将 Console 的 `trigger_fetch` 从提交 `ado_repost.run` 改为提交新 task_type（或直接提交 `content.pipeline.linear` 作为过渡）。
- 回滚方式：保留旧接口/旧任务类型；出现问题可切回 `ado_repost.run`。

### Phase 2：AI 处理与发布闭环（2-4 天）

- 在 Console 增加“AI 处理”入口：提交 `content.pipeline.radar`（可按 source_type 限定）。
- 发布侧统一：优先让“审核通过→发布”写 Post 成功即完成 MVP；外部发布通过 `ADO_PUBLISH_ENABLED` 明确启用。
- 回滚方式：AI 处理与外部发布均可通过开关禁用，不影响抓取入库。

### Phase 3：旧 content_bridge/ado_repost 退役（按风险择机）

- 将 `ado_repost.run` 降级为兼容入口或彻底移除，平台只保留本地任务类型。
- 对 AgentDraft 做一次性迁移或停止写入，确保内容资产唯一。

## 测试与验收口径

- 启动验收：运行启动脚本后能访问 `/health` 与 `/console`，且不会因 `SECRET_KEY` 缺失崩溃。
- 抓取验收：Console 创建一个数据源，点击“运行”后 FetchRun 状态可从 pending → success，ContentItem 有新增，且 `pipeline_status=fetched`。
- 处理验收：触发 radar pipeline 后，ContentItem 的 AI 字段（如 summary/rewritten/tags）更新，Console 可进入审核。
- 发布验收：审核通过后写 Post 成功；若开启 `ADO_PUBLISH_ENABLED`，外部发布产生可追踪记录（或返回外部 id）。
- 单测补齐：修复 RSS lookback/limit 边界用例，保证抓取层正确性。

