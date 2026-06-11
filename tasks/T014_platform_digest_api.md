# T014: platform_digest_api — Platform：日报 API

## 目标（一句话）
在 platform 中新增日报查询和生成 API，支持查看历史日报列表、日报详情和手动触发日报生成。

## 依赖
- 前置任务：T013（审核 API 完成，有 approved 内容可用）、T011（workflow 完成）
- 阻塞项：依赖 T001（`digest_reports` 表已建）

## 输入文件（请先阅读）
- `digest_reports` 表结构（T001 产出）
- 现有路由示例：[apps/platform/routers/internal_tasks.py](file:///D:/Python/content_hub/apps/platform/routers/internal_tasks.py)
- API schemas：[apps/platform/schemas/pipeline.py](file:///D:/Python/content_hub/apps/platform/schemas/pipeline.py)
- 任务清单：`content_hub_mvp_task_breakdown.md` 第 4.4 节（日报 API 部分）

## 输出要求（具体、可检查）

### 1. 日报 Service 层
新建 `apps/platform/services/digest_service.py`：

```python
class DigestService:
    def __init__(self, db: Session):
        self.db = db

    def list_digests(self, page: int = 1, page_size: int = 20) -> tuple[list[DigestReport], int]:
        """查询日报列表（按 generated_at 倒序）"""
        ...

    def get_digest(self, digest_id: int) -> DigestReport:
        """获取单条日报详情"""
        ...

    def generate_digest(self, run_id: str, lookback_hours: int = 24) -> DigestReport:
        """生成日报：拉取最近 24h 审核通过的内容 → 传入 MarkdownDigestPublisher → 入库"""
        ...
```

**generate_digest 流程**：
1. 查询审核通过的内容（`content_items.review_status = "approved"` + `created_at` 在 lookback 范围内）。
2. 调用 publisher_engine 的 `MarkdownDigestPublisher.generate()` 生成 Markdown。
3. 插入 `digest_reports` 记录。
4. 更新 `content_items.digest_included = True`。
5. 返回 `DigestReport`。

### 2. 日报 Pydantic Schemas
在 [apps/platform/schemas/pipeline.py](file:///D:/Python/content_hub/apps/platform/schemas/pipeline.py) 中新增：

```python
class DigestReportOut(BaseModel):
    id: int
    title: str
    content_markdown: str
    included_count: int
    generated_at: datetime
    run_id: str | None
    created_at: datetime | None

    model_config = ConfigDict(from_attributes=True)

class DigestGenerateRequest(BaseModel):
    lookback_hours: int = 24
    run_id: str | None = None
```

### 3. 日报路由
新建 `apps/platform/routers/digests.py`：

```python
router = APIRouter(prefix="/api/internal/content/digests", tags=["digests"])

@router.get("/", response_model=PaginatedResponse[DigestReportOut])
def list_digests(page: int = 1, page_size: int = 20):
    ...

@router.get("/{digest_id}", response_model=DigestReportOut)
def get_digest(digest_id: int):
    ...

@router.post("/generate", response_model=DigestReportOut)
def generate_digest(body: DigestGenerateRequest):
    """手动触发日报生成"""
    ...
```

在 `main.py` 中注册路由。

### 4. Markdown 下载端点
日报查看支持下载：
```python
@router.get("/{digest_id}/download")
def download_digest_markdown(digest_id: int):
    """返回 content-type: text/markdown 的下载响应"""
    digest = digest_service.get_digest(digest_id)
    return Response(content=digest.content_markdown, media_type="text/markdown",
                    headers={"Content-Disposition": f"attachment; filename=digest_{digest_id}.md"})
```

## 验收标准（必须全部勾选才算完成）
- [ ] `GET /api/internal/content/digests` 返回日报列表（按时间倒序）
- [ ] `GET /api/internal/content/digests/{id}` 返回日报详情（含 content_markdown）
- [ ] `POST /api/internal/content/digests/generate` 触发日报生成，返回新建日报
- [ ] 生成后 `content_items.digest_included` 标记为 True
- [ ] 生成后 `digest_reports` 表有对应记录
- [ ] `GET /api/internal/content/digests/{id}/download` 下载 Markdown 文件
- [ ] Swagger UI 可测试所有端点
- [ ] 更新 [codex_board.md](file:///D:/Python/content_hub/codex_board.md) 标记 T014 为完成
