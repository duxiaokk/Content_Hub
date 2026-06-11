# T006: cnblogs_bilibili_fields — CNBlogs/Bilibili 字段补齐

## 目标（一句话）
补齐现有 CNBlogs 和 Bilibili 抓取器的输出字段，使 source_account、发布时间、摘要、链接完整覆盖。

## 依赖
- 前置任务：T002（FetchService + 注册表已完成）
- 阻塞项：无（与 T003/T004/T005 可并行开发）

## 输入文件（请先阅读）
- CNBlogs 抓取器：[apps/fetcher_engine/connectors/cnblogs/fetcher.py](file:///D:/Python/content_hub/apps/fetcher_engine/connectors/cnblogs/fetcher.py)
- Bilibili 抓取器：[apps/fetcher_engine/connectors/bilibili/fetcher.py](file:///D:/Python/content_hub/apps/fetcher_engine/connectors/bilibili/fetcher.py)
- UnifiedPost 定义：[apps/fetcher_engine/runtime/rss.py](file:///D:/Python/content_hub/apps/fetcher_engine/runtime/rss.py)
- FetchService 注册表：`apps/fetcher_engine/api/registry.py`（T002 产出）
- 任务清单：`content_hub_mvp_task_breakdown.md` 第 4.1 节第 5 项

## 输出要求（具体、可检查）

### 1. CNBlogs 抓取器字段补齐
在 [apps/fetcher_engine/connectors/cnblogs/fetcher.py](file:///D:/Python/content_hub/apps/fetcher_engine/connectors/cnblogs/fetcher.py) 中修改：

要求输出中补齐以下字段：
- `source_account`：作者名（从页面中提取作者 link/name）
- `published_at`：发布时间（解析 CNBlogs 的时间格式，如 `2025-06-01 12:00`）
- `summary`：文章摘要或前 300 字正文
- `url`：文章完整 URL（不是 RSS proxy URL）
- `raw`：补充 {author, category, view_count}

### 2. Bilibili 抓取器字段补齐
在 [apps/fetcher_engine/connectors/bilibili/fetcher.py](file:///D:/Python/content_hub/apps/fetcher_engine/connectors/bilibili/fetcher.py) 中修改：

要求输出中补齐以下字段：
- `source_account`：UP 主名称
- `published_at`：视频发布时间
- `summary`：视频简介/描述文字
- `url`：视频页 URL（`https://www.bilibili.com/video/{bvid}`）
- `raw`：补充 {author, play_count, danmaku_count, duration, cover_url}

### 3. 注册到 FetchService
```python
register_fetcher("cnblogs", lambda cfg: CnblogsFetcher(...))
register_fetcher("bilibili", lambda cfg: BilibiliFetcher(...))
```

### 4. 统一输出结构
确保两个抓取器的 `fetch()` 方法返回 `list[UnifiedPost]`（或等价标准结构），与 RSS / GitHub Trending / Reddit 抓取器保持契约一致。

## 验收标准（必须全部勾选才算完成）
- [ ] CNBlogs 抓取器返回的每个 item 包含 `source_account`、`published_at`、`summary`、`url`
- [ ] Bilibili 抓取器返回的每个 item 包含 `source_account`、`published_at`、`summary`、`url`
- [ ] `published_at` 为有效 datetime 对象（非字符串）
- [ ] CNBlogs/Bilibili 均在 FetchService 注册表中注册
- [ ] 更新 [codex_board.md](file:///D:/Python/content_hub/codex_board.md) 标记 T006 为完成
