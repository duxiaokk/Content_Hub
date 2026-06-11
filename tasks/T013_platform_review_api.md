# T013: platform_review_api — Platform：审核队列 API

## 目标（一句话）
在 platform 中新增审核队列 CRUD API，支持待审核列表查询、审核操作（通过/驳回/归档）以及内容编辑后通过。

## 依赖
- 前置任务：T012（信源 CRUD 完成）、T011（workflow 幂等完成，审核入队逻辑就绪）
- 阻塞项：依赖 T001（`review_queue` / `review_status` 字段已建）

## 输入文件（请先阅读）
- 审核队列数据模型：`review_queue` 表（T001 产出，[apps/platform/models.py](file:///D:/Python/content_hub/apps/platform/models.py) 中 `ReviewQueue` ORM 类）
- `content_items.review_status` 字段（T001 产出）
- 现有路由示例：[apps/platform/routers/internal_tasks.py](file:///D:/Python/content_hub/apps/platform/routers/internal_tasks.py)
- 现有 API schemas：[apps/platform/schemas/pipeline.py](file:///D:/Python/content_hub/apps/platform/schemas/pipeline.py)
- Sever-side 服务：[apps/platform/services/post_service.py](file:///D:/Python/content_hub/apps/platform/services/post_service.py)（示例参考）
- 任务清单：`content_hub_mvp_task_breakdown.md` 第 4.4 节（审核 API 部分）

## 输出要求（具体、可检查）

### 1. 审核服务层
新建或扩展 `apps/platform/services/review_service.py`：

```python
class ReviewService:
    def __init__(self, db: Session):
        self.db = db

    def get_pending_reviews(self, page: int, page_size: int) -> tuple[list[ReviewQueue], int]:
        """查询待审核列表"""
        ...

    def get_review_detail(self, review_id: int) -> dict:
        """获取单条审核详情（含原始 content_item 信息）"""
        ...

    def approve(self, review_id: int, reviewer: str) -> dict:
        """审核通过"""
        ...

    def reject(self, review_id: int, reviewer: str, note: str) -> dict:
        """驳回"""
        ...

    def archive(self, review_id: int, reviewer: str) -> dict:
        """归档"""
        ...
```

审核操作逻辑：
- `approve`：
  1. 更新 `review_queue.status = "approved"`, `reviewer = "xxx"`, `reviewed_at = now()`
  2. 更新 `content_items.review_status = "approved"`, `reviewed_at = now()`
  3. 返回审核结果 + 通知下游（供 T016 博客发布使用）
- `reject`：
  1. 更新 `review_queue.status = "rejected"`, `review_note = "xxx"`
  2. 更新 `content_items.review_status = "rejected"`
- `archive`：
  1. 更新 `review_queue.status = "archived"`
  2. 更新 `content_items.review_status = "archived"`

### 2. 审核 Pydantic Schemas
在 [apps/platform/schemas/pipeline.py](file:///D:/Python/content_hub/apps/platform/schemas/pipeline.py)（或新建 `schemas/review.py`）中：

```python
class ReviewQueueOut(BaseModel):
    id: int
    content_item_id: int
    candidate_title: str | None
    candidate_content: str | None
    status: str
    reviewer: str | None
    review_note: str | None
    reviewed_at: datetime | None
    created_at: datetime | None

    # 关联 content_items 信息
    original_title: str | None
    original_content: str | None
    summary: str | None
    score: float | None
    tags: list[str] | None
    source_url: str | None

class ReviewApproveRequest(BaseModel):
    reviewer: str = "admin"
    edited_title: str | None = None
    edited_content: str | None = None

class ReviewRejectRequest(BaseModel):
    reviewer: str = "admin"
    note: str = ""
```

### 3. 审核路由
新建 `apps/platform/routers/reviews.py`：

```python
router = APIRouter(prefix="/api/internal/content/reviews", tags=["reviews"])

@router.get("/", response_model=PaginatedResponse[ReviewQueueOut])
def list_reviews(page: int = 1, page_size: int = 20, status: str = "pending"):
    ...

@router.get("/{review_id}", response_model=ReviewQueueOut)
def get_review(review_id: int):
    ...

@router.post("/{review_id}/approve")
def approve_review(review_id: int, body: ReviewApproveRequest):
    ...

@router.post("/{review_id}/reject")
def reject_review(review_id: int, body: ReviewRejectRequest):
    ...

@router.post("/{review_id}/archive")
def archive_review(review_id: int, reviewer: str = "admin"):
    ...
```

在 `main.py` 中注册路由。

### 4. 编辑后通过
`approve` 接口支持可选 `edited_title` / `edited_content` 参数：
- 提供时，先更新 `review_queue.candidate_title` / `candidate_content` 为编辑后的版本，再执行通过逻辑。
- 同时更新 `content_items.rewritten_title` / `rewritten_content`（如果有）。

## 验收标准（必须全部勾选才算完成）
- [ ] `GET /api/internal/content/reviews?status=pending` 返回待审核列表
- [ ] `GET /api/internal/content/reviews/{id}` 返回审核详情（含原始内容+改写稿）
- [ ] `POST .../{id}/approve` 审核通过，review_queue 和 content_items 状态同步更新
- [ ] `POST .../{id}/reject` 驳回，review_note 保存成功
- [ ] `POST .../{id}/archive` 归档
- [ ] approve 带 edited_title/edited_content 时，编辑稿正确保存
- [ ] Swagger UI 可访问并测试所有端点
- [ ] 更新 [codex_board.md](file:///D:/Python/content_hub/codex_board.md) 标记 T013 为完成
