# Content Hub MVP 开发任务清单

## 1. MVP 目标

MVP 版本只解决一个明确问题：

每天自动抓取多个技术信源，筛出值得看的内容，生成中文摘要和改写稿，进入人工审核队列，审核通过后一键发布到博客草稿，并自动生成一份日报 Markdown。

## 2. MVP 范围

### 2.1 本期必须完成

1. 多信源抓取：RSS、CNBlogs、Bilibili RSS 代理、GitHub Trending、Reddit。
2. 内容标准化入库。
3. 去重和关键词过滤。
4. AI 摘要、翻译、改写。
5. 审核队列。
6. 博客草稿发布。
7. 日报 Markdown 生成。
8. 控制台最小可用页面。

### 2.2 本期明确不做

1. 正式社交平台自动发布。
2. 视频音频转录。
3. 复杂 DAG 编排。
4. 多租户和组织权限。
5. 完整知识库检索系统。

## 3. MVP 业务闭环

```text
定时抓取
  -> 标准化入库
  -> 去重过滤
  -> AI 摘要/翻译/改写
  -> 待审核
  -> 审核通过
  -> 博客草稿发布
  -> 写入日报
```

## 4. 模块任务拆解

## 4.1 `apps/fetcher_engine`

### 目标

统一抓取入口，输出标准内容对象。

### 开发任务

1. 新增统一抓取服务层：
   - `fetcher_engine/api/service.py`
   - 职责：按 source subscription 批量调度抓取器，返回统一结果。
2. 完成 RSS 抓取器稳定化：
   - 复用 `runtime/rss.py`
   - 支持 feed 元数据回写。
3. 新增 GitHub Trending 抓取器：
   - 目录：`connectors/github_trending/`
   - 输出统一 `UnifiedPost` 或工作流契约对象。
4. 新增 Reddit 抓取器：
   - 目录：`connectors/reddit/`
   - MVP 可先用公开 RSS 或 JSON 入口。
5. 扩展 CNBlogs/Bilibili 抓取器：
   - 补齐 source account、发布时间、摘要、链接字段。
6. 增量控制：
   - 使用 `shared_memory` 或数据库记录 cursor / last_seen。
7. 失败容错：
   - 单一信源失败不阻断整个批次。

### 对外接口

#### Python 接口

```python
class FetchService:
    async def run_sources(self, request: FetchBatchRequest) -> FetchBatchResult:
        ...
```

#### 请求模型

```python
class FetchBatchRequest(BaseModel):
    run_id: str
    sources: list[str]
    lookback_hours: int = 24
    limit_per_source: int = 20
    options: dict[str, Any] = {}
```

#### 返回模型

```python
class FetchBatchResult(BaseModel):
    run_id: str
    items: list[dict]
    errors: list[dict]
    stats: dict[str, Any]
```

## 4.2 `apps/workflow_engine`

### 目标

把当前 pipeline 能力扩成可执行 MVP 的标准工作流。

### 开发任务

1. 保留现有 `linear_pipeline.py` 作为 MVP 主路径。
2. 增加流程节点语义：
   - `fetch`
   - `filter`
   - `process`
   - `review_prepare`
   - `publish`
   - `digest_generate`
3. 扩展 `registry/contracts.py`：
   - 增加过滤结果、审核结果、日报结果模型。
4. 新增工作流模板定义：
   - `radar_pipeline`
   - `daily_digest_pipeline`
5. 增加运行轨迹记录：
   - 每步耗时
   - 成功数
   - 失败数
   - token 成本
6. 增加幂等控制：
   - 同一 `dedup_key + target` 不重复发布。

### 对外接口

#### 内部服务接口

```python
class WorkflowService:
    async def run_radar_pipeline(self, request: RadarPipelineRequest) -> dict[str, Any]:
        ...
```

#### 请求模型

```python
class RadarPipelineRequest(BaseModel):
    run_id: str
    workflow_name: str = "radar_pipeline"
    sources: list[str]
    lookback_hours: int = 24
    limit_per_source: int = 20
    filters: dict[str, Any] = {}
    process_options: dict[str, Any] = {}
    publish_options: dict[str, Any] = {}
```

#### HTTP 入口

- `POST /api/internal/tasks/content-pipeline/radar/run`
- `POST /api/internal/tasks/content-pipeline/daily-digest/run`

## 4.3 `apps/ai_processor`

### 目标

把当前“改写”扩成完整的内容筛选与生成处理链。

### 开发任务

