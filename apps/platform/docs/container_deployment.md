# 容器部署文档 (Container Deployment Guide)

> P1 容器化改造 — 使用 Docker Compose 一键部署全部服务。

---

## 1. 前置条件

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| Docker | 24.0+ | 容器运行时 |
| Docker Compose | v2.20+ | `docker compose` (非 docker-compose v1) |
| Git | 2.0+ | 拉取代码 |
| 磁盘空间 | 2GB+ | 镜像 + 数据卷 |

---

## 2. 快速开始

```bash
# 1. 克隆项目
git clone <repo-url> personal-blog
cd personal-blog

# 2. 配置环境变量（可选，默认值可运行）
cp .env.example .env
# 编辑 .env，至少设置 SECRET_KEY 和 LLM_API_KEY

# 3. 构建并一键启动全部服务
docker compose up -d

# 4. 等待所有服务健康检查通过
docker compose ps

# 5. 访问
#    首页:    http://localhost:8000
#    Swagger: http://localhost:8000/docs
#    调度中心: http://localhost:8010/health
```

---

## 3. 服务清单

| 服务 | 容器名 | 端口 | 外部访问 | 说明 |
|------|--------|------|----------|------|
| PostgreSQL | `blog-postgres` | 5432 | 仅开发 | 数据库 |
| Redis | `blog-redis` | 6379 | 仅开发 | 缓存 + 队列 |
| 平台主服务 | `blog-platform` | 8000 | **是** | 用户入口 |
| 调度中心 API | `blog-scheduler-api` | 8010 | 内部 | 任务管理 HTTP API |
| Dispatcher | `blog-scheduler-dispatcher` | — | 内部 | 任务调度引擎 |
| Ingest Worker | `blog-scheduler-ingest` | — | 内部 | Redis→DB 落库 (可选) |
| Audit Agent | `blog-audit-agent` | — | 内部 | 草稿审核 Agent |

---

## 4. 常用命令

### 4.1 启动与停止

```bash
# 启动全部服务
docker compose up -d

# 启动全部 + 可选服务 (Ingest Worker)
docker compose --profile ingest up -d

# 重新构建并启动
docker compose up -d --build

# 停止全部服务
docker compose down

# 停止并清理数据卷（危险！）
docker compose down -v
```

### 4.2 查看状态

```bash
# 查看所有容器状态
docker compose ps

# 查看特定服务状态
docker compose ps platform
docker compose ps scheduler-api

# 检查健康状态
docker inspect blog-platform --format='{{json .State.Health}}' | python -m json.tool
```

### 4.3 日志

```bash
# 查看所有服务日志
docker compose logs -f

# 查看特定服务日志（最近 100 行）
docker compose logs --tail=100 platform

# 查看特定服务日志（跟随输出）
docker compose logs -f scheduler-dispatcher

# 查看最近 10 分钟日志
docker compose logs --since=10m
```

### 4.4 重启

```bash
# 重启特定服务
docker compose restart platform
docker compose restart scheduler-api

# 重启全部
docker compose restart
```

### 4.5 数据清理

```bash
# 清理停止的容器、网络（保留数据卷）
docker compose down

# 彻底清理（保留镜像）
docker compose down -v

# 清理未使用的镜像和构建缓存
docker image prune -a
docker builder prune
```

---

## 5. 环境变量覆盖

docker-compose.yml 中内置了所有默认值，可通过以下方式覆盖：

### 方式一：`.env` 文件（推荐）

```bash
# .env
SECRET_KEY=my-production-secret-key
LLM_API_KEY=sk-real-key-here
POSTGRES_PASSWORD=strong-db-password
PLATFORM_PORT=80
```

### 方式二：命令行临时覆盖

```bash
SECRET_KEY=temp-key docker compose up -d
```

### 方式三：Docker Compose 覆盖文件

```bash
# docker-compose.prod.yml
services:
  platform:
    environment:
      MOCK_LLM: "false"
      LOG_LEVEL: WARNING
```

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## 6. 网络架构

