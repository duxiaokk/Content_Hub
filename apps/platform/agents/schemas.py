"""Agent 标准 I/O 协议

定义 5 类 Agent 的请求/响应 schema：
  - PlannerAgent: 任务拆解
  - DataProcessorAgent: 数据提取/清洗/预处理
  - ToolCallingAgent: 外部工具调用（搜索/翻译等）
  - ContentGeneratorAgent: 内容生成
  - AggregatorAgent: 结果聚合
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# =========================================================================
# 通用协议
# =========================================================================


class AgentHeartbeat(BaseModel):
    """Agent 心跳负载信息。"""
    agent_key: str
    status: Literal["healthy", "degraded", "unavailable"] = "healthy"
    current_load: int = Field(default=0, ge=0, description="当前并发请求数")
    max_load: int = Field(default=10, ge=1, description="最大并发请求数")
    avg_latency_ms: float = Field(default=0.0, ge=0, description="最近平均延迟(ms)")
    error_count: int = Field(default=0, ge=0, description="最近错误数")
    uptime_seconds: float = Field(default=0.0, ge=0, description="运行时间(秒)")


class AgentErrorReport(BaseModel):
    """Agent 异常上报。"""
    agent_key: str
    error_type: str
    error_message: str
    task_id: str | None = None
    trace_id: str | None = None
    retry_recommended: bool = False
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    context: dict[str, Any] = Field(default_factory=dict)


# =========================================================================
# Planner Agent
# =========================================================================


class PlannerInput(BaseModel):
    """Planner Agent 输入。"""
    intent: str = Field(description="用户的自然语言需求描述")
    context: dict[str, Any] = Field(default_factory=dict, description="上下文数据")
    available_capabilities: list[dict[str, Any]] = Field(default_factory=list, description="可用 Agent 能力列表")
    constraints: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None


class PlannerTask(BaseModel):
    """Plan 中的单个任务。"""
    task_key: str
    task_type: str
    description: str = ""
    depends_on: list[str] = Field(default_factory=list)
    input_payload: dict[str, Any] = Field(default_factory=dict)
    max_retries: int = 2
    retry_delay_seconds: float = 3.0
    timeout_seconds: float | None = None
    condition: str | None = None
    branch_on: dict[str, str] = Field(default_factory=dict)
    sub_tasks: list["PlannerTask"] = Field(default_factory=list)


class PlannerOutput(BaseModel):
    """Planner Agent 输出的执行计划。"""
    plan_id: str
    intent: str
    tasks: list[PlannerTask]
    estimated_duration_seconds: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# =========================================================================
# Data Processor Agent
# =========================================================================


class DataProcessorInput(BaseModel):
    """Data Processor Agent 输入。"""
    operation: Literal["extract", "transform", "clean", "enrich", "validate", "summarize"] = "transform"
    source_type: str = Field(default="text", description="text/json/csv/html/markdown/sql")
    data: dict[str, Any] = Field(default_factory=dict)
    schema_hint: dict[str, Any] | None = None  # 期望输出结构
    rules: list[dict[str, Any]] = Field(default_factory=list)  # 转换规则
    context: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None


class DataProcessorOutput(BaseModel):
    """Data Processor Agent 输出。"""
    operation: str
    result: dict[str, Any] = Field(default_factory=dict)
    processed_count: int = 0
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# =========================================================================
# Tool Calling Agent
# =========================================================================


class ToolDefinition(BaseModel):
    """工具定义。"""
    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class ToolCallRequest(BaseModel):
    """工具调用请求。"""
    tool_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class ToolCallResult(BaseModel):
    """工具调用结果。"""
    tool_name: str
    success: bool
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    duration_ms: float = 0.0


class ToolCallingInput(BaseModel):
    """Tool Calling Agent 输入。"""
    intent: str = Field(description="用户想要执行的操作")
    available_tools: list[ToolDefinition] = Field(default_factory=list)
    tool_calls: list[ToolCallRequest] | None = None  # 预定义调用；None 则由 LLM 自动选择
    context: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None


class ToolCallingOutput(BaseModel):
    """Tool Calling Agent 输出。"""
    results: list[ToolCallResult] = Field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# =========================================================================
# Content Generator Agent
# =========================================================================


class ContentGeneratorInput(BaseModel):
    """Content Generator Agent 输入。"""
    content_type: str = Field(default="blog_post", description="blog_post/outline/summary/social_media/email")
    topic: str = ""
    instructions: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    style: str = Field(default="professional", description="professional/casual/technical/witty")
    target_audience: str = ""
    word_count_range: tuple[int, int] | None = None  # (min, max)
    reference_materials: list[dict[str, Any]] = Field(default_factory=list)
    trace_id: str | None = None


class ContentGeneratorOutput(BaseModel):
    """Content Generator Agent 输出。"""
    content_type: str
    title: str = ""
    content: str = ""
    outline: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    token_count: int = 0


# =========================================================================
# Aggregator Agent
# =========================================================================


class TaskResultItem(BaseModel):
    """单个子任务的结果。"""
    task_key: str
    task_type: str
    status: str
    output: dict[str, Any] = Field(default_factory=dict)
    artifact_ref: str | None = None
    error: str | None = None


class AggregatorInput(BaseModel):
    """Aggregator Agent 输入。"""
    run_id: str
    intent: str
    task_results: list[TaskResultItem]
    aggregation_mode: Literal["merge", "summarize", "vote", "compose"] = "merge"
    trace_id: str | None = None


class AggregatorOutput(BaseModel):
    """Aggregator Agent 输出。"""
    run_id: str
    success: bool
    aggregated_result: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    error: str | None = None
