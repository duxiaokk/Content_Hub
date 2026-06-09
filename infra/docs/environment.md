# Content Hub 环境变量与配置说明

## 1. 文档目的

本文档用于说明 Content Hub 工作区当前的配置入口，重点覆盖：

- 哪些配置是工作区内多个服务共用的
- 哪些配置只属于某一个服务
- 哪些配置当前不在 `.env` 中，而在其他配置文件中

当前仓库仍处于迁移阶段，所以配置方式还没有完全统一。  
这份文档的目标不是“宣称已经标准化”，而是先把现状讲清楚。

## 2. 当前配置来源

目前工作区中的配置主要来自 3 类来源：

1. `.env` 或 `.env.example`
   - 主要用于 `platform` 和 `comment_agent`
   - `ado_repost` 也使用部分环境变量

2. `config.yaml`
   - 当前主要由 `ado_repost` 使用
   - 用于抓取器和处理器相关配置

3. 启动脚本注入的运行时变量
   - 例如 `PYTHONPATH`
   - 这类变量不一定出现在 `.env` 中

## 3. 工作区共享配置

以下配置项在多个服务之间存在明显关联，应优先理解为“工作区级共享配置”。

### 3.1 调度中心配置

用于服务向调度中心注册，或与调度系统对接。

| 配置项 | 说明 | 当前出现位置 |
|------|------|------|
| `SCHEDULER_CENTER_URL` | 调度中心地址 | `platform`、`comment_agent`、`ado_repost` 相关代码 |
| `SCHEDULER_INTERNAL_TOKEN` | 调度中心内部鉴权令牌 | `platform` `.env.example`，并被其他服务兼容读取 |

说明：

- `comment_agent` 和 `ado_repost` 都会兼容读取 `SCHEDULER_INTERNAL_TOKEN`
- 这说明当前系统中存在统一调度或统一内部鉴权约定

### 3.2 共享内存 / 共享存储配置

用于多服务复用共享库能力。

| 配置项 | 说明 |
|------|------|
| `MEMPOOL_NAMESPACE` | 评论服务使用的共享空间命名 |
| `MEMPOOL_REDIS_URL` | Redis 地址 |
| `MEMPOOL_REDIS_KEY_PREFIX` | Redis key 前缀 |
| `MEMPOOL_SQLITE_PATH` | 本地 SQLite 存储路径 |
| `MEMPOOL_DEFAULT_TTL_SECONDS` | 默认过期时间 |
| `SHARED_MEMORY_NAMESPACE` | ADO 服务共享存储命名空间，历史文档中出现 |
| `SHARED_MEMORY_REDIS_URL` | ADO 服务共享 Redis 地址，历史文档中出现 |
| `SHARED_MEMORY_REDIS_KEY_PREFIX` | ADO 服务共享前缀，历史文档中出现 |
| `SHARED_MEMORY_SQLITE_PATH` | ADO 服务本地共享 SQLite 路径，历史文档中出现 |

说明：

- 当前共享能力相关命名还没有完全统一
- `comment_agent` 倾向使用 `MEMPOOL_*`
- `ado_repost` 相关文档中还保留 `SHARED_MEMORY_*`

这正是后续需要收敛的地方。

### 3.3 Redis 配置

| 配置项 | 说明 |
|------|------|
| `REDIS_URL` | 平台服务 Redis 地址 |
| `MEMPOOL_REDIS_URL` | 评论服务共享存储 Redis 地址 |
| `SHARED_MEMORY_REDIS_URL` | ADO 相关共享存储 Redis 地址 |

说明：

- 虽然都指向 Redis，但当前不同服务的命名方式还不一致
- 后续应统一成一套工作区可复用的命名规范

## 4. platform 配置

`platform` 当前配置来源主要是 [apps/platform/.env.example](D:/Python/content_hub/apps/platform/.env.example)。

### 4.1 数据库配置

| 配置项 | 说明 |
|------|------|
| `DATABASE_URL` | 主数据库连接地址 |

当前示例默认使用 SQLite，例如：

```text
DATABASE_URL=sqlite:///./blog.db
```

后续也预留了 PostgreSQL / MySQL 形式。

### 4.2 安全与认证配置