```
外部请求 ─→ 8000 (host) ─→ blog-platform:8000
                              │
                              ├──→ blog-net ──→ postgres:5432
                              ├──→ blog-net ──→ redis:6379
                              └──→ blog-net ──→ scheduler-api:8010
                                                    │
                          ┌─────────────────────────┤
                          ▼                         ▼
              scheduler-dispatcher          audit-agent:8000
              (内部，无端口暴露)             (内部，无端口暴露)
```

- 所有服务在 `blog-net` 桥接网络内通过**容器名**互相访问
- 只有 `blog-platform` 的 8000 端口对外暴露
- PostgreSQL / Redis 端口默认暴露（开发便利），生产环境应注释掉 `ports` 配置

---

## 7. 数据持久化

| 数据卷 | 用途 | 清理命令 |
|--------|------|----------|
| `blog-postgres-data` | PostgreSQL 数据库文件 | `docker volume rm blog-postgres-data` |
| `blog-redis-data` | Redis 持久化 (AOF) | `docker volume rm blog-redis-data` |
| `blog-scheduler-data` | 调度中心 SQLite / 日志 | `docker volume rm blog-scheduler-data` |
| `blog-platform-uploads` | 用户上传图片 (`/app/image`) | `docker volume rm blog-platform-uploads` |
| `blog-platform-drafts` | Agent 草稿 Markdown | `docker volume rm blog-platform-drafts` |
| `blog-platform-logs` | 平台日志文件 | `docker volume rm blog-platform-logs` |

### 备份数据库

```bash
# PostgreSQL
docker exec blog-postgres pg_dump -U blog_user blog_db > backup_$(date +%Y%m%d).sql

# 恢复
cat backup_20260606.sql | docker exec -i blog-postgres psql -U blog_user -d blog_db
```

---

## 8. 资源限制

每个服务已配置 CPU / 内存限制：

| 服务 | CPU Limit | Memory Limit |
|------|-----------|--------------|
| PostgreSQL | 2.0 | 1 GB |
| Redis | 0.5 | 256 MB |
| 平台主服务 | 2.0 | 1 GB |
| 调度中心 API | 1.0 | 512 MB |
| Dispatcher | 1.0 | 512 MB |
| Ingest Worker | 0.5 | 256 MB |
| Audit Agent | 1.0 | 512 MB |

可通过环境变量调整：

```bash
# 增加平台服务内存限制
PLATFORM_MEMORY_LIMIT=2G docker compose up -d
```

---

## 9. 故障排查

### 9.1 容器无法启动

```bash
# 查看退出日志
docker compose logs platform

# 进入容器调试
docker compose run --rm platform /bin/bash
```

### 9.2 数据库连接失败

```bash
# 检查 PostgreSQL 是否就绪
docker compose exec postgres pg_isready -U blog_user -d blog_db

# 进入数据库 shell
docker compose exec postgres psql -U blog_user -d blog_db
```

### 9.3 调度中心不健康

```bash
# 直接调用健康检查 API
curl http://localhost:8010/health
curl http://localhost:8010/ready

# 查看调度中心日志
docker compose logs scheduler-api
docker compose logs scheduler-dispatcher
```

### 9.4 重新构建

```bash
# 强制重新构建不使用缓存
docker compose build --no-cache

# 构建 + 启动
docker compose up -d --build
```

---

## 10. 生产环境建议

1. **移除开发端口暴露**：`docker-compose.prod.yml` 中注释 postgres/redis 的 `ports`
2. **使用 secrets 管理密钥**：`SECRET_KEY`, `POSTGRES_PASSWORD`, `LLM_API_KEY` 通过 Docker secrets 或 HashiCorp Vault 注入
3. **反向代理**：在 `blog-platform` 前加 Nginx / Traefik，配置 HTTPS
4. **监控**：接入 Prometheus + Grafana，配置容器资源告警
5. **日志聚合**：配置 `logging` driver 为 `fluentd` 或 `loki`
6. **资源调优**：根据实际负载调整 `deploy.resources.limits`
