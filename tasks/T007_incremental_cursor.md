# T007: incremental_cursor — 增量控制 + 失败容错

## 目标（一句话）
为所有抓取器增加统一的增量抓取控制和失败容错机制，确保每次只抓新内容且单信源失败不阻断整体流程。

## 依赖
- 前置任务：T003（RSS 稳定化）、T004（GitHub Trending）、T005（Reddit）、T006（CNBlogs/Bilibili 补齐）
- 阻塞项：无

## 输入文件（请先阅读）
- FetchService：[apps/fetcher_engine/api/service.py](file:///D:/Python/content_hub/apps/fetcher_engine/api/service.py)（T002 产出）
- RSS 抓取器：[apps/fetcher_engine/runtime/rss.py](file:///D:/Python/content_hub/apps/fetcher_engine/runtime/rss.py)
- 数据库模型：`source_subscriptions.last_cursor`（T001 产出）
- shared_memory：[libs/shared_memory/src/shared_memory/pool.py](file:///D:/Python/content_hub/libs/shared_memory/src/shared_memory/pool.py)
- 任务清单：`content_hub_mvp_task_breakdown.md` 第 4.1 节第 6、7 项

## 输出要求（具体、可检查）

### 1. 增量抓取控制
在 FetchService 中实现增量逻辑：

**cursor 策略**：
- 每次抓取后，更新 `source_subscriptions.last_cursor` 为本次抓到的最新一条记录的 `external_id` 或 `published_at`。
- 下次抓取时，将 `last_cursor` 传给对应抓取器，只取 cursor 之后的新内容。
- 对无 cursor 记录的信源（首次抓取），使用 `lookback_hours` 截断。

**Cursor 存储**：
- 复用 `source_subscriptions.last_cursor`（VARCHAR，存储 JSON 如 `{"external_id": "xxx", "fetched_at": "2025-06-01T12:00:00Z"}`）。
- 在 FetchService 中新增 `_update_cursor(source_id: int, cursor_value: dict)` 方法。

### 2. 去重增强
在 FetchService 入库前：
1. 按 `(source_type, external_id)` 查 `content_items` 是否已存在。
2. 已存在的跳过（计数到 `deduped`）。
3. 不存在的插入。

### 3. 失败容错增强
在 FetchService 的 `run_sources()` 中：
1. 外层 `try/except` 包裹每个信源调用。
2. 失败时记录 `{"source": source_type, "error": str(e), "traceback": ...}` 到 `FetchBatchResult.errors`。
3. 继续处理下一个信源，不抛异常。
4. 最终 stats 中统计 `sources_succeeded` / `sources_failed`。

### 4. 日志与监控
- 每次抓取记录 `run_id`、信源名、耗时、结果数量。
- 失败时记录完整 error + traceback 到应用日志。

## 验收标准（必须全部勾选才算完成）
- [ ] 同一信源连续两次抓取，第二次不产生重复 content_items
- [ ] `source_subscriptions.last_cursor` 在抓取后正确更新
- [ ] 首次抓取（无 cursor）正常使用 lookback_hours 截断
- [ ] 模拟一个信源失败（如错误 URL），其他信源仍正常完成
- [ ] `FetchBatchResult.errors` 包含失败信源的详细信息
- [ ] `FetchBatchResult.stats` 包含 `sources_succeeded` / `sources_failed`
- [ ] 更新 [codex_board.md](file:///D:/Python/content_hub/codex_board.md) 标记 T007 为完成
