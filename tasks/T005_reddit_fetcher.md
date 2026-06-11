# T005: reddit_fetcher — Reddit 抓取器（公开 RSS/JSON）

## 目标（一句话）
新增 Reddit 抓取器，通过 Reddit 公开 RSS 入口抓取指定 subreddit 热帖，输出为 `UnifiedPost` 列表。

## 依赖
- 前置任务：T002（FetchService + 注册表已完成）
- 阻塞项：无（与 T003/T004/T006 可并行开发）

## 输入文件（请先阅读）
- RSS 抓取器参考：[apps/fetcher_engine/runtime/rss.py](file:///D:/Python/content_hub/apps/fetcher_engine/runtime/rss.py)（可复用 `parse_rss_items` / `UnifiedPost`）
- FetchService 注册表：`apps/fetcher_engine/api/registry.py`（T002 产出）
- 任务清单：`content_hub_mvp_task_breakdown.md` 第 4.1 节第 4 项

## 输出要求（具体、可检查）

### 1. Reddit 抓取器
新建目录和文件：

```
apps/fetcher_engine/connectors/reddit/
    __init__.py
    fetcher.py
```

在 [fetcher.py](file:///D:/Python/content_hub/apps/fetcher_engine/connectors/reddit/fetcher.py) 中实现：

```python
class RedditFetcher:
    source_type = "reddit"

    def __init__(self, subreddit: str, sort: str = "hot", limit: int = 25):
        ...

    async def fetch(self, lookback_hours: int = 24, limit: int = 20) -> list[UnifiedPost]:
        ...
```

核心逻辑：
1. MVP 使用 Reddit 公开 RSS 入口：`https://www.reddit.com/r/{subreddit}/.rss` 或 JSON 入口 `https://www.reddit.com/r/{subreddit}/hot.json`。
2. RSS 方式：直接复用 [parse_rss_items](file:///D:/Python/content_hub/apps/fetcher_engine/runtime/rss.py) 函数。
3. JSON 方式（备选）：解析 Reddit JSON API，提取 `data.children[].data` 中的 `title` / `selftext` / `url` / `permalink` / `created_utc`。
4. 输出 `list[UnifiedPost]`：
   - `source` = `"reddit"`
   - `adapter` = `"reddit"`
   - `external_id` = post id（如 `t3_xxxxx`）
   - `title` = post title
   - `url` = `https://www.reddit.com{permalink}`
   - `summary` = selftext 前 500 字符
   - `published_at` = from `created_utc`
   - `raw` = {subreddit, author, score, num_comments, ups}

### 2. 注册到 FetchService
```python
register_fetcher("reddit", lambda cfg: RedditFetcher(subreddit=cfg.get("subreddit", "artificial"), sort=cfg.get("sort", "hot"), limit=cfg.get("limit", 25)))
```

### 3. 容错处理
- 404 subreddit 不存在 → 返回空列表
- Reddit 频限 → 记录错误，不崩溃
- 响应超时 30s

## 验收标准（必须全部勾选才算完成）
- [ ] `RedditFetcher.fetch()` 返回 `list[UnifiedPost]`，字段齐全
- [ ] 至少测试 `r/artificial`、`r/MachineLearning` 两个 subreddit
- [ ] 每个 item 的 `external_id` 为 Reddit post id
- [ ] `raw` 包含 score、author、num_comments 等元数据
- [ ] 已注册到 FetchService，可通过 `source_type="reddit"` 调度
- [ ] 更新 [codex_board.md](file:///D:/Python/content_hub/codex_board.md) 标记 T005 为完成
