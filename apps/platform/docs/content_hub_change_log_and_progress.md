# Content Hub 改动与进度记录

## 1. 目的

本文件记录本轮改造已经修改了什么、当前进度到哪里、下一步准备做什么。

更新原则：

1. 记录真实已落库/已落代码的内容
2. 不把“计划中”写成“已完成”
3. 后续每推进一阶段继续追加

## 2. 当前总进度

当前阶段目标：

`CNBlogs / Bilibili -> AI Rewrite -> Blog Draft Publish`

总体进度判断：

- 架构蓝图：已完成
- 风险与依赖记录：已完成
- 最小内容模型：已完成
- 新引擎目录骨架：已完成
- 采集桥接：已完成
- AI 改写桥接：已完成
- 草稿发布桥接：已完成
- `content_items` 状态回写：已完成
- `scheduler_center` 接线性 pipeline：已完成基础接入
- 真实闭环联调：未完成

## 3. 已修改内容

### 3.1 文档

新增：

- [content_hub_target_architecture.md](/D:/Python/content_hub/apps/platform/docs/content_hub_target_architecture.md)
- [content_hub_risks_and_dependencies.md](/D:/Python/content_hub/apps/platform/docs/content_hub_risks_and_dependencies.md)
- [content_hub_change_log_and_progress.md](/D:/Python/content_hub/apps/platform/docs/content_hub_change_log_and_progress.md)

作用：

- 目标架构蓝图
- 风险、依赖、外部参数清单
- 本文件：改动与进度持续记录

### 3.2 数据模型与迁移

修改：

- [models.py](/D:/Python/content_hub/apps/platform/models.py)

新增：

- [f3a1c2d4e5f6_add_content_items.py](/D:/Python/content_hub/apps/platform/migrations/versions/f3a1c2d4e5f6_add_content_items.py)

内容：

- 新增 `ContentItem`
- 新增 `content_items` 表
- 增加唯一键：`source_type + source_id`
- 增加 `pipeline_status` / `publish_status` 等运行态字段

### 3.3 CRUD 层

新增：

- [crud_content_item.py](/D:/Python/content_hub/apps/platform/crud/crud_content_item.py)

修改：

- [__init__.py](/D:/Python/content_hub/apps/platform/crud/__init__.py)

内容：

- 新增 `content_items` 的查询、创建、更新操作

### 3.4 新引擎目录骨架

新增目录：

- [apps/fetcher_engine](/D:/Python/content_hub/apps/fetcher_engine)
- [apps/ai_processor](/D:/Python/content_hub/apps/ai_processor)
- [apps/publisher_engine](/D:/Python/content_hub/apps/publisher_engine)
- [apps/workflow_engine](/D:/Python/content_hub/apps/workflow_engine)

内容：

- 基础包结构
- runtime / connectors / processors / adapters / registry / pipeline

### 3.5 工作流契约与注册表

新增：

- [contracts.py](/D:/Python/content_hub/apps/workflow_engine/registry/contracts.py)
- [plugin_registry.py](/D:/Python/content_hub/apps/workflow_engine/registry/plugin_registry.py)
- [static_registry.py](/D:/Python/content_hub/apps/workflow_engine/registry/static_registry.py)
- [settings.py](/D:/Python/content_hub/apps/workflow_engine/registry/settings.py)
- [bootstrap.py](/D:/Python/content_hub/apps/workflow_engine/registry/bootstrap.py)

内容：

- `Fetcher / Processor / Publisher`
- `SourceItem / ContentAsset / PublishResult`
- `AIProcessorConfig`
- 静态注册表
- 默认注册入口

### 3.6 采集器接入

新增或修改：

- [base.py](/D:/Python/content_hub/apps/fetcher_engine/runtime/base.py)
- [fetcher.py](/D:/Python/content_hub/apps/fetcher_engine/connectors/cnblogs/fetcher.py)
- [fetcher.py](/D:/Python/content_hub/apps/fetcher_engine/connectors/bilibili/fetcher.py)

内容：

- `CNBlogsFetcher` 复用 `ado_repost` RSS 适配器
- `BilibiliFetcher` 复用 `ado_repost` RSS 适配器

### 3.7 AI 改写接入

新增或修改：

- [base.py](/D:/Python/content_hub/apps/ai_processor/runtime/base.py)
- [processor.py](/D:/Python/content_hub/apps/ai_processor/processors/rewrite/processor.py)

内容：

- 接入现有 `llm_client.py`
- 支持 `local / openai / anthropic` 配置路径
- 支持 `skip / raw / retry` 降级策略

### 3.8 发布器接入

新增或修改：

