# T011: workflow_trace_idempotency — Workflow Engine：运行轨迹 + 幂等控制

## 目标（一句话）
为每个工作流运行记录完整的运行轨迹（每步耗时/成功数/失败数/token 成本），并实现幂等控制防止重复发布。

## 依赖
- 前置任务：T010（radar_pipeline 已可运行）
- 阻塞项：无

## 输入文件（请先阅读）
- Workflow service：[apps/workflow_engine/api/service.py](file:///D:/Python/content_hub/apps/workflow_engine/api/service.py)
- 现有 observability：[apps/workflow_engine/runtime/observability.py](file:///D:/Python/content_hub/apps/workflow_engine/runtime/observability.py)
- 数据模型：`workflow_run` 表（架构文档 7.1 节定义；需在 T001 中确认已建表）
- 任务清单：`content_hub_mvp_task_breakdown.md` 第 4.2 节第 5、6 项

## 输出要求（具体、可检查）

### 1. workflow_run 运行轨迹记录
在 WorkflowService 中，每次 pipeline 执行前后：

**入库时机**：
- 开始时：插入 `workflow_run` 记录（status=running）。
- 每步完成时：更新 trace_payload JSON 字段。
- 结束时：更新 status=success/failed，记录 finished_at。

**trace_payload 结构**：
```json
{
  "steps": [
    {
      "name": "fetch",
      "status": "success",
      "started_at": "2025-06-01T09:00:01",
      "finished_at": "2025-06-01T09:00:15",
      "duration_ms": 14000,
      "items_in": 0,
      "items_out": 45,
      "error": null
    },
    {
      "name": "dedup_filter",
      "status": "success",
      "started_at": "2025-06-01T09:00:15",
      "finished_at": "2025-06-01T09:00:16",
      "duration_ms": 1000,
      "items_in": 45,
      "items_out": 12,
      "error": null
    }
  ],
  "total_token_cost": 45000,
  "total_elapsed_ms": 65000
}
```

**汇总字段**：
- `items_total`：总输入数
- `items_succeeded`：成功处理数
- `items_failed`：失败数
- `error_summary`：错误摘要（如某步骤失败原因）

### 2. 幂等控制
实现同一内容不重复发布：

**dedup_key 机制**：
- 每篇 content_item 在入库时已有 `dedup_key`（如 `{source_type}:{external_id}`）。
- 每次发布前，查询 `publish_records` 表：
  ```sql
  SELECT 1 FROM publish_records
  WHERE content_item_id = ? AND target_type = ? AND status = 'success'
  ```
- 已成功发布的，标记为 `"skipped"`，不重复发布。

**run_id 幂等**：
- 同一 `run_id` 的发布操作不重复执行（在 `publish_records` 中 `(run_id, content_item_id, target_type)` 唯一约束或查询前置判断）。

### 3. Observability 扩展
在 [apps/workflow_engine/runtime/observability.py](file:///D:/Python/content_hub/apps/workflow_engine/runtime/observability.py) 中新增：
- `log_step_start(run_id, step_name)` — 记录步骤开始
- `log_step_end(run_id, step_name, result)` — 记录步骤结束
- `log_token_usage(run_id, tokens)` — 累计 token 消耗

### 4. 建表补充（如 T001 未包含 workflow_run）
如果 `workflow_run` 表在 T001 中未建，需要补充：

```sql
CREATE TABLE workflow_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_name VARCHAR(64) NOT NULL,
    trigger_type VARCHAR(32) NOT NULL DEFAULT 'manual',
    status VARCHAR(32) NOT NULL DEFAULT 'running',
    started_at DATETIME NOT NULL,
    finished_at DATETIME,
    items_total INTEGER DEFAULT 0,
    items_succeeded INTEGER DEFAULT 0,
    items_failed INTEGER DEFAULT 0,
    error_summary TEXT,
    trace_payload JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

## 验收标准（必须全部勾选才算完成）
- [ ] 每次 radar_pipeline 运行生成一条 `workflow_run` 记录
- [ ] `trace_payload` 包含每步的耗时、输入输出数和错误信息
- [ ] `total_token_cost` 正确累加所有 LLM 调用的 token 消耗
- [ ] pipeline 正常结束：`workflow_run.status = "success"`
- [ ] pipeline 某步失败：`workflow_run.status = "failed"` 且 `error_summary` 有内容
- [ ] 同一 `(content_item_id, target_type)` 已成功发布过的，不会重复发布
- [ ] 幂等控制日志可追溯（skipped 记录可查）
- [ ] 更新 [codex_board.md](file:///D:/Python/content_hub/codex_board.md) 标记 T011 为完成
