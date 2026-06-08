# 部署清单 (Deployment Checklist)

> P0 基线 — 端口、健康检查、数据目录、日志目录的完整清单。

---

## 1. 端口分配

| 服务 | 默认端口 | 协议 | 对外暴露 | 说明 |
|------|----------|------|----------|------|
| 平台主服务 | `8000` | HTTP | 是 | 用户入口，页面 + API |
| 调度中心 | `8010` | HTTP | 否 (内部) | 仅内网可达 |
| Comment Agent | `8020` | HTTP | 否 (内部) | 约定端口 |
| Audit Agent | 动态 | HTTP | 否 (内部) | 启动时注册到调度中心 |
| Ado Repost Agent | 动态 | HTTP | 否 (内部) | 启动时注册到调度中心 |
| Redis | `6379` | TCP | 否 (内部) | 可选 |

**冲突检查**：部署前确保以上端口未被占用。

---

## 2. 健康检查

| 服务 | 存活检查 | 就绪检查 | 鉴权要求 |
|------|----------|----------|----------|
| 平台主服务 | `GET /docs` (可访问即存活) | — | 无 (公开) |
| 调度中心 | `GET /health` → `{"status":"ok"}` | `GET /ready` → `{"status":"ready","db_ok":true}` | 无 (内部) |
| Audit Agent | `GET /health` → `{"status":"ok"}` | — | 无 (内部) |
| Comment Agent | `GET /health` | `GET /ready` | 无 (内部) |

**说明**：
- 平台主服务当前无独立 `/health` 端点，后续应在 `main.py` 中补充。
- 调度中心 `/ready` 检查数据库连通性 (`SELECT 1`)。
- Docker / K8s 部署时应配置 `healthcheck` 或 `livenessProbe` / `readinessProbe`。

### 健康检查验证命令

```bash
# 平台主服务
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/

# 调度中心
curl http://localhost:8010/health
curl http://localhost:8010/ready

# Audit Agent
curl http://<audit_agent_host>/health
```

---

## 3. 数据目录

| 路径 | 用途 | 持久化 | 备份策略 |
|------|------|--------|----------|
| `./blog.db` | 平台主数据库 (SQLite) | 必须 | 每日备份 |
| `./scheduler.db` | 调度中心数据库 (SQLite) | 必须 | 每日备份 |
| `./content/agent_drafts/` | Agent 生成的 Markdown 草稿 | 必须 | 纳入备份 |
| `./static/` | 前端静态资源 (CSS/JS) | 否 (代码) | Git 管理 |
| `./image/` | 用户上传图片 | 必须 | 纳入备份 |
| `./migrations/` | Alembic 数据库迁移脚本 | 否 (代码) | Git 管理 |

**生产环境迁移建议**：
- SQLite → PostgreSQL：修改 `DATABASE_URL` / `SCHEDULER_DATABASE_URL` 即可
- 文件存储 → 对象存储 (S3/MinIO)：`content/agent_drafts/` 和 `image/` 目录

---

## 4. 日志目录

| 路径 | 来源 | 日志内容 |
|------|------|----------|
| stdout/stderr | 平台主服务 | FastAPI 请求日志、应用日志 (`logging.INFO`) |
| stdout/stderr | 调度中心 | 调度日志、任务执行日志、Agent 回调日志 |
| stdout/stderr | Audit Agent | 审核日志、LLM 调用日志 |
| `scheduler_task_logs` 表 | 调度中心数据库 | 任务级结构化日志 |

**当前状态**：所有日志输出到 stdout/stderr，由容器运行时或 systemd 收集。
建议：生产环境接入结构化日志（JSON 格式）+ 集中日志平台（ELK / Loki）。

---

## 5. 启动命令

### 开发环境

```bash
# 平台主服务
python tasks.py run

# 调度中心 (含 API + Dispatcher)
python -m scheduler_center.worker

# 或分别启动
python -m scheduler_center.main          # 仅 API
python -m scheduler_center.worker         # 仅 Dispatcher

# Ingest Worker (启用 Fast Submit 时需要)
python -m scheduler_center.ingest_worker

# Audit Agent
python audit_agent.py
```

### Docker

```bash
docker build -t personal-blog .
docker run -p 8000:8000 --env-file .env personal-blog
```

### 生产环境 (systemd 示例)

```ini
[Unit]
Description=Personal Blog Platform
After=network.target

[Service]
Type=simple
User=app
WorkingDirectory=/opt/personal-blog
EnvironmentFile=/opt/personal-blog/.env
ExecStart=/opt/personal-blog/venv/bin/python tasks.py run --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## 6. 环境变量清单速查

### 平台主服务必填项

| 变量 | 生产环境要求 |
|------|-------------|
| `SECRET_KEY` | `openssl rand -hex 32` 生成，通过密钥管理服务注入 |
| `DATABASE_URL` | PostgreSQL 连接串 |
| `SCHEDULER_CENTER_URL` | 调度中心内网地址 |
| `SCHEDULER_INTERNAL_TOKEN` | 随机生成，与调度中心一致 |
| `LLM_API_KEY` | 通过密钥管理服务注入 |
| `INTERNAL_AGENT_TOKEN` | 随机生成，与 Agent 端一致 |

### 调度中心必填项

| 变量 | 生产环境要求 |
|------|-------------|
| `SCHEDULER_INTERNAL_TOKEN` | 随机生成，与调用方一致 |
| `SCHEDULER_DATABASE_URL` | PostgreSQL 连接串（替代 SQLite） |
| `SCHEDULER_AGENT_TOKEN` | 随机生成，与 Agent 端一致 |

---

## 7. 前置依赖

| 依赖 | 开发 | 测试 | 生产 |
|------|------|------|------|
| Python 3.10+ | 必须 | 必须 | 必须 |
| SQLite | 内置 (无需安装) | 内置 | — |
| PostgreSQL | — | 可选 | 推荐 |
| Redis | 可选 | 可选 | 可选 |
| LLM API Key | 可选 (Mock 模式) | 可选 (Mock 模式) | 必须 |
