# T001: 数据模型扩展（第一批迁移）

## 目标
扩展现有数据库模型，支撑 MVP 闭环。

## 输入文件（请先阅读）
- 现有模型位置：`apps/platform/models.py`（或你当前的数据库模型文件）
- 架构文档参考：`docs/content_hub_product_architecture.md` 第 7.1 节

## 输出要求

### 1. 修改 `content_items` 表
新增字段：
- `source_account` (varchar)
- `language` (varchar, default 'zh')
- `summary` (text, nullable)
- `rewritten_title` (varchar, nullable)
- `rewritten_content` (text, nullable)
- `tags_json` (json, default '[]')
- `score` (float, default 0)
- `review_status` (varchar, default 'pending', 可选值: pending/approved/rejected/archived)
- `reviewed_at` (datetime, nullable)
- `digest_included` (boolean, default false)

### 2. 新增表（SQLAlchemy 模型 + Alembic 迁移）
- `source_subscriptions`
- `filter_rules`
- `rewrite_profiles`
- `review_queue`
- `digest_reports`
- `publish_records`

字段定义参考架构文档 7.1 节。

### 3. 统一模型基类
确保所有新表继承统一 Base，有 `created_at` / `updated_at`。

## 验收标准（必须全部勾选）
- [ ] Alembic 迁移文件生成成功（`alembic revision --autogenerate -m "mvp_batch1"`）
- [ ] `alembic upgrade head` 执行成功
- [ ] 能在 Python shell 中 `from apps.platform.models import ContentItem` 并访问新字段
- [ ] 更新 `codex_board.md` 标记 T001 为完成