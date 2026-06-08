# API 契约 v1.0 — 范围冻结

> P0 基线 — 明确第一版 API 的保留、重构与废弃范围，冻结后续改动边界。

---

## 1. 契约原则

1. **版本号规则**：当前 API 无版本前缀的路径（如 `/posts`, `/ai`）后续统一迁移至 `/api/v1/`。
2. **兼容策略**：标记 `[保留]` 的接口承诺 **字段不回退**，新增字段只追加不删除。
3. **内部 vs 公开**：`/api/internal/*` 路径为服务间内部调用，不对外承诺兼容性。
4. **废弃宽限期**：标记 `[废弃]` 的接口在下一个大版本移除，当前保持可用。

---

## 2. 接口清单与分类

### 2.1 页面路由（HTML 渲染）

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| GET | `/` | **保留** | 首页 (搜索/筛选/分页) |
| GET | `/archive` | **保留** | 归档页 |
| GET | `/top` | **保留** | 核心能力矩阵 |
| GET | `/about` | **保留** | 关于页 |
| GET | `/architecture` | **保留** | 架构展示 |
| GET | `/demo` | **保留** | 任务演示 |
| GET | `/posts/{post_id}` | **保留** | 文章详情 HTML |
| GET | `/create-post` | **保留** | 创作页 (管理员) |
| GET | `/login` | **保留** | 登录页 |
| GET | `/register-page` | **保留** | 注册页 |
| GET | `/agent-demo` | **保留** | Agent 演示 |
| GET | `/random` | **保留** | 随机文章 |
| POST | `/handle-create-post` | **重构** | 表单提交 → 合并到 `/api/v1/posts` POST |
| GET | `/logout` | **保留** | 登出 |

### 2.2 认证 API

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| POST | `/login` | **保留** | JSON 登录 |
| POST | `/register` | **保留** | 注册 (JSON + Form) |
| POST | `/refresh-token` | **保留** | 刷新令牌 |
| POST | `/profile/avatar` | **保留** | 头像更新 |
| GET | `/csrf-token` | **保留** | CSRF 令牌 |

> **重构方向**：后续统一迁移到 `/api/v1/auth/*` 路径前缀。

### 2.3 文章 API

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| GET | `/api/v1/posts/{post_id}` | **保留** | 文章详情 JSON |
| POST | `/api/v1/posts/{post_id}/like` | **保留** | 点赞 |
| DELETE | `/api/v1/posts/{post_id}` | **保留** | 软删除 |

> **待补充**：
> - `POST /api/v1/posts` — 创建文章 (当前仅 HTML form)
> - `GET /api/v1/posts` — 文章列表 (当前仅 HTML 渲染)
> - `PUT /api/v1/posts/{post_id}` — 更新文章

### 2.4 评论 API

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| GET | `/posts/{post_id}/comments` | **保留** | 评论列表 |
| GET | `/posts/{post_id}/comments/stream` | **保留** | SSE 实时推送 |
| POST | `/posts/{post_id}/comments` | **保留** | 发评论 → 投递审核 |
| PUT | `/comments/{comment_id}` | **保留** | 编辑评论 |
| DELETE | `/comments/{comment_id}` | **保留** | 软删除 |
| POST | `/comments/{comment_id}/like` | **保留** | 评论点赞 |

> **重构方向**：迁移到 `/api/v1/comments/*`，与文章路径解耦。

### 2.5 AI API

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| POST | `/ai/articles/draft` | **重构** | 占位实现 → 合并到 Agent 草稿流 |
| POST | `/ai/outline` | **保留** | 生成大纲 |
| POST | `/ai/outline/stream` | **保留** | 流式大纲 (SSE) |
| POST | `/ai/polish` | **保留** | 文本润色 |
| POST | `/ai/polish/stream` | **保留** | 流式润色 (SSE) |
| POST | `/ai/analyze` | **保留** | 平台分析 |
| POST | `/ai/analyze/stream` | **保留** | 流式分析 (SSE) |
| POST | `/ai/recommend` | **保留** | 选题推荐 |
| POST | `/ai/recommend/stream` | **保留** | 流式推荐 (SSE) |
| POST | `/ai/draft` | **保留** | 生成草稿 |
| POST | `/ai/draft/stream` | **保留** | 流式草稿 (SSE) |

