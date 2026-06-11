# T004: github_trending_fetcher — GitHub Trending 抓取器

## 目标（一句话）
新增 GitHub Trending 抓取器，从 GitHub Trending 页面抓取热门仓库，输出为标准 `UnifiedPost` 列表并注册到 FetchService。

## 依赖
- 前置任务：T002（FetchService + 注册表已完成）
- 阻塞项：无（与 T003/T005/T006 可并行开发）

## 输入文件（请先阅读）
- RSS 抓取器参考：[apps/fetcher_engine/runtime/rss.py](file:///D:/Python/content_hub/apps/fetcher_engine/runtime/rss.py)（UnifiedPost 数据结构）
- Base 类：[apps/fetcher_engine/runtime/base.py](file:///D:/Python/content_hub/apps/fetcher_engine/runtime/base.py)
- FetchService 注册表：`apps/fetcher_engine/api/registry.py`（T002 产出）
- 任务清单：`content_hub_mvp_task_breakdown.md` 第 4.1 节第 3 项

## 输出要求（具体、可检查）

### 1. GitHub Trending 抓取器
新建目录和文件：

```
apps/fetcher_engine/connectors/github_trending/
    __init__.py
    fetcher.py
```

在 [fetcher.py](file:///D:/Python/content_hub/apps/fetcher_engine/connectors/github_trending/fetcher.py) 中实现：

```python
class GitHubTrendingFetcher:
    source_type = "github_trending"

    def __init__(self, language: str = "", since: str = "daily", spoken_language: str = ""):
        ...

    async def fetch(self, lookback_hours: int = 24, limit: int = 20) -> list[UnifiedPost]:
        ...
```

核心逻辑：
1. 请求 `https://github.com/trending`（可带 `?since=daily&language=python` 等参数）。
2. 解析 HTML 页面（推荐用 `BeautifulSoup` 或正则），提取：
   - `title`：`owner/repo` 名称
   - `url`：`https://github.com/{owner}/{repo}`
   - `summary`：仓库 description
   - `external_id`：`owner/repo` 作为唯一标识
   - `published_at`：使用当前时间
   - `raw`：star 数、language、forks 等 metadata
3. 输出 `list[UnifiedPost]`，严格遵守 `UnifiedPost` 字段结构。

### 2. 注册到 FetchService
在 `apps/fetcher_engine/api/registry.py` 中：
```python
register_fetcher("github_trending", lambda cfg: GitHubTrendingFetcher(language=cfg.get("language", "")))
```

### 3. 容错处理
- 网络错误捕获，不抛出异常
- 页面结构变化时优雅降级（返回空列表 + error log）
- 支持设置 `User-Agent` 避免 403

## 验收标准（必须全部勾选才算完成）
- [ ] `GitHubTrendingFetcher.fetch()` 返回 `list[UnifiedPost]`，字段齐全
- [ ] 每个 item 的 `external_id` 为 `owner/repo` 格式
- [ ] `raw` 字段包含 star 数、language 等元数据
- [ ] 网络不可达时返回空列表，不崩溃
- [ ] 已注册到 FetchService 注册表，可通过 `source_type="github_trending"` 调度
- [ ] 更新 [codex_board.md](file:///D:/Python/content_hub/codex_board.md) 标记 T004 为完成
