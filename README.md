# Content Hub

> 面向开发者的内容自动化工作流引擎。
>
> 采集 → 处理 → 审核 → 发布，像搭积木一样构建你的内容流水线。

## 一句话介绍

Content Hub 帮助开发者从多个平台（X / YouTube / Instagram / RSS 等）自动采集内容，经过去重、翻译、格式化等处理后，聚合到一个中心面板进行审核，最终分发到你的博客、社交账号或其他渠道。

## 适用场景

- **个人自媒体**：自动追踪行业大 V 动态，翻译/改写后发布到自己的频道
- **跨境内容运营**：抓取外文内容，自动翻译并适配本地语境后发布
- **信息聚合站**：从多个信源抓取内容，建立自己的垂直领域资讯站
- **自动化营销**：监控品牌关键词，自动生成评论或二次传播内容

## 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                      Content Hub 核心                         │
│                    （platform / 调度中心）                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │   调度引擎    │  │   Web 控制台  │  │   内容仓库    │       │
│  │ Scheduler    │  │  Frontend    │  │   Blog DB    │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
└─────────────────────────────────────────────────────────────┘
         ↑                      ↓                      ↓
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   数据源插件      │    │   处理插件       │    │   发布插件       │
│  ado_repost     │ →  │  去重/翻译/格式化 │ →  │  博客/社交平台   │
│  (X/YouTube/    │    │  (processors)    │    │  (publishing)   │
│   Instagram/    │    │                 │    │                 │
│   RSS)          │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         ↑                                              ↓
┌─────────────────┐                            ┌─────────────────┐
│   辅助 Agent     │                            │   输出目标       │
│  comment_agent  │ ←──────────────────────────│  你的博客        │
│  (自动评论/互动) │                            │  社交账号        │
│                 │                            │  邮件/通知      │
└─────────────────┘                            └─────────────────┘
```

## 核心模块

| 模块 | 路径 | 职责 | 状态 |
|------|------|------|------|
| **调度中心** | `apps/platform/scheduler_center` | 工作流编排、定时任务、Agent 调度 | 🟡 重构中 |
| **Web 控制台** | `apps/platform/frontend` | 内容审核、规则配置、运行监控 | 🟢 可用 |
| **内容仓库** | `apps/platform/blog.db` | 聚合内容的存储与 CRUD | 🟢 可用 |
| **采集器** | `apps/ado_repost` | 多平台内容抓取与初步处理 | 🟢 可用 |
| **评论 Agent** | `apps/comment_agent` | 自动评论与互动 | 🟡 待接入调度 |
| **共享记忆** | `libs/shared_memory` | 跨模块状态共享与游标持久化 | 🟢 可用 |

> 🟢 可用：功能完整，可直接使用  
> 🟡 重构中/待接入：需要调整架构边界

## 快速开始

### 1. 克隆并初始化

```bash
git clone https://github.com/duxiaokk/Content_Hub.git
cd Content_Hub

# 初始化 workspace（创建虚拟环境、安装依赖）
.\infra\scripts\bootstrap_workspace.ps1
```

### 2. 启动核心平台

```bash
.\infra\scripts\start_content_hub.ps1
```

平台默认运行在 http://localhost:8000，前端面板在 http://localhost:8000/dashboard

### 3. 配置数据源并运行采集

编辑 `apps/ado_repost/config.yaml`，启用你需要的数据源：

```yaml
fetchers:
  lookback_hours: 24
  persist_cursors: true
  x_enabled: true
  youtube_enabled: true
  youtube_channel_id: "UCxxxxxx"
  youtube_api_key: "YOUR_API_KEY"
```

运行采集：

```bash
cd apps/ado_repost/src
$env:PYTHONPATH='src'
py -m content_bridge.main --config ../config.yaml
```

采集结果会写入 `data/run_result.json`，同时自动同步到 platform 的内容仓库。

### 4. 在控制台审核并发布

打开 Web 控制台 → 进入"待审核" → 查看采集到的内容 → 确认后触发发布工作流。

## 工作流示例

```yaml
# 示例：每日自动采集并发布流程
workflow:
  name: "daily_content_pipeline"
  trigger:
    type: cron
    expression: "0 9 * * *"  # 每天早上 9 点
  steps:
    - name: fetch
      plugin: ado_repost
      config:
        sources: [x, youtube, rss]
        lookback_hours: 24
    - name: process
      plugin: content_processor
      config:
        dedup: true
        translate: zh-CN
        format: markdown
    - name: review
      plugin: human_review
      config:
        timeout_minutes: 60  # 等待人工审核，超时则跳过
    - name: publish
      plugin: blog_publisher
      config:
        target: my_blog
        draft: false
```

## 扩展开发

Content Hub 采用插件化架构，你可以开发自己的插件：

| 插件类型 | 开发文档 | 示例 |
|---------|---------|------|
| 数据源插件 | `docs/plugins/source.md` | `ado_repost` |
| 处理器插件 | `docs/plugins/processor.md` | `processors/` |
| 发布插件 | `docs/plugins/publisher.md` | `publishing/` |
| Agent 插件 | `docs/plugins/agent.md` | `comment_agent` |

## 路线图

- [x] 多平台内容采集（X / YouTube / Instagram / RSS）
- [x] 内容处理流水线（去重、翻译、格式化）
- [x] Web 控制台与内容审核
- [x] 共享记忆池与游标持久化
- [ ] 工作流可视化编排器（前端拖拽配置）
- [ ] 发布插件生态（WordPress、Twitter、Discord 等）
- [ ] 多租户与权限隔离
- [ ] REST API 对外开放

## 技术栈

- **后端**：Python 3.11 + FastAPI + SQLAlchemy + apscheduler
- **前端**：React + Ant Design
- **数据库**：SQLite（开发）/ PostgreSQL（生产）
- **消息/缓存**：Redis（可选）/ SQLite（内嵌）
- **部署**：Docker Compose / PowerShell 脚本

## 开发约定

- 新的总项目根目录：`D:\Python\content_hub`（开发环境）
- 推荐启动顺序：platform → comment_agent → ado_repost
- 所有新开发优先使用 `libs/shared_memory`
- `libs/shared_mempool` 为历史副本，将逐步合并移除

## License

MIT
