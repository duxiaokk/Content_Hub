# Content Hub 产品架构方案

## 1. 文档目标

本文档用于把 Content Hub 从“已有若干抓取、改写、发布能力的代码仓库”收敛为“可持续演进的产品方案”。

当前阶段不追求一次性重构全部目录和服务，而是明确以下四件事：

1. 产品边界：系统最终解决什么问题。
2. 统一模型：三类业务场景如何共用一套内容底座。
3. 模块职责：现有仓库中哪些模块承担哪些角色。
4. 近期落地：MVP 版本先做什么，哪些能力暂缓。

## 2. 产品定义

Content Hub 的目标不是单一抓取器，也不是单一博客发布器，而是一个面向个人创作者和小团队的内容运营中台。

它负责把外部信息源转化为三类稳定产出：

1. 可审核、可发布的内容草稿。
2. 自动生成的日报、周报和摘要卡片。
3. 可持续积累的知识归档条目。

## 3. 统一业务视角

当前拟覆盖的三类场景：

1. 内容雷达 + 外脑
2. 垂直领域自动资讯站
3. 个人知识管理自动归档

这三类场景不应拆成三套系统，而应共用一套内容管线，只通过“信源配置、处理规则、发布目标、归档策略”区分。

统一后的产品视角如下：

| 场景 | 主要输入 | 核心处理 | 主要输出 |
|---|---|---|---|
| 内容雷达 | 技术大 V、RSS、社交动态 | 去重、过滤、摘要、翻译、改写 | 审核稿、博客草稿 |
| 自动资讯站 | 新闻站、GitHub Trending、论文 RSS、Reddit | 聚合、分类、标签、摘要、日报生成 | 资讯站内容、日报、引流摘要 |
| 自动归档 | 收藏、点赞、稍后读、视频内容 | 转录、摘要、主题归档、回顾 | 知识卡片、项目档案、周回顾 |

## 4. 产品边界

### 4.1 系统负责

1. 管理信源订阅和抓取频率。
2. 对抓取结果做标准化、去重、过滤、分类和 AI 处理。
3. 把结果送入审核队列。
4. 生成博客草稿、日报、知识条目等结构化产物。
5. 记录工作流运行状态、失败原因、发布结果和回顾状态。

### 4.2 系统暂不负责

1. 完整多租户隔离。
2. 全量 DAG 可视化拖拽编排。
3. 高复杂度协同编辑器。
4. 全渠道正式发布生态的一次性打齐。
5. 企业级权限模型和审计中心。

## 5. 总体架构

```text
+---------------------+      +----------------------+      +----------------------+
| Source Subscriptions| ---> | Ingestion & Normalize| ---> | Filter & Dedup       |
+---------------------+      +----------------------+      +----------------------+
                                                                      |
                                                                      v
+---------------------+      +----------------------+      +----------------------+
| Review Queue        | <--- | AI Processing        | <--- | Classification/Score |
+---------------------+      +----------------------+      +----------------------+
           |                            |
           v                            v
+---------------------+      +----------------------+
| Distribution        |      | Knowledge Archive    |
+---------------------+      +----------------------+
           |
           v
+---------------------+
| Blog / Notion / etc |
+---------------------+
```

## 6. 模块职责划分

结合当前仓库，建议采用如下职责划分：

| 逻辑模块 | 当前目录 | 职责 |
|---|---|---|
| Web Console / Platform | `apps/platform` | 控制台、审核、配置、内部任务入口、监控 |
| Scheduler Center | `apps/platform/scheduler_center` | 定时任务调度、工作流触发、运行状态管理 |
| Workflow Engine | `apps/workflow_engine` | 工作流定义、注册表、线性/DAG 执行 |
| Fetcher Engine | `apps/fetcher_engine` | 信源抓取、标准化、游标与增量控制 |
| AI Processor | `apps/ai_processor` | 摘要、翻译、改写、标签、分类、评分 |
| Publisher Engine | `apps/publisher_engine` | 发布目标适配、草稿投递、结果回写 |
| Shared Memory | `libs/shared_memory` | 共享状态、游标、公共持久化能力 |

## 7. 统一内容模型

全系统应围绕统一内容实体构建，不按来源平台分别建模主流程。

### 7.1 核心实体

#### `content_item`

表示采集进入系统的原始内容主记录。

建议字段：

- `id`
- `source_type`
- `source_account`
- `source_url`
- `external_id`
- `title`
- `raw_text`
- `raw_html`
- `language`
- `published_at`
- `ingested_at`
- `dedup_key`
- `pipeline_status`
- `review_status`
- `publish_status`
- `archive_status`
- `score`
- `error_message`

#### `content_asset`

表示由原始内容派生出的处理结果。

建议字段：

- `id`
- `content_item_id`
- `asset_type`：summary / translation / rewrite / title / tags / transcript / report_snippet
- `version`
- `body`
- `metadata`
- `created_at`

#### `source_subscription`

表示一个被监控的来源配置。

建议字段：

- `id`
- `source_type`
- `source_name`
- `account_identifier`
- `feed_url`
- `schedule_expression`
- `enabled`
- `category`
- `default_tags`
- `last_cursor`

#### `workflow_run`

表示一次工作流执行记录。

建议字段：

- `id`
- `workflow_name`
- `trigger_type`
- `status`
- `started_at`
- `finished_at`
- `items_total`
- `items_succeeded`
- `items_failed`
- `error_summary`
- `trace_payload`

#### `review_queue`

表示待审核工作项。

建议字段：

- `id`
- `content_item_id`
- `candidate_asset_id`
- `status`
- `reviewer`
- `review_note`
- `reviewed_at`

#### `publish_record`

表示面向单一目标的一次发布尝试。

