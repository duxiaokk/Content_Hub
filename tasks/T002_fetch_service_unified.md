# T002: fetch_service_unified — 统一入口 FetchService + Pydantic 模型

## 目标（一句话）
在 `fetcher_engine` 中新增统一抓取服务层 `FetchService`，提供按信源订阅批量调度抓取器的能力，输出统一的 Pydantic 契约模型。

## 依赖
- 前置任务：T001（依赖 `content_items` 新字段 + `source_subscriptions` 表）
- 阻塞项：无

## 输入文件（请先阅读）
- 现有 RSS 抓取器：[apps/fetcher_engine/runtime/rss.py](file:///D:/Python/content_hub/apps/fetcher_engine/runtime/rss.py)（`UnifiedPost` / `RssFeedAdapter` / `FetchBatch` 已有定义）
- 现有 base：[apps/fetcher_engine/runtime/base.py](file:///D:/Python/content_hub/apps/fetcher_engine/runtime/base.py)
- 现有 connector 示例：[apps/fetcher_engine/connectors/cnblogs/fetcher.py](file:///D:/Python/content_hub/apps/fetcher_engine/connectors/cnblogs/fetcher.py)
- Workflow contracts：[apps/workflow_engine/registry/contracts.py](file:///D:/Python/content_hub/apps/workflow_engine/registry/contracts.py)（了解 SourceItem / FetchRequest 契约）
- 任务清单：`content_hub_mvp_task_breakdown.md` 第 4.1 节

## 输出要求（具体、可检查）

### 1. 新增 Pydantic 契约模型
在 `apps/fetcher_engine/api/models.py`（新建）中定义：

```python
class FetchBatchRequest(BaseModel):
    run_id: str
    sources: list[str]           # source_type 列表
    lookback_hours: int = 24
    limit_per_source: int = 20
    options: dict[str, Any] = {}

class FetchBatchResult(BaseModel):
    run_id: str
    items: list[dict]            # UnifiedPost 标准化字典列表
    errors: list[dict]           # {source, error, traceback}
    stats: dict[str, Any]        # {total_fetched, total_inserted, total_deduped}
```

### 2. 新增 `FetchService`
在 `apps/fetcher_engine/api/service.py`（新建）中实现：

```python
class FetchService:
    def __init__(self, db_session, source_repo):
        ...

    async def run_sources(self, request: FetchBatchRequest) -> FetchBatchResult:
        """按 sources 列表逐个调度抓取器，单个失败不阻塞批次"""
        ...
```

核心逻辑：
1. 从 `source_subscriptions` 表读取 enabled 的信源配置。
2. 按 `request.sources` 过滤（若为空则取全部）。
3. 对每个信源调用对应抓取器（RSS / CNBlogs / Bilibili 等）。
4. 单个信源失败时记录 error 到 `FetchBatchResult.errors`，继续下一个。
5. 所有结果去重（按 `external_id` + `source_type`），通过 `content_items` 表 dedup_key 判重。
6. 将新内容写入 `content_items` 表，回写 `FetchBatchResult.stats`。

### 3. 抓取器注册表
在 `apps/fetcher_engine/api/registry.py`（新建）中实现简单的抓取器注册/查找：

```python
FETCHER_REGISTRY: dict[str, Callable] = {}   # key: source_type, value: fetcher class/factory

def register_fetcher(source_type: str, fetcher_factory):
    ...

def get_fetcher(source_type: str):
    ...
```

## 验收标准（必须全部勾选才算完成）
- [ ] `from apps.fetcher_engine.api.models import FetchBatchRequest, FetchBatchResult` 导入成功
- [ ] `FetchService.run_sources()` 对单信源可正确抓取并入库
- [ ] 多信源批量抓取时，一个信源失败不阻断其余信源
- [ ] 重复 `external_id` 不会重复插入 content_items
- [ ] `FetchBatchResult.errors` 中包含失败信源的 error 信息
- [ ] `FetchBatchResult.stats` 包含 `total_fetched` / `total_inserted` / `total_deduped`
- [ ] 更新 [codex_board.md](file:///D:/Python/content_hub/codex_board.md) 标记 T002 为完成
