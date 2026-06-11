# T017: scheduler_cron — Scheduler：定时任务配置（09:00/09:15）

## 目标（一句话）
在 scheduler_center 中新增两类定时任务：每日 09:00 触发 radar pipeline，每日 09:15 触发 daily digest pipeline。

## 依赖
- 前置任务：T016（博客发布完成）、T015（Markdown 日报完成）、T013（审核 API 完成）
- 阻塞项：依赖 workflow_engine HTTP 入口

## 输入文件（请先阅读）
- Scheduler 主入口：[apps/platform/scheduler_center/main.py](file:///D:/Python/content_hub/apps/platform/scheduler_center/main.py)
- Scheduler 配置：[apps/platform/scheduler_center/config.py](file:///D:/Python/content_hub/apps/platform/scheduler_center/config.py)
- Scheduler 路由：[apps/platform/scheduler_center/router.py](file:///D:/Python/content_hub/apps/platform/scheduler_center/router.py)
- Scheduler dispatcher：[apps/platform/scheduler_center/dispatcher.py](file:///D:/Python/content_hub/apps/platform/scheduler_center/dispatcher.py)
- Cron 依赖：需确认是否有 `APScheduler` 或类似调度库，如无可用 `asyncio` + `sleep` 简单实现
- 任务清单：`content_hub_mvp_task_breakdown.md` 第 4.6 节

## 输出要求（具体、可检查）

### 1. 新增两类标准任务类型
定义任务常量（在 config 或 schemas 中）：

```python
CONTENT_PIPELINE_RADAR = "content.pipeline.radar"
CONTENT_PIPELINE_DAILY_DIGEST = "content.pipeline.daily_digest"
```

### 2. 定时调度配置
在 [apps/platform/scheduler_center/config.py](file:///D:/Python/content_hub/apps/platform/scheduler_center/config.py) 中新增：

```python
SCHEDULED_JOBS = [
    {
        "task_type": "content.pipeline.radar",
        "cron_expression": "0 9 * * *",     # 每天 09:00
        "payload": {
            "workflow_name": "radar_pipeline",
            "sources": ["cnblogs", "bilibili", "github_trending", "reddit_ai"],
            "lookback_hours": 24,
            "limit_per_source": 20,
            "filters": {
                "keywords": ["agent", "rag", "openai", "llm"],
                "exclude_keywords": ["招聘", "广告"]
            },
            "process_options": {"rewrite_profile": "zh_tech_blog"},
            "publish_options": {"targets": ["blog"]}
        },
    },
    {
        "task_type": "content.pipeline.daily_digest",
        "cron_expression": "15 9 * * *",    # 每天 09:15
        "payload": {
            "workflow_name": "daily_digest_pipeline",
            "lookback_hours": 24,
            "publish_options": {"targets": ["digest_markdown"]}
        },
    },
]
```

### 3. 调度触发机制
实现方式：在 [apps/platform/scheduler_center/dispatcher.py](file:///D:/Python/content_hub/apps/platform/scheduler_center/dispatcher.py) 中新增 cron 调度逻辑：

**选项 A（推荐）— APScheduler**：
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()
for job_def in SCHEDULED_JOBS:
    scheduler.add_job(
        func=dispatch_task,
        trigger=CronTrigger.from_crontab(job_def["cron_expression"]),
        kwargs={"task_type": job_def["task_type"], "payload": job_def["payload"]},
        id=job_def["task_type"],
    )
scheduler.start()
```

**选项 B（最小依赖）— asyncio loop**：
```python
async def cron_loop():
    while True:
        now = datetime.now()
        if now.hour == 9 and now.minute == 0:
            await dispatch_radar()
            await asyncio.sleep(60)  # 避免同一分钟重复
        await asyncio.sleep(30)
```

### 4. dispatch_task 实现
在 dispatcher 中新增：

```python
async def dispatch_task(task_type: str, payload: dict):
    """调用 platform 的内部任务 API 触发 pipeline"""
    target_url = f"{PLATFORM_URL}/api/internal/tasks/content-pipeline/{task_type}/run"
    ...
```

实际调用：
- radar: `POST /api/internal/tasks/content-pipeline/radar/run`
- daily_digest: `POST /api/internal/tasks/content-pipeline/daily-digest/run`

### 5. 任务日志和状态查询
每次定时触发后，记录到 scheduler_center 自身的 task 表：
- `task_type`
- `status`（running / success / failure）
- `error_message`
- `created_at` / `updated_at`

提供查询 API（复用现有 router）：
- `GET /api/internal/scheduler/tasks` — 最近任务列表
- `GET /api/internal/scheduler/tasks/{id}` — 单条任务详情

### 6. 配置开关
```env
# 在 .env.example 中新增
CONTENT_HUB_SCHEDULER_ENABLED=true
```
调度器检测此配置，若为 false 则不启动 cron。

## 验收标准（必须全部勾选才算完成）
- [ ] 每天 09:00 自动触发 `content.pipeline.radar`
- [ ] 每天 09:15 自动触发 `content.pipeline.daily_digest`
- [ ] 调度触发后产生 task 记录（可查询状态）
- [ ] 调度失败时有 error_message 记录
- [ ] `CONTENT_HUB_SCHEDULER_ENABLED=false` 时调度器不启动
- [ ] `GET /api/internal/scheduler/tasks` 可查看调度历史
- [ ] 更新 [codex_board.md](file:///D:/Python/content_hub/codex_board.md) 标记 T017 为完成
