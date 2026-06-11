# T015: publisher_markdown — Publisher：Markdown 日报生成器

## 目标（一句话）
在 publisher_engine 中新增 Markdown 日报生成适配器，将审核通过的内容聚合为格式化的 Markdown 日报文件。

## 依赖
- 前置任务：T014（日报 API 完成）、T011（workflow 幂等控制完成）
- 阻塞项：无

## 输入文件（请先阅读）
- 现有 blog publisher：[apps/publisher_engine/adapters/blog/publisher.py](file:///D:/Python/content_hub/apps/publisher_engine/adapters/blog/publisher.py)
- publisher 模型：[apps/publisher_engine/runtime/models.py](file:///D:/Python/content_hub/apps/publisher_engine/runtime/models.py)
- 架构文档：`content_hub_product_architecture.md` 第 11.2 节
- 任务清单：`content_hub_mvp_task_breakdown.md` 第 4.5 节

## 输出要求（具体、可检查）

### 1. 新建 Markdown 日报适配器
新建 `apps/publisher_engine/adapters/markdown_export/publisher.py`：

```python
class MarkdownDigestPublisher:
    """将 digest_items 列表渲染为 Markdown 日报，输出到文件或返回字符串"""

    name = "markdown_digest"

    async def publish(self, items: list[dict], options: dict | None = None) -> dict:
        ...
```

**Markdown 模板**：
```markdown
# 技术内容日报 — {date}

> 生成时间：{generated_at}  |  共 {count} 条

---

## 1. [{title}]({url})
- **来源**：{source_type} / {source_account}
- **分类**：{category}
- **标签**：{tags}
- **摘要**：{summary}

---

## 2. ...
```

**输出**：
- `content_markdown`：完整的 Markdown 字符串
- `file_path`：保存路径（`CONTENT_HUB_DIGEST_OUTPUT_DIR` / `{date}.md`）

### 2. 集成到 PublishingService
在 `apps/publisher_engine/api/` 新增或扩展 PublishingService：

```python
class PublishingService:
    async def generate_digest(self, items: list[dict], run_id: str) -> DigestResult:
        """将审核通过的内容列表生成为日报 Markdown"""
        ...
```

流程：
1. 调用 MarkdownDigestPublisher 生成 Markdown 字符串。
2. 写入文件（路径：`{DIGEST_OUTPUT_DIR}/{date}.md`）。
3. 插入 `digest_reports` 表记录。
4. 返回 `DigestResult`。

### 3. 文件输出配置
从 .env 读取：
```env
CONTENT_HUB_DIGEST_OUTPUT_DIR=.tmp/digests
```
默认目录 `.tmp/digests`，如不存在则自动创建。

### 4. 发布记录回写
日报生成成功/失败后，向 `publish_records` 插入记录：
```python
{
    "content_item_id": None,          # 日报是聚合产物，不关联单条
    "target_type": "digest_markdown",
    "target_name": "daily_digest",
    "status": "success",
    "run_id": run_id,
    "response_payload": "{'file_path': '...'}"
}
```

## 验收标准（必须全部勾选才算完成）
- [ ] `MarkdownDigestPublisher.publish()` 输出格式正确的 Markdown 日报
- [ ] 日报文件成功写入 `CONTENT_HUB_DIGEST_OUTPUT_DIR`
- [ ] `digest_reports` 表中有对应记录
- [ ] 生成失败时 `publish_records` 中有 fail 记录
- [ ] 日报中包含每条内容的来源、摘要、标签、URL
- [ ] 日期格式为 `YYYY-MM-DD`
- [ ] 更新 [codex_board.md](file:///D:/Python/content_hub/codex_board.md) 标记 T015 为完成
