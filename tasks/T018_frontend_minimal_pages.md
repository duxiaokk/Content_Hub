# T018: frontend_minimal_pages — 前端：信源/内容/审核/日报最小页面

## 目标（一句话）
在现有 React 前端基础上，新增信源管理、内容列表、审核队列和日报查看四个最小可用页面。

## 依赖
- 前置任务：T012（信源 CRUD API）、T013（审核 API）、T014（日报 API）
- 阻塞项：依赖后端 API 就绪

## 输入文件（请先阅读）
- 现有页面示例：[apps/platform/frontend/src/pages/Sources/SourcesPage.tsx](file:///D:/Python/content_hub/apps/platform/frontend/src/pages/Sources/SourcesPage.tsx)
- 现有类型定义：[apps/platform/frontend/src/types/index.ts](file:///D:/Python/content_hub/apps/platform/frontend/src/types/index.ts)（含 `SourceConfig` / `ContentItem` 等 TypeScript 接口）
- API 服务：[apps/platform/frontend/src/services/api.ts](file:///D:/Python/content_hub/apps/platform/frontend/src/services/api.ts)
- 路由配置：`apps/platform/frontend/src/App.tsx`
- 布局组件：[apps/platform/frontend/src/components/Layout/AppLayout.tsx](file:///D:/Python/content_hub/apps/platform/frontend/src/components/Layout/AppLayout.tsx)
- 现有 ContentQueue：[apps/platform/frontend/src/pages/ContentQueue/ContentQueuePage.tsx](file:///D:/Python/content_hub/apps/platform/frontend/src/pages/ContentQueue/ContentQueuePage.tsx)
- 任务清单：`content_hub_mvp_task_breakdown.md` 第 6 节

## 输出要求（具体、可检查）

### 1. 扩展 TypeScript 类型
在 [apps/platform/frontend/src/types/index.ts](file:///D:/Python/content_hub/apps/platform/frontend/src/types/index.ts) 中新增/扩展：

```typescript
export interface SourceSubscription {
  id: number;
  source_type: string;
  source_name: string;
  account_identifier?: string;
  feed_url?: string;
  enabled: boolean;
  category?: string;
  last_cursor?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ReviewItem {
  id: number;
  content_item_id: number;
  candidate_title?: string;
  candidate_content?: string;
  original_title: string;
  original_content: string;
  summary?: string;
  source_url?: string;
  score: number;
  tags: string[];
  category?: string;
  status: ReviewStatus;
  reviewer?: string;
  review_note?: string;
  reviewed_at?: string;
  created_at?: string;
}

export type ReviewStatus = 'pending' | 'approved' | 'rejected' | 'archived';

export interface DigestReport {
  id: number;
  title: string;
  content_markdown: string;
  included_count: number;
  generated_at: string;
  created_at?: string;
}
```

### 2. 信源管理页面（增强 SourcesPage）
修改现有 [apps/platform/frontend/src/pages/Sources/SourcesPage.tsx](file:///D:/Python/content_hub/apps/platform/frontend/src/pages/Sources/SourcesPage.tsx)：

最小能力：
- 列表展示：source_type、source_name、enabled 状态、category、last_cursor
- 启停信源（toggle switch）
- 手动触发抓取按钮（调用 `POST /api/internal/tasks/content-pipeline/radar/run`）
- 新增信源表单（modal 或 drawer）

### 3. 内容列表页面（增强 ContentQueue）
修改现有 [apps/platform/frontend/src/pages/ContentQueue/ContentQueuePage.tsx](file:///D:/Python/content_hub/apps/platform/frontend/src/pages/ContentQueue/ContentQueuePage.tsx)：

最小能力：
- 列表展示：title、source_type、pipeline_status、review_status、score、created_at
- 筛选：按 pipeline_status / review_status / source_type
- 展开查看摘要和改写结果（详细信息面板）
- 点击进入审核详情页

### 4. 审核队列页面（新建）
新建 `apps/platform/frontend/src/pages/ReviewQueue/ReviewQueuePage.tsx`：

最小能力：
- 待审核列表（status=pending 的 review_queue 记录）
- 三栏查看：原文 / 摘要+改写稿 / 元数据
- 操作按钮：通过 / 驳回 / 归档
- 驳回时输入 review_note
- 编辑改写稿后通过（inline 编辑 textarea）

### 5. 日报查看页面（新建）
新建 `apps/platform/frontend/src/pages/Digests/DigestPage.tsx`：

最小能力：
- 最新日报列表
- 点击查看 Markdown 渲染内容
- 手动重新生成按钮（`POST /api/internal/tasks/content-pipeline/daily-digest/run`）
- 下载 Markdown 文件按钮

### 6. 路由注册
在 `apps/platform/frontend/src/App.tsx` 中新增路由：
```typescript
<Route path="/review-queue" element={<ReviewQueuePage />} />
<Route path="/digests" element={<DigestPage />} />
```

在 AppLayout 侧边栏增加菜单项："审核队列"、"日报"。

### 7. API 调用函数
在 [apps/platform/frontend/src/services/api.ts](file:///D:/Python/content_hub/apps/platform/frontend/src/services/api.ts) 中新增：

```typescript
// 信源管理
getSources(): Promise<SourceSubscription[]>
createSource(data): Promise<SourceSubscription>
updateSource(id, data): Promise<SourceSubscription>
toggleSource(id, enabled): Promise<void>
triggerFetch(sourceId): Promise<void>

// 审核队列
getReviews(params): Promise<PaginatedResponse<ReviewItem>>
getReview(id): Promise<ReviewItem>
approveReview(id): Promise<void>
rejectReview(id, note): Promise<void>
archiveReview(id): Promise<void>

// 日报
getDigests(): Promise<DigestReport[]>
getDigest(id): Promise<DigestReport>
generateDigest(): Promise<DigestReport>
downloadDigest(id): Promise<Blob>
```

## 验收标准（必须全部勾选才算完成）
- [ ] 信源管理页面：可查看/启停/新增信源，可手动触发抓取
- [ ] 内容列表页面：可查看/筛选 pipeline 状态
- [ ] 审核队列页面：可查看待审核列表，原文/摘要/改写稿三栏显示
- [ ] 审核队列页面：可通过/驳回/归档，驳回可输入备注
- [ ] 日报页面：可查看最新日报列表，查看渲染内容，下载 Markdown
- [ ] 所有页面通过 AppLayout 侧边栏可达
- [ ] 无 TypeScript 编译错误
- [ ] 更新 [codex_board.md](file:///D:/Python/content_hub/codex_board.md) 标记 T018 为完成
