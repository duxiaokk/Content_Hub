"""编排层 Pydantic 协议

定义 Planner 输入/输出，Aggregator 输入/输出，Run/Task 响应模型。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# =========================================================================
# Planner 协议
# =========================================================================


class AgentCapability(BaseModel):
    """Agent 能力描述（供 Planner 使用）。"""
    agent_key: str
    name: str
    task_types: list[str] = Field(default_factory=list)
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class PlannerRequest(BaseModel):
    """Planner 输入协议。"""
    intent: str = Field(description="用户的自然语言需求描述")
    context: dict[str, Any] = Field(default_factory=dict, description="上下文数据（已有文章、平台信息等）")
    available_capabilities: list[AgentCapability] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict, description="约束条件（超时、并行度等）")
    trace_id: str | None = None


class PlanTask(BaseModel):
    """执行计划中的单个任务。"""
    task_key: str = Field(description="任务唯一标识（在 run 内）")
    task_type: str = Field(description="对应的 SchedulerTask task_type")
    description: str = ""
    depends_on: list[str] = Field(default_factory=list, description="依赖的 task_key 列表")
    input_payload: dict[str, Any] = Field(default_factory=dict)
    max_retries: int = 2
    retry_delay_seconds: float = 3.0
    timeout_seconds: float | None = None


class ExecutionPlan(BaseModel):
    """Planner 输出的执行计划。"""
    plan_id: str
    intent: str
    tasks: list[PlanTask]
    estimated_duration_seconds: float | None = None
    trace_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlannerResponse(BaseModel):
    """Planner 完成响应。"""
    success: bool
    plan: ExecutionPlan | None = None
    error: str | None = None
    trace_id: str | None = None


# =========================================================================
# Aggregator 协议
# =========================================================================


class TaskResult(BaseModel):
    """单个任务的结果工件。"""
    task_key: str
    task_type: str
    status: str
    output: dict[str, Any] = Field(default_factory=dict)
    artifact_ref: str | None = None
    error: str | None = None


class AggregatorRequest(BaseModel):
    """Aggregator 输入协议。"""
    run_id: str
    intent: str
    task_results: list[TaskResult]
    trace_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AggregatorResponse(BaseModel):
    """Aggregator 输出。"""
    success: bool
    run_id: str
    status: str
    summary: str | None = None
    aggregated_result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    trace_id: str | None = None


# =========================================================================
# 编排 Run 协议
# =========================================================================


class RunSubmitRequest(BaseModel):
    """提交编排运行请求。"""
    name: str | None = None
    intent: str = Field(min_length=1, max_length=2000)
    context: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None
    use_planner: bool = True  # False = 直接运行静态 DAG
    plan: ExecutionPlan | None = None  # 静态 DAG（use_planner=False 时）


class RunSubmitResponse(BaseModel):
    """提交运行响应。"""
    run_id: str
    trace_id: str
    status: str
    plan: ExecutionPlan | None = None
    total_tasks: int
    created_at: datetime


class RunStatusResponse(BaseModel):
    """运行状态响应。"""
    run_id: str
    trace_id: str
    name: str | None
    status: str
    total_tasks: int
    succeeded_tasks: int
    failed_tasks: int
    skipped_tasks: int
    task_statuses: dict[str, str]  # task_key → status
    result: dict[str, Any] | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None = None


class RunListItem(BaseModel):
    """运行列表项。"""
    run_id: str
    trace_id: str
    name: str | None
    status: str
    total_tasks: int
    created_at: datetime


class RunListResponse(BaseModel):
    """运行列表。"""
    items: list[RunListItem]
    total: int


# =========================================================================
# Planner 独立任务类型
# =========================================================================


class PlannerTaskRequest(BaseModel):
    """发送给 Planner Agent 的任务 payload。"""
    intent: str
    context: dict[str, Any] = Field(default_factory=dict)
    available_capabilities: list[dict[str, Any]] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    plan_id: str
    trace_id: str | None = None


class AggregatorTaskRequest(BaseModel):
    """发送给 Aggregator Agent 的任务 payload。"""
    run_id: str
    intent: str
    task_results: list[dict[str, Any]] = Field(default_factory=list)
    trace_id: str | None = None