1. 保留 `processors/rewrite/processor.py`。
2. 新增 `processors/summarize/processor.py`。
3. 新增 `processors/classify/processor.py`。
4. 新增 `processors/tag/processor.py`。
5. 可选新增 `processors/translate/processor.py`，或将翻译并入 rewrite。
6. 统一处理配置：
   - provider
   - model
   - timeout
   - fallback
   - token limit
7. 引入分层处理策略：
   - 先规则过滤
   - 再摘要与分类
   - 最后对高分内容执行完整改写
8. 为输出结果增加结构化 metadata：
   - 原语言
   - 主题
   - 标签
   - 质量评分

### 对外接口

#### Python 接口

```python
class ContentProcessingService:
    async def process_batch(self, request: ProcessBatchRequest) -> ProcessBatchResult:
        ...
```

#### 请求模型

```python
class ProcessBatchRequest(BaseModel):
    run_id: str
    items: list[dict]
    processors: list[str]
    options: dict[str, Any] = {}
```

#### 返回模型

```python
class ProcessBatchResult(BaseModel):
    run_id: str
    results: list[dict]
    errors: list[dict]
    token_usage: int = 0
```

## 4.4 `apps/platform`

### 目标

承载信源配置、规则配置、审核队列、日报查看和内部任务触发。

### 开发任务

1. 新增信源管理模型与 CRUD：
   - `source_subscriptions`
2. 新增规则配置模型与 CRUD：
   - `filter_rules`
   - `rewrite_profiles`
3. 扩展 `content_items`：
   - `source_account`
   - `language`
   - `review_status`
   - `score`
   - `tags`
   - `summary`
   - `rewritten_title`
4. 新增审核队列模型与 CRUD：
   - `review_queue`
5. 新增日报记录模型与 CRUD：
   - `digest_reports`
6. 新增内部任务路由：
   - 触发 radar pipeline
   - 触发日报生成
7. 新增页面或 API：
   - 信源列表
   - 待审核列表
   - 单条内容审核页
   - 日报查看页
8. 审核操作：
   - 通过
   - 驳回
   - 归档
   - 编辑后通过

### 对外接口

#### 信源管理 API

- `GET /api/internal/content/sources`
- `POST /api/internal/content/sources`
- `PATCH /api/internal/content/sources/{source_id}`
- `POST /api/internal/content/sources/{source_id}/enable`
- `POST /api/internal/content/sources/{source_id}/disable`

#### 审核 API

- `GET /api/internal/content/reviews`
- `GET /api/internal/content/reviews/{review_id}`
- `POST /api/internal/content/reviews/{review_id}/approve`
- `POST /api/internal/content/reviews/{review_id}/reject`
- `POST /api/internal/content/reviews/{review_id}/archive`

#### 日报 API

- `GET /api/internal/content/digests`
- `GET /api/internal/content/digests/{digest_id}`
- `POST /api/internal/content/digests/generate`

## 4.5 `apps/publisher_engine`

### 目标

把内容投递到博客草稿，并输出日报 Markdown。

### 开发任务

1. 保留 `adapters/blog/publisher.py`。
2. 新增 `adapters/markdown_export/publisher.py`：
   - 输出日报 Markdown 文件或字符串。
3. 支持统一发布目标：
   - `blog`
   - `digest_markdown`
4. 记录每次发布结果：
   - target
   - status
   - response
5. 支持草稿模式和正式模式参数，但 MVP 默认草稿模式。

### 对外接口

#### Python 接口

```python
class PublishingService:
    async def publish_batch(self, request: PublishBatchRequest) -> PublishBatchResult:
        ...
```

#### 请求模型

```python
class PublishBatchRequest(BaseModel):
    run_id: str
    items: list[dict]
    targets: list[dict]
```

#### 返回模型

```python
class PublishBatchResult(BaseModel):
    run_id: str
    results: list[dict]
    errors: list[dict]
```

## 4.6 `apps/platform/scheduler_center`

### 目标

定时触发内容雷达工作流和日报工作流。

### 开发任务

1. 新增两类标准任务名：
   - `content.pipeline.radar`
   - `content.pipeline.daily_digest`
2. 调度配置支持 cron 表达式。
3. 每日 09:00 触发 radar pipeline。
4. 每日 09:15 触发 digest pipeline。
5. 增加任务日志和最近运行状态展示。

### 对外接口

- `POST /api/internal/scheduler/tasks`
- `GET /api/internal/scheduler/tasks`
- `GET /api/internal/scheduler/tasks/{id}`

任务 `payload` 示例：

