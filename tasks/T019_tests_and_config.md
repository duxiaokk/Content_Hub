# T019: tests_and_config — 测试 + 配置项整理

## 目标（一句话）
补齐关键模块的单元测试和集成测试，整理所有 .env.example 配置项，确保项目可交付验收。

## 依赖
- 前置任务：T001~T018 全部完成
- 阻塞项：无

## 输入文件（请先阅读）
- 现有测试示例：[apps/workflow_engine/tests/](file:///D:/Python/content_hub/apps/workflow_engine/tests/)（conftest + 4 个测试文件）
- 现有测试示例：[apps/platform/tests/](file:///D:/Python/content_hub/apps/platform/tests/)（23 个测试文件）
- 现有 blog publisher 测试：[apps/publisher_engine/tests/test_blog_publisher.py](file:///D:/Python/content_hub/apps/publisher_engine/tests/test_blog_publisher.py)
- 现有 .env.example：[apps/platform/.env.example](file:///D:/Python/content_hub/apps/platform/.env.example)
- 现有迁移测试：[apps/platform/tests/test_migration_regression.py](file:///D:/Python/content_hub/apps/platform/tests/test_migration_regression.py)
- 任务清单：`content_hub_mvp_task_breakdown.md` 第 7、8 节

## 输出要求（具体、可检查）

### 1. 单元测试（8 个最小集合）
新建或扩展以下测试文件：

| 测试文件 | 测试内容 |
|----------|----------|
| `apps/fetcher_engine/tests/test_rss_parsing.py` | RSS 解析和时间过滤逻辑 |
| `apps/fetcher_engine/tests/test_github_trending.py` | GitHub Trending 抓取结果标准化 |
| `apps/fetcher_engine/tests/test_reddit.py` | Reddit 抓取结果标准化 |
| `apps/ai_processor/tests/test_summarize.py` | SummarizeProcessor 输出验证（含 mock LLM） |
| `apps/ai_processor/tests/test_rewrite_fallback.py` | RewriteProcessor 降级策略测试 |
| `apps/publisher_engine/tests/test_markdown_digest.py` | MarkdownDigestPublisher 输出格式验证 |
| `apps/workflow_engine/tests/test_filter_rules.py` | 关键词白/黑名单 + 去重规则 |
| `apps/workflow_engine/tests/test_dedup.py` | 去重逻辑单元测试 |

每个测试文件要求：
- 使用 pytest + pytest-asyncio（如涉及 async）。
- Mock 外部 HTTP / LLM 调用。
- 正面 case + 异常 case + 边界 case 各至少 1 个。

### 2. 集成测试（4 个）
新建或扩展以下测试文件：

| 测试文件 | 测试内容 |
|----------|----------|
| `apps/platform/tests/test_radar_pipeline_e2e.py` | radar_pipeline 从抓取到审核入队全链路 |
| `apps/platform/tests/test_review_publish_flow.py` | 审核通过后博客草稿发布流程 |
| `apps/platform/tests/test_digest_generation.py` | daily_digest_pipeline 日报生成全链路 |
| `apps/platform/tests/test_idempotency.py` | 重复内容不重复发布 |

要求：
- 使用 `conftest.py` 共享 fixtures（db session、test client 等）。
- 每个测试可独立运行、可重复运行。
- 使用测试数据库（`DATABASE_URL=sqlite:///./test_blog.db`），测试后清理。

### 3. API 测试（4 个）
新建或扩展：

| 测试文件 | 测试内容 |
|----------|----------|
| `apps/platform/tests/test_source_crud_api.py` | 信源 CRUD：创建/编辑/启停/列表 |
| `apps/platform/tests/test_review_api.py` | 审核队列：查询/通过/驳回/归档 |
| `apps/platform/tests/test_digest_api.py` | 日报：生成/查看/下载 |
| `apps/platform/tests/test_internal_task_trigger.py` | 内部任务触发接口 |

要求：使用 FastAPI TestClient。

### 4. .env.example 整理
在 [apps/platform/.env.example](file:///D:/Python/content_hub/apps/platform/.env.example) 末尾追加 Content Hub MVP 相关配置（不删除现有内容）：

```env
# =============================================================================
# 10. Content Hub MVP 配置 (Content Hub MVP)
# =============================================================================
# [OPTIONAL] 是否启用日报生成
CONTENT_HUB_ENABLE_DIGEST=true

# [OPTIONAL] 默认改写配置文件名（对应 rewrite_profiles.name）
CONTENT_HUB_DEFAULT_REWRITE_PROFILE=zh_tech_blog

# [OPTIONAL] 日报 Markdown 输出目录
CONTENT_HUB_DIGEST_OUTPUT_DIR=.tmp/digests

# [OPTIONAL] 审核是否必选（false=跳过审核直接发布）
CONTENT_HUB_REVIEW_REQUIRED=true

# [OPTIONAL] 默认关键词白名单（逗号分隔）
CONTENT_HUB_FILTER_KEYWORDS=agent,rag,llm,openai

# [OPTIONAL] 默认关键词黑名单（逗号分隔）
CONTENT_HUB_FILTER_EXCLUDE_KEYWORDS=招聘,广告

# [OPTIONAL] 是否启用 GitHub Trending 抓取
CONTENT_HUB_GITHUB_TRENDING_ENABLED=true

# [OPTIONAL] 是否启用 Reddit 抓取
CONTENT_HUB_REDDIT_ENABLED=true

# [OPTIONAL] 调度器是否启用定时任务
CONTENT_HUB_SCHEDULER_ENABLED=true
```

### 5. pytest 配置
确保 `pyproject.toml` 或 `pytest.ini` 中有基础的 pytest 配置：
```ini
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["apps/fetcher_engine/tests", "apps/ai_processor/tests", "apps/workflow_engine/tests", "apps/publisher_engine/tests", "apps/platform/tests"]
```

## 验收标准（必须全部勾选才算完成）
- [ ] 8 个单元测试全部通过（`pytest apps/fetcher_engine/tests/ apps/ai_processor/tests/ apps/publisher_engine/tests/ apps/workflow_engine/tests/ -v`）
- [ ] 4 个集成测试全部通过
- [ ] 4 个 API 测试全部通过
- [ ] `.env.example` 包含所有 Content Hub MVP 配置项
- [ ] 所有 LLM 调用在测试中均有 mock，不消耗真实 token
- [ ] 测试数据库不污染开发数据库
- [ ] 更新 [codex_board.md](file:///D:/Python/content_hub/codex_board.md) 标记 T019 为完成