| 配置项 | 说明 |
|------|------|
| `SECRET_KEY` | JWT 或认证相关签名密钥 |
| `ALGORITHM` | 签名算法 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 访问令牌过期分钟数 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | 刷新令牌过期天数 |
| `ADMIN_USERNAME` | 默认管理员用户名 |

### 4.3 平台业务配置

| 配置项 | 说明 |
|------|------|
| `TECH_TAGS` | 平台展示使用的技术标签列表 |

### 4.4 AI / LLM 配置

| 配置项 | 说明 |
|------|------|
| `LLM_API_KEY` | 大模型 API Key |
| `LLM_BASE_URL` | 大模型服务地址 |
| `LLM_MODEL` | 模型名称 |
| `MOCK_LLM` | 是否使用 mock 模式 |

说明：

- 这些配置表明 `platform` 当前已考虑接入大模型能力
- 生产环境下这类密钥不应直接写入仓库

### 4.5 内部服务认证

| 配置项 | 说明 |
|------|------|
| `INTERNAL_AGENT_TOKEN` | 平台与内部 Agent 通信使用的令牌 |

### 4.6 运行与观测配置

| 配置项 | 说明 |
|------|------|
| `REDIS_URL` | 平台 Redis 地址 |
| `LOG_LEVEL` | 日志级别 |
| `LOG_DIR` | 日志目录 |
| `OTEL_ENABLED` | 是否启用 OpenTelemetry |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP 上报地址 |
| `OTEL_SERVICE_NAME` | 观测服务名 |
| `METRICS_ENABLED` | 是否启用指标采集 |
| `LOG_FORMAT` | 日志格式 |
| `GRAFANA_USER` | Grafana 用户名 |
| `GRAFANA_PASSWORD` | Grafana 密码 |

## 5. comment_agent 配置

`comment_agent` 当前配置来源主要是 [apps/comment_agent/.env.example](D:/Python/content_hub/apps/comment_agent/.env.example)。

### 5.1 基础配置

| 配置项 | 说明 |
|------|------|
| `APP_NAME` | 服务名称 |
| `DATABASE_URL` | 评论服务数据库地址 |

### 5.2 评论业务配置

| 配置项 | 说明 |
|------|------|
| `DEFAULT_REPLY_DELAY_SECONDS` | 默认回复延迟 |
| `DEFAULT_ARTICLE_REPLY_LIMIT` | 单篇文章默认回复数量限制 |

### 5.3 内部认证与注册配置

| 配置项 | 说明 |
|------|------|
| `COMMENT_AGENT_INTERNAL_TOKEN` | 评论服务内部鉴权令牌 |
| `COMMENT_AGENT_BASE_URL` | 服务对外基址，用于向调度中心注册 |
| `COMMENT_AGENT_KEY` | 注册时的 agent key |
| `COMMENT_AGENT_NAME` | 注册时的 agent name |
| `SCHEDULER_CENTER_URL` | 调度中心地址 |
| `SCHEDULER_INTERNAL_TOKEN` | 兼容读取的内部令牌 |

说明：

- 从代码看，`comment_agent` 启动时可能会尝试向调度中心自动注册
- 如果未配置 `SCHEDULER_CENTER_URL` 或 `COMMENT_AGENT_BASE_URL`，则不会执行注册

### 5.4 CORS 配置

| 配置项 | 说明 |
|------|------|
| `COMMENT_AGENT_CORS_ALLOW_ORIGINS` | 允许跨域访问的来源列表 |

“CORS” 可以先简单理解成“浏览器是否允许别的前端页面来调用这个服务”。

### 5.5 共享存储配置

| 配置项 | 说明 |
|------|------|
| `MEMPOOL_NAMESPACE` | 共享空间名称 |
| `MEMPOOL_REDIS_URL` | Redis 地址 |
| `MEMPOOL_REDIS_KEY_PREFIX` | Redis key 前缀 |
| `MEMPOOL_SQLITE_PATH` | SQLite 本地存储文件 |
| `MEMPOOL_DEFAULT_TTL_SECONDS` | 默认过期时间 |

## 6. ado_repost 配置

`ado_repost` 当前配置来源不止一种：