```json
{
  "task_type": "content.pipeline.radar",
  "payload": {
    "workflow_name": "radar_pipeline",
    "sources": ["cnblogs", "bilibili", "github_trending", "reddit_ai"],
    "lookback_hours": 24,
    "limit_per_source": 20,
    "filters": {
      "keywords": ["agent", "rag", "openai", "llm"],
      "exclude_keywords": ["招聘", "广告"]
    },
    "process_options": {
      "rewrite_profile": "zh_tech_blog"
    },
    "publish_options": {
      "targets": ["blog"]
    }
  }
}
```

## 5. 数据库任务拆解

## 5.1 第一批迁移

### 修改

- 扩展 `content_items`

新增字段建议：

- `source_account`
- `language`
- `summary`
- `rewritten_title`
- `rewritten_content`
- `tags_json`
- `score`
- `review_status`
- `reviewed_at`
- `digest_included`

### 新增表

1. `source_subscriptions`
2. `filter_rules`
3. `rewrite_profiles`
4. `review_queue`
5. `digest_reports`
6. `publish_records`

## 5.2 第二批迁移

待 MVP 稳定后再拆：

1. `content_assets`
2. `content_labels`
3. `content_events`

## 6. 页面任务拆解

## 6.1 信源中心

最小能力：

1. 列表页
2. 新增信源
3. 启停信源
4. 手动触发抓取

## 6.2 内容工作台

最小能力：

1. 抓取结果列表
2. 过滤结果状态
3. AI 处理状态
4. 查看摘要与改写结果

## 6.3 审核台

最小能力：

1. 待审核列表
2. 原文/摘要/改写稿三栏查看
3. 通过/驳回/归档
4. 编辑最终稿后通过

## 6.4 日报页

最小能力：

1. 查看最新日报
2. 手动重生成
3. 下载 Markdown

## 7. 配置项任务拆解

需要新增或整理 `.env.example` / 配置模型的变量：

```env
CONTENT_HUB_ENABLE_DIGEST=true
CONTENT_HUB_DEFAULT_REWRITE_PROFILE=zh_tech_blog
CONTENT_HUB_DIGEST_OUTPUT_DIR=.tmp/digests
CONTENT_HUB_REVIEW_REQUIRED=true
CONTENT_HUB_FILTER_KEYWORDS=agent,rag,llm,openai
CONTENT_HUB_FILTER_EXCLUDE_KEYWORDS=ad,job,spam
CONTENT_HUB_GITHUB_TRENDING_ENABLED=true
CONTENT_HUB_REDDIT_ENABLED=true
```

## 8. 测试任务拆解

## 8.1 单元测试

1. RSS 解析和时间过滤。
2. GitHub Trending 抓取结果标准化。
3. Reddit 抓取结果标准化。
4. 去重规则。
5. 关键词过滤规则。
6. 摘要处理器输出。
7. 改写处理器降级策略。
8. Markdown 日报生成器。

## 8.2 集成测试

1. `radar_pipeline` 从抓取到审核入队。
2. 审核通过后博客草稿发布。
3. `daily_digest_pipeline` 生成日报记录。
4. 重复内容不会重复发布。

## 8.3 API 测试

1. 信源 CRUD。
2. 审核队列查询与操作。
3. 日报生成与查看。
4. 内部任务触发接口。

## 9. 开发顺序

建议按以下顺序实施：

1. 数据模型与迁移。
2. `fetcher_engine` 多信源抓取统一化。
3. `ai_processor` 摘要/分类/改写处理链。
4. `workflow_engine` 串联 radar pipeline。
5. `platform` 审核队列与信源管理 API。
6. `publisher_engine` 博客草稿与日报 Markdown。
7. `scheduler_center` 定时触发。
8. 前端最小页面。
9. 集成测试补齐。

## 10. 里程碑验收

### M1：抓取闭环

完成标准：

1. 可配置至少 3 个信源。
2. 抓取结果统一入库。
3. 支持去重和关键词过滤。

### M2：AI 处理闭环

完成标准：

1. 可生成摘要。
2. 可生成中文改写稿。
3. 处理失败有明确降级。

### M3：审核闭环

完成标准：

1. 控制台可查看待审核内容。
2. 可通过、驳回、归档。
3. 可编辑最终稿。

### M4：发布闭环

完成标准：

1. 审核通过后可生成博客草稿。
2. 可生成日报 Markdown。
3. 可查看发布结果记录。

### M5：调度闭环

完成标准：

1. 每天 09:00 自动运行。
2. 可查看运行状态和错误信息。
3. 重跑不会重复发布同一条内容。

## 11. 结论

MVP 不需要把所有构想一起实现。当前最合理的交付顺序是先做“内容雷达”主链路，再把“日报生成”作为并行输出。

这会直接验证三件核心事情：

1. 信源抓取是否稳定。
2. AI 处理是否有内容价值。
3. 审核后发布是否真正节省运营时间。