建议字段：

- `id`
- `content_item_id`
- `target_type`
- `target_name`
- `status`
- `external_url`
- `external_id`
- `response_payload`
- `published_at`

### 7.2 当前阶段建模策略

当前仓库已经有最小 `content_items` 主表和基础状态回写能力。MVP 阶段不建议马上把所有从表一次性建完，建议分两步：

1. 先扩展 `content_items` 字段以支撑审核、分类和日报。
2. 待闭环稳定后，再拆出 `content_asset`、`review_queue`、`publish_record`。

## 8. 核心流程设计

### 8.1 通用内容流程

1. 定时任务触发抓取。
2. 抓取器拉取近一段时间的新内容。
3. 统一转换为标准内容对象。
4. 执行去重和关键词过滤。
5. 对保留内容执行摘要、翻译、改写、分类。
6. 将候选结果写入审核队列。
7. 审核通过后投递到发布目标。
8. 同步生成归档记录、日报条目或回顾素材。

### 8.2 三类标准工作流模板

#### `radar_pipeline`

用于个人或小团队内容雷达。

步骤：

1. `fetch`
2. `dedup_filter`
3. `summarize`
4. `translate_rewrite`
5. `review`
6. `publish_blog_draft`

#### `newsroom_pipeline`

用于自动资讯站。

步骤：

1. `fetch_multi_source`
2. `dedup_filter`
3. `classify_tag`
4. `summarize`
5. `generate_digest`
6. `publish_site`
7. `distribute_social`

#### `archive_pipeline`

用于个人知识归档。

步骤：

1. `fetch_saved_content`
2. `extract_text_or_transcript`
3. `summarize`
4. `classify_by_topic`
5. `archive`
6. `schedule_review`

## 9. 信源策略

### 9.1 MVP 支持信源

第一阶段建议优先支持：

1. RSS
2. GitHub Trending
3. Reddit
4. CNBlogs
5. Bilibili RSS 代理源

原因：

- 接入成本低
- 权限模型简单
- 可测试性高
- 适合先验证统一内容模型

### 9.2 第二阶段补充

1. X / Twitter
2. YouTube
3. 论文 RSS
4. 飞书/Notion 收藏输入
5. 视频转录源

## 10. AI 处理策略

AI Processor 不应只有“改写”一个能力，应在统一处理链中支持以下步骤：

1. `summarize`
2. `translate`
3. `rewrite`
4. `classify`
5. `tag`
6. `title_generate`
7. `quality_score`

建议处理顺序：

1. 先做轻量过滤与规则命中。
2. 再做摘要和分类。
3. 最后只对高价值内容执行较昂贵的翻译与改写。

这样可以控制 token 成本。

## 11. 审核与分发策略

### 11.1 审核

审核台是产品闭环中的关键节点，MVP 必须具备：

1. 待审核列表。
2. 原文、摘要、改写稿对照查看。
3. 通过、驳回、归档。
4. 人工编辑最终稿。

### 11.2 分发

MVP 优先支持以下目标：

1. 博客草稿
2. Markdown 导出
3. 日报文件生成

第二阶段再补：

1. Notion
2. 飞书
3. Discord
4. WordPress
5. 社交平台引流摘要

## 12. 控制台信息架构

建议控制台优先实现 6 个页面：

1. 信源中心
2. 规则中心
3. 内容工作台
4. 审核队列
5. 分发中心
6. 日报/归档中心

### 12.1 信源中心

用于管理订阅对象：

- 来源类型
- 账号或 feed 地址
- 启停状态
- 抓取频率
- 分类归属

### 12.2 规则中心

用于配置：

- 关键词白名单/黑名单
- 去重规则
- 标签规则
- AI 模板
- 发布模板

### 12.3 内容工作台

用于查看抓取结果和 AI 处理结果：

- 新内容
- 已过滤
- 已处理
- 待审核
- 已归档

### 12.4 审核队列

用于执行最终人工判断。

### 12.5 分发中心

用于查看草稿投递和日报生成结果。

### 12.6 日报/归档中心

用于查看日报生成结果和知识卡片沉淀状态。

## 13. 非功能要求

### 13.1 稳定性

1. 抓取、处理、发布均需有明确失败状态。
2. 每一步都应记录错误原因。
3. 工作流支持幂等执行，避免重复发布。

### 13.2 成本控制

1. 先规则过滤，再调用 LLM。
2. 对低价值内容只做摘要，不做完整改写。
3. 记录每次运行的 token 消耗。

### 13.3 可运维性

1. 每个工作流有独立运行记录。
2. 每次发布有独立结果记录。
3. 每类信源可单独停用。

## 14. 当前阶段不建议做的事

1. 一次性重写现有目录结构。
2. 过早做复杂多租户。
3. 先做全功能可视化 DAG 编排器。
4. 直接接入大量高风控社交平台抓取。
5. 在没有审核闭环之前做全自动正式发布。

## 15. 推荐实施顺序

### Phase 1：MVP 闭环

目标：

每天自动抓取多个技术信源，筛出值得看的内容，生成中文摘要和改写稿，人工审核后一键发到博客。

### Phase 2：资讯站扩展

目标：

支持多主题聚合、日报生成、SEO 发布和外部通知。

### Phase 3：知识归档扩展

目标：

支持收藏内容接入、转录、主题归档和周回顾。

## 16. 结论

Content Hub 应当按“一套内容底座 + 多种工作流模板 + 多目标输出”的方向演进。

当前仓库已经具备抓取、改写、发布和调度的基础雏形。正确路径不是推倒重来，而是：

1. 统一内容模型。
2. 收敛模块职责。
3. 先跑通 MVP 闭环。
4. 再逐步扩展资讯站和知识归档能力。
