# Content Hub 风险与外部依赖清单

## 1. 目的

本文件记录当前改造阶段所有已知风险、外部依赖、关键配置项、待确认参数和运行前提。

作用：

1. 避免后续推进时遗漏阻塞项
2. 明确哪些值必须由人工提供
3. 区分“代码已就绪”和“外部条件未满足”

## 2. 当前阶段目标

当前目标不是完整三层中台，而是先跑通这一条闭环：

`CNBlogs / Bilibili -> AI Rewrite -> Blog Draft Publish`

所以本文只记录和这条主链路直接相关的风险和依赖。

## 3. 已知架构风险

### 3.1 `apps/platform` 与 Python 标准库 `platform` 冲突

风险等级：高

现象：

- 当 `apps` 被加入 `sys.path` 前部时，`import platform` 可能误命中 `apps/platform`
- 会连带影响 `sqlalchemy`、`httpx`、`attr` 等依赖导入

当前状态：

- 已在 [legacy_paths.py](/D:/Python/content_hub/apps/workflow_engine/runtime/legacy_paths.py) 做临时兜底
- 该兜底只能算桥接措施，不是长期解法

建议：

- 尽快将 `apps/platform` 迁移为 `apps/web_console`

### 3.2 现有代码仍处于“桥接旧实现”状态

风险等级：中高

现象：

- `fetcher_engine` 复用了 `ado_repost`
- `rewrite processor` 复用了 `platform/services/llm_client.py`
- `publisher_engine` 将复用 `ado_repost/publishing`

影响：

- 旧目录和新目录会并存一段时间
- 一旦旧实现行为变化，桥接层也会受影响

建议：

- 第一阶段允许桥接
- 第二阶段再逐步把抓取、AI、发布完全迁到新引擎目录

### 3.3 工作流目前仅支持线性流水线

风险等级：中

现状：

- 只支持 `fetch -> process -> publish`

影响：

- 暂时不支持条件分支、人工审核节点、并行抓取合流

建议：

- 先用这条闭环验证业务可行性，不提前扩展 DAG

### 3.4 内容模型仍是最小表

风险等级：低中

现状：

- 当前只落一张 `content_items` 表

影响：

- 短期足够
- 后续如果要支持多版本改写、多目标发布、多轮审核，需要扩模型

建议：

- 半年内保持轻量
- 待闭环稳定后再拆 `publication_records` 等从表

## 4. 外部依赖清单

### 4.1 LLM 依赖

当前接入方式：

- 复用 [llm_client.py](/D:/Python/content_hub/apps/platform/services/llm_client.py)
- `openai` / `anthropic` 当前都走 OpenAI-compatible 模式
- `local` 当前走 mock provider

需要配置的项：

- `SECRET_KEY`
- `CONTENT_HUB_LLM_PROVIDER`
- `CONTENT_HUB_LLM_MODEL`
- `CONTENT_HUB_LLM_MAX_TOKENS`
- `CONTENT_HUB_LLM_TIMEOUT_SECONDS`
- `CONTENT_HUB_LLM_FALLBACK`
- `CONTENT_HUB_LLM_COST_TRACKING`
- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `MOCK_LLM`

待确认：

- 你最终要用的 provider 是 `openai`、`anthropic` 还是兼容网关
- 实际模型名称
- 单次最大 token 上限
- 失败时是 `raw` 还是 `retry`

### 4.2 采集源依赖

当前接入方式：

- `CNBlogsFetcher` 先走 RSS
- `BilibiliFetcher` 先走 RSS feed

需要配置的项：

- `CONTENT_HUB_CNBLOGS_FEED_URL`
- `CONTENT_HUB_BILIBILI_FEED_URL`

待确认：

- 具体抓哪个博客园博主
- 具体抓哪个 B 站 UP 主
- 对应 feed URL 是否稳定可访问

### 4.3 发布目标依赖

当前接入方式：

- 复用 `ado_repost` 的 draft publishing client
- 目标是 platform 的内部草稿接口

相关代码：

- [client.py](/D:/Python/content_hub/apps/ado_repost/src/ado_repost/publishing/client.py)
- [config.py](/D:/Python/content_hub/apps/ado_repost/src/ado_repost/publishing/config.py)
- [models.py](/D:/Python/content_hub/apps/ado_repost/src/ado_repost/publishing/models.py)