- [apps/ado_repost/.env.example](D:/Python/content_hub/apps/ado_repost/.env.example)
- [apps/ado_repost/.env](D:/Python/content_hub/apps/ado_repost/.env)
- [apps/ado_repost/config.yaml](D:/Python/content_hub/apps/ado_repost/config.yaml)
- 运行时环境变量

### 6.1 发布相关配置

| 配置项 | 说明 |
|------|------|
| `ADO_PUBLISH_ENABLED` | 是否启用发布 |
| `ADO_PUBLISH_ENDPOINT_URL` | 发布目标地址 |
| `ADO_INTERNAL_TOKEN` | 发布时使用的内部令牌 |
| `ADO_PUBLISH_TIMEOUT_SECONDS` | 发布请求超时时间 |
| `ADO_SOURCE_PLATFORM` | 当前来源平台标识 |

### 6.2 Agent 运行与注册配置

从代码中还能确认以下配置：

| 配置项 | 说明 |
|------|------|
| `ADO_REPOST_INTERNAL_TOKEN` | ADO 服务内部鉴权令牌 |
| `ADO_REPOST_BASE_URL` | 服务基址，用于注册 |
| `ADO_REPOST_AGENT_KEY` | 注册时的 agent key |
| `ADO_REPOST_AGENT_NAME` | 注册时的 agent name |
| `SCHEDULER_CENTER_URL` | 调度中心地址 |
| `SCHEDULER_INTERNAL_TOKEN` | 兼容读取的内部令牌 |

说明：

- `ado_repost` 也会尝试向调度中心注册
- 若缺少调度中心地址或服务基址，则不会执行注册

### 6.3 YAML 配置

`ado_repost` 目前还有一部分核心配置不在 `.env` 中，而在 `config.yaml` 中。

当前可见配置包括：

| 配置项 | 说明 |
|------|------|
| `fetchers.lookback_hours` | 回看抓取时间窗口 |
| `fetchers.persist_cursors` | 是否保存增量抓取游标 |
| `fetchers.max_retries` | 抓取最大重试次数 |
| `fetchers.timeout_seconds` | 抓取超时时间 |
| `fetchers.x_enabled` | 是否启用 X 抓取 |
| `fetchers.youtube_enabled` | 是否启用 YouTube 抓取 |
| `fetchers.instagram_enabled` | 是否启用 Instagram 抓取 |
| `fetchers.youtube_api_key` | YouTube API Key |
| `fetchers.youtube_channel_id` | YouTube Channel ID |

说明：

- 这说明 `ado_repost` 当前采用“环境变量 + YAML 混合配置”的方式
- 后续是否继续保留这种方式，需要在阶段二或阶段三再评估

## 7. 运行时注入配置

除了 `.env` 和 `config.yaml`，当前还有一些配置是通过启动脚本在运行时注入的。

### 7.1 `PYTHONPATH`

当前脚本会为不同服务注入不同源码路径：

- `comment_agent` 注入 `libs/shared_memory/src`
- `ado_repost` 注入 `apps/ado_repost/src` 和 `libs/shared_memory/src`

这说明当前工作区的一部分依赖关系，还依赖脚本显式指定源码搜索路径。

## 8. 当前配置问题

当前配置系统存在以下明显问题：

1. 配置入口不统一
   - 有的服务主要依赖 `.env`
   - 有的服务同时依赖 `.env` 和 YAML

2. 命名不统一
   - `MEMPOOL_*` 与 `SHARED_MEMORY_*` 并存
   - Redis 相关命名也没有统一

3. 仍存在本机路径耦合风险
   - 某些依赖声明仍引用本机绝对路径

4. 密钥管理尚未收敛
   - 示例文件中已出现 API Key 类字段
   - 后续需要更明确地区分示例值与真实密钥注入方式

## 9. 当前建议

在配置系统正式收敛前，建议遵循以下规则：

1. 新增配置时，优先放入 `.env.example`
2. 仅在确实需要分层结构时再使用 YAML
3. 不要继续引入新的绝对路径配置
4. 尽量向统一命名收敛，而不是继续增加新的前缀体系

## 10. 后续待补

当前文档已经覆盖主要配置入口，但仍有后续工作：

- 为工作区补统一配置命名规范
- 区分开发、测试、生产环境配置策略
- 清理示例文件中的敏感信息和历史字段
