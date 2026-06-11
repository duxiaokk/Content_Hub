# T012: platform_source_api — Platform：信源管理 CRUD API

## 目标（一句话）
在 platform 中新增信源订阅管理的完整 CRUD API，支持列表查询、新增、编辑、启停信源。

## 依赖
- 前置任务：T001（`source_subscriptions` 表已建）
- 阻塞项：无

## 输入文件（请先阅读）
- `source_subscriptions` ORM 模型：[apps/platform/models.py](file:///D:/Python/content_hub/apps/platform/models.py)（T001 产出）
- 现有路由示例：[apps/platform/routers/post.py](file:///D:/Python/content_hub/apps/platform/routers/post.py)（FastAPI 路由写法）
- 现有 API schemas：[apps/platform/schemas/post.py](file:///D:/Python/content_hub/apps/platform/schemas/post.py)（Pydantic schema 写法）
- 现有 CRUD 模式：[apps/platform/crud/crud_post.py](file:///D:/Python/content_hub/apps/platform/crud/crud_post.py)（Repository 层写法）
- 现有服务层：[apps/platform/services/post_service.py](file:///D:/Python/content_hub/apps/platform/services/post_service.py)（Service 层写法）
- 架构文档：`content_hub_product_architecture.md` 第 12.1 节（信源中心信息架构）
- 任务清单：`content_hub_mvp_task_breakdown.md` 第 4.4 节（信源管理 API）

## 输出要求（具体、可检查）

### 1. 信源 Pydantic Schemas
在 [apps/platform/schemas/pipeline.py](file:///D:/Python/content_hub/apps/platform/schemas/pipeline.py)（或新建 `schemas/source.py`）中定义：

```python
class SourceSubscriptionCreate(BaseModel):
    source_type: str             # rss / github_trending / reddit / cnblogs / bilibili
    source_name: str             # 显示名称
    account_identifier: str | None = None
    feed_url: str | None = None
    schedule_expression: str | None = None
    category: str | None = None
    default_tags: str | None = None    # JSON 字符串

class SourceSubscriptionUpdate(BaseModel):
    source_name: str | None = None
    feed_url: str | None = None
    schedule_expression: str | None = None
    category: str | None = None
    default_tags: str | None = None

class SourceSubscriptionOut(BaseModel):
    id: int
    source_type: str
    source_name: str
    account_identifier: str | None
    feed_url: str | None
    enabled: bool
    category: str | None
    default_tags: str | None
    last_cursor: str | None
    created_at: datetime | None
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
```

### 2. 信源 Service 层
新建 `apps/platform/services/source_service.py`：

```python
class SourceService:
    def __init__(self, db: Session):
        self.db = db

    def list_sources(self, enabled_only: bool = False) -> list[SourceSubscription]:
        ...

    def get_source(self, source_id: int) -> SourceSubscription:
        ...

    def create_source(self, data: SourceSubscriptionCreate) -> SourceSubscription:
        ...

    def update_source(self, source_id: int, data: SourceSubscriptionUpdate) -> SourceSubscription:
        ...

    def enable_source(self, source_id: int) -> SourceSubscription:
        ...

    def disable_source(self, source_id: int) -> SourceSubscription:
        ...
```

### 3. 信源路由
新建 `apps/platform/routers/sources.py`：

```python
router = APIRouter(prefix="/api/internal/content/sources", tags=["sources"])

@router.get("/")
def list_sources():
    ...

@router.post("/")
def create_source(body: SourceSubscriptionCreate):
    ...

@router.patch("/{source_id}")
def update_source(source_id: int, body: SourceSubscriptionUpdate):
    ...

@router.post("/{source_id}/enable")
def enable_source(source_id: int):
    ...

@router.post("/{source_id}/disable")
def disable_source(source_id: int):
    ...
```

在 [apps/platform/main.py](file:///D:/Python/content_hub/apps/platform/main.py) 中注册 `from routers.sources import router as sources_router`。

## 验收标准（必须全部勾选才算完成）
- [ ] `GET /api/internal/content/sources` 返回所有信源列表
- [ ] `POST /api/internal/content/sources` 可创建新信源
- [ ] `PATCH /api/internal/content/sources/{id}` 可编辑信源字段
- [ ] `POST /api/internal/content/sources/{id}/enable` 启用信源
- [ ] `POST /api/internal/content/sources/{id}/disable` 停用信源
- [ ] 唯一约束 `(source_type, account_identifier)` 生效，重复创建报 409
- [ ] Swagger UI 可访问并测试所有端点（`/docs`）
- [ ] 更新 [codex_board.md](file:///D:/Python/content_hub/codex_board.md) 标记 T012 为完成
