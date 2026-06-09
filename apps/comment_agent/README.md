# Comment Agent

Third-party AI comment agent service for blog platforms.

## MVP Scope

- Receive blog webhook events
- Verify HMAC signatures
- Store sites, agents, events, and reply tasks
- Expose basic admin APIs
- Prepare async task records for later worker integration

## Quick Start

1. Create a virtual environment and install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

   If you use the workspace bootstrap script, it will also install the local `shared_memory` package for this service.

2. Start the API server:

   ```bash
   uvicorn app.main:app --reload
   ```

3. Open docs:

   ```text
   http://127.0.0.1:8000/docs
   ```

4. Optional environment file:

   ```bash
   copy .env.example .env
   ```

## Probes

- `GET /health`：进程存活探测
- `GET /ready`：就绪探测（含 DB 连通性检查）
- `GET /mempool/health`：Shared Memory（Redis/SQLite）健康状态

## Shared Memory

Comment Agent 会在启动时初始化共享记忆池（Redis 可选，SQLite 必选），并提供 `/mempool/health` 健康检查接口。

可用配置项（`.env`）：

```text
MEMPOOL_NAMESPACE=comment-agent
MEMPOOL_REDIS_URL=redis://localhost:6379/0
MEMPOOL_REDIS_KEY_PREFIX=shared_memory:
MEMPOOL_SQLITE_PATH=./shared_mempool.db
MEMPOOL_DEFAULT_TTL_SECONDS=3600
```

## CORS

通过环境变量配置白名单 Origin（逗号分隔），为空表示不启用 CORS：

```text
COMMENT_AGENT_CORS_ALLOW_ORIGINS=http://localhost:5173
```

## Internal Auth

Agent 内部接口 `POST /api/internal/agent/run` 需要请求头：

```text
x-internal-token: <TOKEN>
```

优先读取 `COMMENT_AGENT_INTERNAL_TOKEN`，同时兼容 `SCHEDULER_INTERNAL_TOKEN`（用于与 Scheduler Center 对齐）。

## Current API

- `POST /api/v1/events`
- `POST /api/v1/sites`
- `GET /api/v1/sites`
- `POST /api/v1/agents`
- `GET /api/v1/agents`
- `GET /api/v1/tasks`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/event-logs`
- `GET /api/v1/reviews`
- `POST /api/v1/reviews/{review_id}/approve`
- `POST /api/v1/reviews/{review_id}/reject`
- `POST /api/v1/admin/tasks/{task_id}/mock-review`

## Suggested Bootstrap Order

1. Create a site record with `site_key`, `webhook_secret`, and `api_token`
2. Create at least one enabled agent for that site
3. Send webhook events to `POST /api/v1/events`
4. Read queued tasks from `GET /api/v1/tasks`

## Webhook Notes

- Supported events in MVP:
  - `article.published`
  - `comment.created`
- Signature header:

  ```text
  X-Webhook-Signature: sha256=<hex_digest>
  ```

- The HMAC payload is the raw JSON request body.
- The current MVP matches the incoming `site.id` field to local `sites.site_key`.

## Current Behavior

- Duplicate events are rejected by generated event id uniqueness
- Unsupported events are stored and marked as skipped
- Accepted events create reply tasks with fixed delay scheduling
- The worker and actual LLM publishing flow are not implemented yet

## Admin Workflow in MVP

1. Create a site
2. Create an agent
3. Send an event
4. Inspect event logs with `GET /api/v1/event-logs`
5. Inspect queued tasks with `GET /api/v1/tasks`
6. Create a mock review item with `POST /api/v1/admin/tasks/{task_id}/mock-review`
7. Review pending items with `GET /api/v1/reviews`
8. Approve or reject using the review endpoints

## Why the Mock Review Endpoint Exists

- It lets the admin flow be exercised before the model worker is built
- It keeps backend and frontend admin development unblocked
- It makes status transitions testable with realistic records

## Notes

- Default database uses local SQLite for MVP bootstrap.
- Replace with MySQL or PostgreSQL before production rollout.
