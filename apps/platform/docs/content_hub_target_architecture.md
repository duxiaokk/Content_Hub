# Content Hub 目标架构与迁移蓝图

## 1. 目标

本文件定义 Content Hub 从“主平台 + 若干业务应用”收敛为“Web 控制台 + 引擎层 + 静态插件注册”的目标结构。

这次改造的核心不是重写全部代码，而是完成四件事：

1. 明确 Web 控制台与业务执行面的边界
2. 抽出采集、AI 处理、发布三类稳定接口
3. 先用线性流水线跑通 `fetch -> process -> publish`
4. 让现有应用以适配器方式接入统一工作流引擎

## 2. 当前阶段目标架构

```text
+------------------------------------------------------+
|                    Web Console                       |
|------------------------------------------------------|
| workflow config | content review | run monitor       |
+------------------------------------------------------+
                         |
                         v
+------------------------------------------------------+
|                  Workflow Engine                     |
|------------------------------------------------------|
| linear pipeline: fetch -> process -> publish         |
+------------------------------------------------------+
         |                      |                     |
         v                      v                     v
+----------------+    +----------------+    +------------------+
| Fetcher Engine |    | AI Processor   |    | Publisher Engine |
+----------------+    +----------------+    +------------------+
         |                                           |
         v                                           v
+--------------------+                    +----------------------+
| Connectors         |                    | Adapters             |
| CNBlogs / Bilibili |                    | Blog publish target  |
+--------------------+                    +----------------------+
```

## 3. 架构原则

### 3.1 Web 控制台

现阶段不要单独做 heavy 的 `apps/control_plane`。

Web 控制台直接承担控制平面职责，只负责“配置、审核、监控、触发”：

- 流水线配置
- 控制台页面与管理 API
- 内容审核
- 运行记录与发布记录
- 调用工作流引擎执行任务

不负责：

- 直接实现采集器
- 直接实现 AI 改写逻辑
- 直接实现发布适配器

### 3.2 工作流引擎

现阶段工作流引擎不做完整 DAG，只支持线性流水线：

`fetch -> process -> publish`

先解决闭环：

- 能配置一次采集
- 能进入 AI 处理
- 能写入发布结果
- 能看到每一步状态

下面这些暂不做或只预留接口：

- 条件分支
- 并行节点
- 动态子图
- 可视化拖拽编排

### 3.3 插件边界

插件只负责“平台能力适配”，不反向侵入工作流引擎：

- 连接器插件实现内容来源接入
- 处理器插件实现内容处理步骤
- 发布适配器实现目标平台投递

插件应通过清晰接口注册到引擎，而不是让 Web 路由层直接 import 业务代码。

### 3.4 注册方式

现阶段不做动态发现。

采用静态注册表 + YAML 配置：

- Python 文件中手动注册 `register_fetcher(...)`
- YAML 决定启用哪些 fetcher / processor / publisher
- 先把可调试性和可控性放在第一位

## 4. 现有仓库到目标架构的映射

| 目标模块 | 当前目录 | 处理方式 |
|---|---|---|
| Workflow Engine | `apps/platform/scheduler_center` | 保留，先收敛为线性流水线执行核心 |
| Web Console | `apps/platform/frontend` + `apps/platform/templates` + `apps/platform/routers/pages.py` | 保留，后续重命名为 `apps/web_console` |
| Content Repository | `apps/platform` 中的数据库模型、CRUD、内容接口 | 先用 SQLite + SQLAlchemy 保持轻量实现 |
| Fetcher Engine | `apps/ado_repost` | 收敛并迁移为 `apps/fetcher_engine` |
| AI Processor Engine | `apps/platform/services/ai_services.py`、`planner_service.py`、部分 agent 逻辑 | 抽出为独立引擎模块 |
| Publisher Engine | `apps/platform/posts/comments/internal tasks` 中散落的发布逻辑 | 收敛为统一发布引擎 |
| Connectors | `ado_repost/src/content_bridge` 中的平台抓取能力 | 继续保留，先跑通博客园和 B 站 |
| Adapters | 当前缺少统一目录 | 新建适配层，先只做博客发布目标 |
| 辅助 Agent | `apps/comment_agent` | 不再作为主链路核心架构名词，改为引擎或审核能力的执行单元 |