> **重构方向**：`/ai` → `/api/v1/ai`，`/ai/articles/draft` 与 Agent 草稿流统一。

### 2.6 内部 API（服务间调用）

| 方法 | 路径 | 鉴权 | 状态 | 说明 |
|------|------|------|------|------|
| POST | `/api/internal/agent/drafts` | x-internal-token | **保留** | Agent 草稿接入 |
| GET | `/api/internal/agent/drafts/{id}` | x-internal-token | **保留** | 查询草稿 |
| PATCH | `/api/internal/agent/drafts/{id}` | x-internal-token | **保留** | 更新草稿状态 |
| POST | `/api/internal/tasks/ado-repost/run` | x-internal-token | **保留** | 触发内容搬运 |

### 2.7 演示/开发 API

| 方法 | 路径 | 状态 | 说明 |
|------|------|------|------|
| POST | `/api/demo/submit` | **保留** (开发) | 演示任务提交 |
| GET | `/api/demo/status/{task_id}` | **保留** (开发) | 演示任务状态 |

> `/api/demo/*` 仅为开发演示用途，不纳入 v1 正式 API 契约。

### 2.8 调度中心 API（内部）

| 方法 | 路径 | 鉴权 | 状态 |
|------|------|------|------|
| GET | `/health` | 无 | **保留** |
| GET | `/ready` | 无 | **保留** |
| POST | `/api/internal/scheduler/tasks` | x-internal-token | **保留** |
| GET | `/api/internal/scheduler/tasks` | x-internal-token | **保留** |
| GET | `/api/internal/scheduler/tasks/{id}` | x-internal-token | **保留** |
| POST | `/api/internal/scheduler/tasks/{id}/cancel` | x-internal-token | **保留** |
| GET | `/api/internal/scheduler/tasks/{id}/logs` | x-internal-token | **保留** |
| POST | `/api/internal/scheduler/agents/register` | x-internal-token | **保留** |
| GET | `/api/internal/scheduler/agents` | x-internal-token | **保留** |

---

## 3. 平台 API 重构路线

以下为当前标记 `[重构]` 的接口及目标：

| 当前路径 | 目标路径 | 改动 |
|----------|----------|------|
| `POST /handle-create-post` | `POST /api/v1/posts` | Form → JSON API |
| `POST /ai/articles/draft` | 合并到 Agent 草稿流 | 移除占位实现 |
| `POST /login` | `/api/v1/auth/login` | 路径规范化 |
| `POST /register` | `/api/v1/auth/register` | 路径规范化 |
| `POST /refresh-token` | `/api/v1/auth/refresh` | 路径规范化 |
| `POST /profile/avatar` | `/api/v1/profile/avatar` | 路径规范化 |
| `POST /posts/{id}/comments` | `POST /api/v1/comments` | 路径规范化 |
| `GET /posts/{id}/comments` | `GET /api/v1/comments` | 路径规范化 |

---

## 4. 契约冻结范围

以下内容 **不允许** 在 v1 周期内修改：

1. **认证方式**：JWT (Access Token + Refresh Token) + Cookie + CSRF Token
2. **响应格式**：`{"detail": "..."}` 错误格式、分页结构
3. **内部鉴权头**：`x-internal-token` 头名称和机制
4. **SSE 格式**：`data: {"type": "...", "data": ...}` 结构
5. **软删除语义**：`deleted_at` 非空即删除，不物理删除
6. **调度中心任务状态机**：`PENDING → RUNNING → SUCCEEDED / FAILED / CANCELED`
7. **Agent 回调契约**：`POST /api/internal/agent/run` 的请求/响应结构

---

## 5. v2 计划（不纳入当前版本）

以下功能明确推迟到 v2：

- [ ] 文章全文搜索 API（Elasticsearch / PostgreSQL FTS）
- [ ] GraphQL 接口
- [ ] Webhook 事件通知
- [ ] OAuth2 第三方登录（GitHub / Google）
- [ ] 多语言支持 (i18n)
- [ ] 批量操作 API（批量删除/发布/标签）
- [ ] API Key 管理（程序化访问）
