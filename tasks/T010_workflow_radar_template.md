# T010: workflow_radar_template — Workflow Engine：radar_pipeline 节点定义

## 目标（一句话）
在 workflow_engine 中定义 `radar_pipeline` 工作流模板，串联 fetch → dedup_filter → summarize → classify_tag → rewrite → review_prepare 六个标准节点。

## 依赖
- 前置任务：T009（AI 处理器链完成）、T001（数据模型完成）
- 阻塞项：无

## 输入文件（请先阅读）
- 现有 linear_pipeline：[apps/workflow_engine/pipeline/linear_pipeline.py](file:///D:/Python/content_hub/apps/workflow_engine/pipeline/linear_pipeline.py)
- Pipeline payloads：[apps/workflow_engine/pipeline/payloads.py](file:///D:/Python/content_hub/apps/workflow_engine/pipeline/payloads.py)
- 现有 contracts：[apps/workflow_engine/registry/contracts.py](file:///D:/Python/content_hub/apps/workflow_engine/registry/contracts.py)（SourceItem / ProcessContext / ProcessResult / PublishResult）
- 注册表：[apps/workflow_engine/registry/static_registry.py](file:///D:/Python/content_hub/apps/workflow_engine/registry/static_registry.py)
- Workflow service：[apps/workflow_engine/api/service.py](file:///D:/Python/content_hub/apps/workflow_engine/api/service.py)
- 架构文档：`content_hub_product_architecture.md` 第 8.2 节（radar_pipeline 步骤）
- 任务清单：`content_hub_mvp_task_breakdown.md` 第 4.2 节

## 输出要求（具体、可检查）

### 1. 扩展 contracts.py 流程节点语义
在 [apps/workflow_engine/registry/contracts.py](file:///D:/Python/content_hub/apps/workflow_engine/registry/contracts.py) 中扩展：

```python
PipelineStage = Literal["fetch", "filter", "process", "review_prepare", "publish", "digest_generate"]
```

新增数据模型：

```python
@dataclass(slots=True)
class FilterResult:
    items: list[ContentAsset]
    filtered_out: list[dict]       # 被过滤掉的条目及原因
    stats: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class ReviewItem:
    content_item_id: int
    title: str
    original_url: str
    summary: str | None = None
    rewritten_title: str | None = None
    rewritten_content: str | None = None
    score: float = 0.0
    tags: list[str] = field(default_factory=list)
    category: str | None = None
    status: str = "pending"

@dataclass(slots=True)
class DigestResult:
    digest_id: int
    title: str
    items_count: int
    markdown_content: str
    generated_at: str
```

### 2. 新增 filter_rules 过滤节点
在 `apps/workflow_engine/pipeline/` 新建 `filter_node.py`：

```python
class FilterNode:
    """关键词白/黑名单过滤 + 去重"""

    async def apply(self, items: list[dict], filter_config: dict) -> FilterResult:
        ...
```

规则来源：
1. `filter_rules` 表（`rule_type=keyword_include` / `keyword_exclude` / `dedup`）。
2. `.env` 中的 `CONTENT_HUB_FILTER_KEYWORDS` / `CONTENT_HUB_FILTER_EXCLUDE_KEYWORDS`（fallback）。

### 3. 新增 radar_pipeline 模板定义
在 `apps/workflow_engine/registry/static_registry.py` 中注册：

```python
RADAR_PIPELINE_STEPS = [
    {"name": "fetch", "handler": "fecher_engine.FetchService.run_sources"},
    {"name": "dedup_filter", "handler": "workflow_engine.pipeline.filter_node.FilterNode.apply"},
    {"name": "summarize", "handler": "ai_processor.processors.summarize.SummarizeProcessor.process"},
    {"name": "classify_tag", "handler": "ai_processor.processors.classify.ClassifyProcessor.process"},
    {"name": "rewrite", "handler": "ai_processor.processors.rewrite.RewriteProcessor.process"},
    {"name": "review_prepare", "handler": "platform.services.review_service.prepare_review_queue"},
]
```

### 4. 扩展 WorkflowService
在 [apps/workflow_engine/api/service.py](file:///D:/Python/content_hub/apps/workflow_engine/api/service.py) 中新增：

```python
async def run_radar_pipeline(self, request: RadarPipelineRequest) -> dict[str, Any]:
    """按 RADAR_PIPELINE_STEPS 顺序执行"""
    ...
```

## 验收标准（必须全部勾选才算完成）
- [ ] `from apps.workflow_engine.registry.contracts import FilterResult, ReviewItem, DigestResult` 导入成功
- [ ] `FilterNode.apply()` 可按 `filter_rules` 表规则过滤（白名单/黑名单/去重）
- [ ] `RADAR_PIPELINE_STEPS` 在 static_registry 中注册，6 个节点齐全
- [ ] `WorkflowService.run_radar_pipeline()` 从 fetch 到 review_prepare 全程走通
- [ ] 某节点失败时，pipeline 记录错误后跳过或终止（可配置）
- [ ] 更新 [codex_board.md](file:///D:/Python/content_hub/codex_board.md) 标记 T010 为完成