## 5. 推荐目标目录

推荐先按“单仓多应用”收敛，不立即拆微服务仓库：

```text
apps/
  web_console/
    api/
    web/
    services/
    repositories/
    models/
    workflow_client/
  workflow_engine/
    api/
    pipeline/
    runtime/
    registry/
  fetcher_engine/
    api/
    runtime/
    connectors/
      cnblogs/
      bilibili/
  ai_processor/
    api/
    runtime/
    processors/
      rewrite/
      enrich/
  publisher_engine/
    api/
    runtime/
    adapters/
      blog/
  comment_agent/
    app/
libs/
  content_contracts/
  workflow_sdk/
  plugin_sdk/
  shared_memory/
infra/
  docs/
  scripts/
```

如果第一阶段不想立即改目录名，可以采用“逻辑重组，物理目录延后迁移”的方式：

- `apps/platform` 暂时视为 `web_console`
- `apps/platform/scheduler_center` 暂时视为 `workflow_engine`
- `apps/ado_repost` 暂时视为 `fetcher_engine`
- `apps/comment_agent` 暂时保留

先改模块职责和接口，再改目录名。

## 6. 模块职责边界

### 6.1 Workflow Engine

只负责：

- 线性流水线定义与解析
- 节点顺序调度
- 重试、超时、依赖控制
- 任务实例状态机
- 统一执行日志

不负责：

- 直接抓内容
- 直接调用 LLM 处理内容
- 直接向外部平台发帖

### 6.2 Web Console

只负责：

- 流水线管理
- 内容审核与人工介入
- 规则配置
- 插件配置
- 运行监控和审计

不负责：

- 直接承载具体连接器逻辑
- 在路由层拼装跨平台业务流程

### 6.3 Content Repository

现阶段不提前设计复杂多版本模型。

SQLite + SQLAlchemy 跑一张主表即可：

- `content_items`

推荐字段先控制在能跑闭环的范围：

- `id`
- `source_type`
- `source_id`
- `source_url`
- `title`
- `raw_content`
- `processed_content`
- `publish_target`
- `publish_status`
- `pipeline_status`
- `error_message`
- `created_at`
- `updated_at`

这张表足够支撑未来半年验证，不要过早上 `ContentVariant` 多版本体系。

### 6.4 Fetcher Engine

输入：

- 数据源配置
- 时间窗口 / 增量游标
- 拉取规则

输出：

- 统一内容入站格式，例如 `SourceItem`

内部职责：

- 平台 API 调用
- 拉取节流
- 增量 cursor 管理
- 原始数据归档
- 标准字段归一化

### 6.5 AI Processor Engine

输入：

- 统一内容对象
- 处理流水线配置

输出：

- 处理后的内容变体
- 处理元数据
- 审核结论 / 风险标签

内部职责：

- 去重
- 翻译
- 摘要
- 改写
- 打标签
- 质量评分

AI 原生配置必须单独建模：

```python
class AIProcessorConfig:
    llm_provider: str  # openai / anthropic / local
    model: str
    max_tokens_per_call: int
    timeout_seconds: int
    fallback_strategy: Literal["skip", "raw", "retry"]
    enable_cost_tracking: bool
```

这几个字段是当前阶段必须项：

- `max_tokens_per_call` 用于成本管控
- `timeout_seconds` 用于任务超时控制
- `fallback_strategy` 用于失败降级
- `enable_cost_tracking` 用于记录 token 消耗

### 6.6 Publisher Engine

输入：

- 待发布内容
- 目标平台配置
- 发布策略

输出：

- 发布结果
- 平台返回 ID
- 发布失败原因
- 回执同步记录

内部职责：

- 草稿/正式发布
- 幂等控制
- 重试与补偿
- 发布状态同步

## 7. 第一阶段接口建议

第一阶段不要追求复杂插件系统，先定义 Python 级别稳定接口。

### 7.1 Fetcher

```python
class Fetcher(Protocol):
    name: str

    async def fetch(self, request: FetchRequest) -> list[SourceItem]:
        ...
```

### 7.2 Processor