- [base.py](/D:/Python/content_hub/apps/publisher_engine/runtime/base.py)
- [settings.py](/D:/Python/content_hub/apps/publisher_engine/runtime/settings.py)
- [publisher.py](/D:/Python/content_hub/apps/publisher_engine/adapters/blog/publisher.py)

内容：

- 复用 `ado_repost` draft publishing client
- 当前目标是 platform 内部草稿接口
- disabled 模式安全返回，不误发请求

### 3.9 线性流水线

新增或修改：

- [linear_pipeline.py](/D:/Python/content_hub/apps/workflow_engine/pipeline/linear_pipeline.py)
- [payloads.py](/D:/Python/content_hub/apps/workflow_engine/pipeline/payloads.py)
- [content_repository.py](/D:/Python/content_hub/apps/workflow_engine/runtime/content_repository.py)
- [legacy_paths.py](/D:/Python/content_hub/apps/workflow_engine/runtime/legacy_paths.py)

内容：

- `fetch -> process -> publish`
- 调度 payload 解析
- 抓取/处理/发布状态写回 `content_items`
- 兼容旧目录的桥接导入

### 3.10 调度中心接入

修改：

- [dispatcher.py](/D:/Python/content_hub/apps/platform/scheduler_center/dispatcher.py)
- [__init__.py](/D:/Python/content_hub/apps/platform/scheduler_center/__init__.py)

内容：

- 新增 `content.pipeline.linear` 本地执行分支
- 遇到该任务类型时不再走远端 agent HTTP
- 直接在调度进程内运行 `LinearPipelineRunner`
- 对 `platform` 标准库冲突增加调度侧导入修复

## 4. 已补测试

新增：

- [test_content_pipeline_contracts.py](/D:/Python/content_hub/apps/platform/tests/test_content_pipeline_contracts.py)
- [test_content_item_crud.py](/D:/Python/content_hub/apps/platform/tests/test_content_item_crud.py)
- [test_registry_bootstrap.py](/D:/Python/content_hub/apps/workflow_engine/tests/test_registry_bootstrap.py)
- [test_linear_pipeline_payload.py](/D:/Python/content_hub/apps/workflow_engine/tests/test_linear_pipeline_payload.py)
- [test_blog_publisher.py](/D:/Python/content_hub/apps/publisher_engine/tests/test_blog_publisher.py)

当前验证过的点：

- `content_items` 建表
- `content_items` CRUD
- registry bootstrap
- linear payload 解析
- blog publisher disabled 模式
- scheduler dispatcher 可导入并识别本地 pipeline 分支

## 5. 当前仍未完成的事项

### 高优先级

1. 提交一个真实的 `content.pipeline.linear` 调度任务并跑通
2. 将抓取结果真正写入数据库后查看内容是否正确
3. 验证 AI 改写后 `processed_content` 是否落库
4. 验证发布成功后 `publish_status` 是否更新

### 中优先级

1. 用真实 feed URL 替换默认占位值
2. 用真实 LLM API 跑一轮改写
3. 把调度入口包装成更易调用的内部 API

### 低优先级

1. 把旧桥接实现逐步迁出
2. 彻底消除 `apps/platform` 命名冲突
3. 逐步迁往 `apps/web_console`

## 6. 当前阻塞

最主要的阻塞已经从“代码没有”变成“外部参数还没定”：

1. 博客园真实 feed URL
2. B 站真实 feed URL / UP 主 ID
3. 真实 LLM API key
4. 真实 LLM base URL
5. 真实模型名
6. 是否继续先投递到 platform 草稿箱

## 7. 下一步建议

最合理的下一步：

1. 新增一个内部触发入口，专门提交 `content.pipeline.linear`
2. 用一组固定测试 payload 跑一次调度任务
3. 读回 `scheduler_tasks` 和 `content_items` 验证全链路结果

## 8. 本次阶段补充

本阶段新增：

- 内部触发入口 `/api/internal/tasks/content-pipeline/linear/run`
- 对应 schema 文件 [pipeline.py](/D:/Python/content_hub/apps/platform/schemas/pipeline.py)
- `schemas/__init__.py` 已导出线性 pipeline 请求模型
- `routers/internal_tasks.py` 已支持提交 `content.pipeline.linear`

新增验证：

- 新 pipeline schema 可导入
- internal task 路由可导入新的 linear pipeline 触发入口

当前推荐的实际联调入口：

- 通过 `/api/internal/tasks/content-pipeline/linear/run` 提交一条任务
- 然后查询 scheduler task 状态
- 再检查 `content_items` 表中的状态变化

## 9. 本次阶段结论

到当前为止，已经不是“架构讨论阶段”，而是“闭环联调前阶段”。

也就是说：

- 蓝图有了
- 风险记账有了
- 数据模型有了
- 三类引擎骨架有了
- 调度接线也有了

现在差的是一轮真实任务执行验证。
