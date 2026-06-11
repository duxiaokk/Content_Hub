# T003: rss_fetcher_stable — RSS 抓取器稳定化 + feed 元数据回写

## 目标（一句话）
基于现有 RssFeedAdapter 代码进行稳定化增强，使其对接 FetchService 统一接口，并支持 feed 元数据回写 source_subscriptions 表。

## 依赖
- 前置任务：T002（FetchService + 注册表已完成）
- 阻塞项：无

## 输入文件（请先阅读）
- RSS 抓取器：[apps/fetcher_engine/runtime/rss.py](file:///D:/Python/content_hub/apps/fetcher_engine/runtime/rss.py)（含 `RssFeedAdapter` / `parse_rss_items` / `UnifiedPost` / `FetchBatch`）
- FetchService 注册表：`apps/fetcher_engine/api/registry.py`（T002 产出）
- 契约模型：`apps/fetcher_engine/api/models.py`（T002 产出）
- 任务清单：`content_hub_mvp_task_breakdown.md` 第 4.1 节第 2 项

## 输出要求（具体、可检查）

### 1. RSS 抓取器适配
在 `apps/fetcher_engine/connectors/` 下不新建目录，直接在 [apps/fetcher_engine/runtime/rss.py](file:///D:/Python/content_hub/apps/fetcher_engine/runtime/rss.py) 中重构或新建 `apps/fetcher_engine/connectors/rss/fetcher.py`（新建）：

```python
class RssFetcher:
    """实现 FetchService 可调用的接口"""
    source_type = "rss"

    def __init__(self, feed_url: str, source_name: str):
        self.adapter = RssFeedAdapter(source=source_name, adapter_name="rss", feed_url=feed_url, stream_key=source_name)

    async def fetch(self, lookback_hours: int = 24, limit: int = 20) -> FetchBatch:
        ...
```

在 `apps/fetcher_engine/api/registry.py` 中注册：
```python
register_fetcher("rss", lambda cfg: RssFetcher(feed_url=cfg.feed_url, source_name=cfg.source_name))
```

### 2. feed 元数据回写
每次抓取完成后，回写 `source_subscriptions` 表：
- `last_cursor`：最近一次抓取到的最后一条内容的时间戳或 external_id
- 可在 FetchService 层调用 `source_repo.update_cursor(source_id, cursor_value)` 实现

### 3. 异常处理增强
- HTTP 超时：设置 30s 超时，超时记录到 error 而非崩溃
- XML 解析异常：捕获 `ParseError`，记录错误信源名和原始 URL
- 空 feed 响应：返回空列表不报错
- 所有异常不向调用方抛出，统一走 `FetchBatchResult.errors`

### 4. 时间过滤增强
- `within_lookback()` 逻辑保留
- 额外增加 `limit` 截断（取前 N 条最新的）

## 验收标准（必须全部勾选才算完成）
- [ ] RSS 抓取器在 FetchService 中注册成功，可通过 `source_type="rss"` 调度
- [ ] 抓取完成后 `source_subscriptions.last_cursor` 被正确更新
- [ ] HTTP 超时时不抛出异常，记录在 FetchBatchResult.errors
- [ ] XML 格式错误时不抛出异常，记录在 FetchBatchResult.errors
- [ ] 空 feed 返回 0 条 items，不报错
- [ ] lookback 和 limit 两种截断均生效
- [ ] 更新 [codex_board.md](file:///D:/Python/content_hub/codex_board.md) 标记 T003 为完成