```python
class Processor(Protocol):
    name: str

    async def process(self, content: ContentAsset, context: ProcessContext) -> ProcessResult:
        ...
```

### 7.3 Publisher

```python
class Publisher(Protocol):
    name: str

    async def publish(self, content: PublishableContent, target: PublishTarget) -> PublishResult:
        ...
```

### 7.4 Registry

```python
class PluginRegistry:
    def register_fetcher(self, fetcher: Fetcher) -> None: ...
    def register_processor(self, processor: Processor) -> None: ...
    def register_publisher(self, publisher: Publisher) -> None: ...
```

推荐最小实现：

```python
registry = PluginRegistry()
registry.register_fetcher(CNBlogsFetcher())
registry.register_fetcher(BilibiliFetcher())
registry.register_processor(RewriteProcessor())
registry.register_publisher(BlogPublisher())
```

插件启停与参数走 YAML，不做动态发现，不做热加载。

## 8. 推荐迁移顺序

### 阶段 1：边界收敛

目标：

- 明确 `platform`、`scheduler_center`、`ado_repost`、`comment_agent` 的新职责
- 冻结旧的跨层直接调用

动作：

1. 补齐目标架构文档
2. 定义统一内容模型和任务模型
3. 梳理现有路由层直接调用业务实现的位置
4. 增加接口层，禁止新增硬编码平台逻辑进入 `routers/` 和 `pages`

### 阶段 2：工作流收口

目标：

- 所有“采集、处理、发布”动作统一通过工作流节点调度

动作：

1. 扩展 `scheduler_center`，先支持线性 pipeline 节点
2. 把现有 `ado_repost` 执行路径包装为 `fetch` 节点
3. 把现有 AI 逻辑包装为 `process` 节点
4. 把现有发布逻辑包装为 `publish` 节点

### 阶段 3：接口插件化

目标：

- 接入新来源、新目标平台时不改控制平面核心代码

动作：

1. 新建 `connectors/`、`processors/`、`adapters/`
2. 将现有实现迁移到统一接口
3. 建立本地注册表与插件配置
4. 为每类插件补测试基线

### 阶段 4：目录与命名迁移

目标：

- 代码目录与架构命名一致

动作：

1. 将 `apps/ado_repost` 重命名或别名化为 `fetcher_engine`
2. 将 `apps/platform` 逻辑收敛并迁移为 `web_console`
3. 抽出 `ai_processor` 和 `publisher_engine`
4. 将共享契约沉淀到 `libs/`

补充说明：

- `apps/platform` 当前名称会与 Python 标准库 `platform` 冲突
- 因此目录迁移虽然排在第 4 阶段，但这个命名风险需要尽早消除
- 在代码完全迁移前，测试和脚本需要避免把 `apps/platform` 直接放到解释器首位导入路径

## 9. 明确不建议的做法

以下做法会让这次改造失败：

1. 一次性改目录、改协议、改数据库、改部署方式
2. 在没有统一内容表前先做“插件市场 UI”
3. 继续把连接器逻辑直接写进 `platform/services`
4. 让工作流引擎感知具体平台字段
5. 把 `comment_agent`、`ado_repost` 等现有应用全部推倒重写

## 10. 近期可执行任务清单

建议按下面顺序开工：

1. 先定义 `content_items` 最小表结构
2. 再补三类接口定义与静态注册表
3. 把 `ado_repost` 适配成第一个 `Fetcher`
4. 先做 `CNBlogsFetcher` 和 `BilibiliFetcher`
5. 把现有 AI 改写逻辑适配成第一个 `Processor`
6. 把现有博客发布逻辑适配成第一个 `Publisher`
7. 最后让 `scheduler_center` 串起 `fetch -> process -> publish`

## 11. 结论

这次改造是值得做的，但当前目标应该定义为：

“先搭一个两层毛坯房：Web 控制台 + 引擎层，把博客园和 B 站跑通，完成 AI 改写与发布闭环验证。”

正确路径是：

- 先统一边界
- 再统一线性流水线
- 再统一接口
- 最后再统一目录和部署

这样能最大化复用当前仓库已有能力，同时把后续扩展成本降下来。
