# T008: ai_summarize_classify_tag — AI Processor：摘要/分类/标签处理器

## 目标（一句话）
在 AI Processor 中新增摘要（summarize）、分类（classify）和标签（tag）三个处理器，支持分层处理策略：先规则过滤，再轻量 AI 处理，最终只对高价值内容做完整改写。

## 依赖
- 前置任务：T007（增量控制完成，抓取链路可产出 content_items）
- 阻塞项：依赖 LLM 配置（[apps/platform/.env.example](file:///D:/Python/content_hub/apps/platform/.env.example) 中的 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`）

## 输入文件（请先阅读）
- 现有 rewrite processor：[apps/ai_processor/processors/rewrite/processor.py](file:///D:/Python/content_hub/apps/ai_processor/processors/rewrite/processor.py)
- LLM client：[apps/ai_processor/runtime/llm_client.py](file:///D:/Python/content_hub/apps/ai_processor/runtime/llm_client.py)
- AI settings：[apps/ai_processor/runtime/settings.py](file:///D:/Python/content_hub/apps/ai_processor/runtime/settings.py)
- Base processor：[apps/ai_processor/runtime/base.py](file:///D:/Python/content_hub/apps/ai_processor/runtime/base.py)
- Workflow contracts：[apps/workflow_engine/registry/contracts.py](file:///D:/Python/content_hub/apps/workflow_engine/registry/contracts.py)（ProcessResult / ProcessContext 定义）
- 架构文档：`content_hub_product_architecture.md` 第 10 节（AI 处理策略）
- 任务清单：`content_hub_mvp_task_breakdown.md` 第 4.3 节第 2-4 项

## 输出要求（具体、可检查）

### 1. 新增摘要处理器
新建 `apps/ai_processor/processors/summarize/processor.py`：

```python
class SummarizeProcessor:
    name = "summarize"

    async def process(self, content: ContentAsset, context: ProcessContext) -> ProcessResult:
        """对 content.raw_content 生成中文摘要（≤200字）"""
        ...
```

要求：
- 调用 LLM，使用中文 prompt。
- 输出摘要存到 `ProcessResult.content.metadata["summary"]`。
- 失败时 fallback：取 raw_content 前 200 字符作为摘要。
- 记录 token 消耗到 `ProcessResult.cost_tokens`。

### 2. 新增分类处理器
新建 `apps/ai_processor/processors/classify/processor.py`：

```python
class ClassifyProcessor:
    name = "classify"

    async def process(self, content: ContentAsset, context: ProcessContext) -> ProcessResult:
        """分类主题：AI/LLM | 前端 | 后端 | DevOps | 安全 | 其他"""
        ...
```

要求：
- 基于标题 + 摘要判断技术领域。
- 输出分类存到 `ProcessResult.content.metadata["category"]`。
- 支持规则优先：标题含 "LLM"/"Agent"/"RAG" 直接分类为 "AI/LLM"。
- 规则未命中再调 LLM。

### 3. 新增标签处理器
新建 `apps/ai_processor/processors/tag/processor.py`：

```python
class TagProcessor:
    name = "tag"

    async def process(self, content: ContentAsset, context: ProcessContext) -> ProcessResult:
        """提取 3-5 个技术标签，如 ["Python", "FastAPI", "Agent"]"""
        ...
```

要求：
- 基于标题 + 摘要生成标签列表。
- 输出标签存到 `ProcessResult.content.metadata["tags"]`（list of str）。
- 规则兜底：如标题含 "Python"、"Go" 等常见技术词可直接命中。

### 4. 回写 content_items 字段
处理完成后，将结果回写到 `content_items` 表：
- `content_items.summary` = 摘要文本
- `content_items.tags_json` = JSON 标签列表
- `content_items.score` = 质量评分（基于 LLM 输出或规则估算）
- `content_items.pipeline_status` = `"processed"`

### 5. 处理顺序
```text
规则过滤（已完成在上游）
  → summarize（轻量 AI）
  → classify（规则 + 轻量 AI）
  → tag（规则 + 轻量 AI）
  → 写入 content_items 字段
  → 仅高分内容进入 T009 rewrite
```

## 验收标准（必须全部勾选才算完成）
- [ ] `SummarizeProcessor.process()` 返回包含 `summary` 的 ProcessResult
- [ ] `ClassifyProcessor.process()` 返回包含 `category` 的 ProcessResult
- [ ] `TagProcessor.process()` 返回包含 `tags` 的 ProcessResult
- [ ] 三个处理器在 LLM 不可用时均有 fallback 策略（不崩溃）
- [ ] token 消耗记录在 `ProcessResult.cost_tokens` 中
- [ ] 处理结果正确回写到 `content_items`（summary/tags_json/score/pipeline_status）
- [ ] 更新 [codex_board.md](file:///D:/Python/content_hub/codex_board.md) 标记 T008 为完成
