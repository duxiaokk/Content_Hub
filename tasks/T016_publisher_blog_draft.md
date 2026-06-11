# T016: publisher_blog_draft — Publisher：博客草稿发布 + 发布记录

## 目标（一句话）
增强现有博客发布适配器，使其支持从审核队列获取批准内容并发布为博客草稿，同时记录每次发布结果到 publish_records。

## 依赖
- 前置任务：T013（审核队列 API 完成，有 approved 内容可发）
- 阻塞项：依赖博客系统 API 或数据库

## 输入文件（请先阅读）
- 现有 blog publisher：[apps/publisher_engine/adapters/blog/publisher.py](file:///D:/Python/content_hub/apps/publisher_engine/adapters/blog/publisher.py)
- publisher 运行时：[apps/publisher_engine/runtime/base.py](file:///D:/Python/content_hub/apps/publisher_engine/runtime/base.py)
- publisher client：[apps/publisher_engine/runtime/client.py](file:///D:/Python/content_hub/apps/publisher_engine/runtime/client.py)
- 现有 blog publisher 测试：[apps/publisher_engine/tests/test_blog_publisher.py](file:///D:/Python/content_hub/apps/publisher_engine/tests/test_blog_publisher.py)
- 架构文档：`content_hub_product_architecture.md` 第 11.2 节
- 任务清单：`content_hub_mvp_task_breakdown.md` 第 4.5 节

## 输出要求（具体、可检查）

### 1. 增强 BlogPublisher
在 [apps/publisher_engine/adapters/blog/publisher.py](file:///D:/Python/content_hub/apps/publisher_engine/adapters/blog/publisher.py) 中增强：

```python
class BlogPublisher:
    name = "blog"

    async def publish(self, content: dict, options: dict | None = None) -> dict:
        """将审核通过的 content 发布为博客草稿（MVP 默认 draft 模式）"""
        ...
```

要求：
- MVP 默认 `draft` 模式（`options.mode = "draft"`），不直接发布为正式文章。
- 输入 `content` 字典应包含：`title`, `content`（改写后的正文）, `tags`, `source_url`。
- 调用现有博客 API 或数据库写入 `posts` 表（[apps/platform/models.py](file:///D:/Python/content_hub/apps/platform/models.py) 中 `Post` 模型）。
- 直接写入 `posts` 表（`published=False` 即草稿）是最简路径。

### 2. 发布记录管理
在 [apps/publisher_engine/runtime/models.py](file:///D:/Python/content_hub/apps/publisher_engine/runtime/models.py) 中新增/or 扩展 Pydantic 模型：

```python
class PublishRequest(BaseModel):
    content_item_id: int
    candidate_title: str
    candidate_content: str
    target_type: str          # "blog" / "digest_markdown"
    options: dict = {}

class PublishResponse(BaseModel):
    content_item_id: int
    target_type: str
    status: str               # "success" / "failed" / "skipped"
    external_url: str | None
    external_id: str | None
    message: str
```

每次发布后写入 `publish_records` 表（T001 已建）。

### 3. 发布后回写 content_items
发布成功后，更新 `content_items`：
- `publish_status` = `"published"`
- `content_items.pipeline_status` = `"published"`

### 4. 幂等检查（与 T011 配合）
发布前检查：
```python
existing = db.query(PublishRecord).filter(
    PublishRecord.content_item_id == item_id,
    PublishRecord.target_type == "blog",
    PublishRecord.status == "success"
).first()
if existing:
    return PublishResponse(status="skipped", message="already published")
```

## 验收标准（必须全部勾选才算完成）
- [ ] `BlogPublisher.publish()` 可将审核通过的内容发布为博客草稿（`posts.published=False`）
- [ ] 发布成功后 `publish_records` 中有 success 记录
- [ ] `content_items.publish_status` 更新为 `"published"`
- [ ] 重复发布同一个 `(content_item_id, target_type)` 时返回 `"skipped"`
- [ ] 发布失败时 `publish_records` 中有 fail 记录（含 error message）
- [ ] 更新 [codex_board.md](file:///D:/Python/content_hub/codex_board.md) 标记 T016 为完成