需要配置的项：

- `ADO_PUBLISH_ENABLED`
- `ADO_PUBLISH_ENDPOINT_URL`
- `ADO_INTERNAL_TOKEN`
- `ADO_PUBLISH_TIMEOUT_SECONDS`
- `ADO_SOURCE_PLATFORM`

默认目标接口：

- `http://127.0.0.1:8000/api/internal/agent/drafts`

待确认：

- 当前是否继续先发布到 platform 草稿箱
- 还是要直接发布到真实博客 API

## 5. 关键 URL / ID / 参数记录

### 5.1 当前代码默认值

#### CNBlogs

- 默认 feed URL:
  `https://feed.cnblogs.com/blog/u/126286/rss`

说明：

- 这是占位默认值
- 需要替换成你的目标博客园博主 feed

#### Bilibili

- 默认 feed URL:
  `https://rsshub.app/bilibili/user/video/2267573`

说明：

- 当前通过 RSSHub 形式占位
- `2267573` 是当前默认占位 UP 主 ID
- 需要替换成你的目标 UP 主 ID 或你自己的 RSS 代理地址

#### YouTube

现有 `ado_repost` 默认值仍存在：

- channel id:
  `UCln9P4Qm3-EAY4aiEPmRwEA`

说明：

- 当前阶段主链路未使用
- 但旧抓取逻辑中仍保留该默认值

#### 发布接口

- platform internal draft endpoint:
  `http://127.0.0.1:8000/api/internal/agent/drafts`

### 5.2 必须由你确认或提供的值

以下值必须最终确认，否则只能停留在“能跑样例”：

1. 博客园目标博主 feed URL
2. B 站目标 UP 主 ID 或 feed URL
3. LLM provider
4. LLM model
5. LLM API key
6. LLM base URL
7. 发布目标是 platform 草稿箱还是真实博客 API
8. 如果是真实博客 API，对应 endpoint、token、字段格式

## 6. 当前代码状态清单

### 已完成

- `content_items` 最小模型已落库
- `Fetcher / Processor / Publisher / PluginRegistry` 已建
- `CNBlogsFetcher` 已接 RSS 适配器
- `BilibiliFetcher` 已接 RSS 适配器
- `RewriteProcessor` 已接 LLM client
- `LinearPipelineRunner` 已就位
- `scheduler_center` 已接 `content.pipeline.linear` 基础执行分支

### 进行中

- 调度任务真实闭环联调

### 未完成

- 真实配置文件落地
- 抓取结果写回 `content_items`
- 发布结果回写 `content_items`
- 真实博客 API 发布

## 7. 当前阶段建议的环境变量模板

```env
SECRET_KEY=replace-with-real-secret

CONTENT_HUB_CNBLOGS_FEED_URL=https://feed.cnblogs.com/blog/u/<your-id>/rss
CONTENT_HUB_BILIBILI_FEED_URL=https://rsshub.app/bilibili/user/video/<your-up-id>

CONTENT_HUB_LLM_PROVIDER=openai
CONTENT_HUB_LLM_MODEL=gpt-4.1-mini
CONTENT_HUB_LLM_MAX_TOKENS=4000
CONTENT_HUB_LLM_TIMEOUT_SECONDS=60
CONTENT_HUB_LLM_FALLBACK=raw
CONTENT_HUB_LLM_COST_TRACKING=true

LLM_API_KEY=replace-with-real-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4.1-mini
MOCK_LLM=false

ADO_PUBLISH_ENABLED=true
ADO_PUBLISH_ENDPOINT_URL=http://127.0.0.1:8000/api/internal/agent/drafts
ADO_INTERNAL_TOKEN=local-dev-internal-token
ADO_PUBLISH_TIMEOUT_SECONDS=15
ADO_SOURCE_PLATFORM=cnblogs
```

## 8. 阻塞项总结

真正会阻塞闭环验证的，不是代码结构，而是下面这些外部信息：

1. 目标博客园 feed URL
2. 目标 B 站 feed URL / UP 主 ID
3. 可用的 LLM API key
4. 可用的 LLM base URL
5. 最终模型名
6. 发布目标接口是否已经确定

这些值一旦明确，闭环验证就可以往前推进。
