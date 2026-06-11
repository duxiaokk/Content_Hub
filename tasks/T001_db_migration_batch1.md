# T001: db_migration_batch1 — 数据模型扩展

## 目标（一句话）
扩展 `content_items` 表字段并新增 6 张 MVP 业务表，打通审核/分类/日报/发布全链路数据底座。

## 依赖
- 前置任务：无
- 阻塞项：无

## 输入文件（请先阅读）
- 现有迁移文件：[apps/platform/migrations/versions/f3a1c2d4e5f6_add_content_items.py](file:///D:/Python/content_hub/apps/platform/migrations/versions/f3a1c2d4e5f6_add_content_items.py)（当前 content_items 定义）
- 现有模型：[apps/platform/models.py](file:///D:/Python/content_hub/apps/platform/models.py)（SQLAlchemy Base / Post / User / Comment）
- Alembic 配置：[apps/platform/alembic.ini](file:///D:/Python/content_hub/apps/platform/alembic.ini)
- 架构文档：`content_hub_product_architecture.md` 第 7.1 节（统一内容模型字段定义）
- 任务清单：`content_hub_mvp_task_breakdown.md` 第 5.1 节（第一批迁移）

## 输出要求（具体、可检查）

### 1. 扩展 `content_items` 表
在现有 [f3a1c2d4e5f6_add_content_items.py](file:///D:/Python/content_hub/apps/platform/migrations/versions/f3a1c2d4e5f6_add_content_items.py) 的基础上，生成新的 Alembic 迁移文件，新增以下字段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `source_account` | VARCHAR(255) | NULL | 信源账号标识 |
| `language` | VARCHAR(16) | `'zh'` | 原文语言 |
| `summary` | TEXT | NULL | AI 生成摘要 |
| `rewritten_title` | VARCHAR(512) | NULL | 改写后标题 |
| `rewritten_content` | TEXT | NULL | 改写后正文 |
| `tags_json` | JSON/Text | `'[]'` | 标签列表 JSON |
| `score` | Float | 0 | 质量评分 |
| `review_status` | VARCHAR(32) | `'pending'` | 审核状态（pending/approved/rejected/archived） |
| `reviewed_at` | DateTime | NULL | 审核时间 |
| `digest_included` | Boolean | False | 是否已收入日报 |

用 `ALTER TABLE` 添加列，每个字段用 `if not exists` 风格保护（可参考现有迁移的 pattern）。

### 2. 新增 6 张表
每张表都需创建完整 SQLAlchemy 模型（在 [apps/platform/models.py](file:///D:/Python/content_hub/apps/platform/models.py) 中新增 ORM 类），并生成对应的 Alembic 迁移建表语句。

#### `source_subscriptions`
| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer PK | 自增主键 |
| `source_type` | VARCHAR(64) NOT NULL | rss / github_trending / reddit / cnblogs / bilibili |
| `source_name` | VARCHAR(128) NOT NULL | 显示名称 |
| `account_identifier` | VARCHAR(255) NULL | 账号/频道标识 |
| `feed_url` | VARCHAR(1024) NULL | RSS Feed URL |
| `schedule_expression` | VARCHAR(64) NULL | cron 表达式 |
| `enabled` | Boolean default True | 是否启用 |
| `category` | VARCHAR(64) NULL | 分类 |
| `default_tags` | VARCHAR(512) NULL | JSON 标签列表 |
| `last_cursor` | VARCHAR(512) NULL | 增量游标 |
| `created_at` | DateTime | 创建时间 |
| `updated_at` | DateTime | 更新时间 |

唯一索引：`(source_type, account_identifier)`

#### `filter_rules`
| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer PK | |
| `rule_type` | VARCHAR(32) NOT NULL | keyword_include / keyword_exclude / dedup |
| `rule_value` | TEXT NOT NULL | 规则值（JSON/关键词列表） |
| `priority` | Integer default 0 | 优先级 |
| `enabled` | Boolean default True | 是否启用 |
| `created_at` | DateTime | |
| `updated_at` | DateTime | |

#### `rewrite_profiles`
| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer PK | |
| `name` | VARCHAR(64) NOT NULL UNIQUE | 配置名称（如 zh_tech_blog） |
| `provider` | VARCHAR(32) | LLM provider |
| `model` | VARCHAR(64) | 模型名 |
| `timeout_seconds` | Integer default 60 | 超时 |
| `fallback_strategy` | VARCHAR(16) default 'skip' | skip / raw / retry |
| `system_prompt` | TEXT NULL | 自定义 system prompt |
| `max_tokens` | Integer default 2048 | 最大 token |
| `created_at` | DateTime | |
| `updated_at` | DateTime | |

#### `review_queue`
| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer PK | |
| `content_item_id` | Integer FK → content_items.id | 关联原始内容 |
| `candidate_title` | VARCHAR(512) NULL | 候选标题 |
| `candidate_content` | TEXT NULL | 候选正文 |
| `status` | VARCHAR(32) default 'pending' | pending / approved / rejected / archived |
| `reviewer` | VARCHAR(64) NULL | 审核人 |
| `review_note` | TEXT NULL | 审核备注 |
| `reviewed_at` | DateTime NULL | 审核时间 |
| `created_at` | DateTime | |
| `updated_at` | DateTime | |

#### `digest_reports`
| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer PK | |
| `title` | VARCHAR(255) NOT NULL | 日报标题 |
| `content_markdown` | TEXT NOT NULL | Markdown 正文 |
| `included_count` | Integer default 0 | 包含条目数 |
| `generated_at` | DateTime | 生成时间 |
| `run_id` | VARCHAR(64) NULL | 关联 workflow run_id |
| `created_at` | DateTime | |
| `updated_at` | DateTime | |

#### `publish_records`
| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer PK | |
| `content_item_id` | Integer FK → content_items.id | 关联内容 |
| `target_type` | VARCHAR(32) NOT NULL | blog / digest_markdown |
| `target_name` | VARCHAR(128) NULL | 目标名称 |
| `status` | VARCHAR(32) NOT NULL | success / failed / skipped |
| `external_url` | VARCHAR(1024) NULL | 发布后外部 URL |
| `external_id` | VARCHAR(255) NULL | 外部系统 ID |
| `response_payload` | TEXT NULL | 发布响应 JSON |
| `run_id` | VARCHAR(64) NULL | 关联 workflow run_id |
| `published_at` | DateTime | 发布时间 |
| `created_at` | DateTime | |
| `updated_at` | DateTime | |

### 3. 更新 SQLAlchemy ORM 模型
在 [apps/platform/models.py](file:///D:/Python/content_hub/apps/platform/models.py) 中新增：
- `ContentItem` ORM 类（映射当前 content_items 表 + 新字段）
- `SourceSubscription`
- `FilterRule`
- `RewriteProfile`
- `ReviewQueue`
- `DigestReport`
- `PublishRecord`

所有模型继承现有 `Base`（来自 `database.py`）。

## 验收标准（必须全部勾选才算完成）
- [ ] 新 Alembic 迁移文件已生成（命名格式 `{revision_id}_mvp_batch1_extend.py`）
- [ ] `alembic upgrade head` 执行成功，无报错
- [ ] `alembic downgrade -1` 执行成功，可回滚
- [ ] 能在 Python shell 中 `from apps.platform.models import ContentItem, SourceSubscription, ReviewQueue` 访问所有新模型
- [ ] 新增字段可通过 ORM 读写（如 `ContentItem().review_status = "approved"`）
- [ ] 更新 [codex_board.md](file:///D:/Python/content_hub/codex_board.md) 标记 T001 为完成
