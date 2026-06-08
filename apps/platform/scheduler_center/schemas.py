from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class TaskSubmitRequest(BaseModel):
    task_type: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: Optional[str] = Field(default=None, min_length=1, max_length=128)
    max_retries: Optional[int] = Field(default=None, ge=0, le=50)
    retry_delay_seconds: Optional[float] = Field(default=None, ge=0, le=3600)


class TaskSubmitResponse(BaseModel):
    id: str
    trace_id: str
    status: str
    created_at: datetime


class TaskCancelResponse(BaseModel):
    id: str
    trace_id: str
    status: str
    cancel_requested: bool
    updated_at: datetime


class TaskAttemptResponse(BaseModel):
    id: int
    attempt_no: int
    agent: Optional[str]
    trace_id: Optional[str]
    request_url: Optional[str]
    request: Optional[dict[str, Any]]
    status: str
    http_status: Optional[int]
    response_text: Optional[str]
    error: Optional[str]
    retryable: bool
    started_at: datetime
    finished_at: Optional[datetime]


class TaskEventResponse(BaseModel):
    id: int
    trace_id: Optional[str]
    event_type: str
    from_status: Optional[str]
    to_status: Optional[str]
    attempt_no: Optional[int]
    message: Optional[str]
    created_at: datetime


class TaskDetailResponse(BaseModel):
    id: str
    idempotency_key: Optional[str]
    trace_id: Optional[str]
    task_type: str
    payload: dict[str, Any]
    status: str
    cancel_requested: bool
    max_retries: int
    retry_delay_seconds: float
    attempt_count: int
    next_run_at: Optional[datetime]
    last_agent: Optional[str]
    result: Optional[dict[str, Any]]
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime
    attempts: list[TaskAttemptResponse]
    events: list[TaskEventResponse]


class TaskLogItem(BaseModel):
    id: int
    trace_id: Optional[str]
    level: str
    message: str
    created_at: datetime


class TaskLogsResponse(BaseModel):
    items: list[TaskLogItem]
    total: int


class TaskListItem(BaseModel):
    id: str
    idempotency_key: Optional[str]
    trace_id: Optional[str]
    task_type: str
    status: str
    cancel_requested: bool
    attempt_count: int
    next_run_at: Optional[datetime]
    last_agent: Optional[str]
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime


class TaskListResponse(BaseModel):
    items: list[TaskListItem]
    total: int


class AgentRegisterRequest(BaseModel):
    agent_key: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    base_url: str = Field(min_length=1, max_length=500)
    task_types: list[str] = Field(default_factory=list)
    health_path: str = Field(default="/health", min_length=1, max_length=200)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    status: int = Field(default=1, ge=0, le=1)


class AgentItem(BaseModel):
    id: int
    agent_key: str
    name: str
    base_url: str
    task_types: list[str]
    health_path: str
    capabilities: dict[str, Any]
    status: int
    last_heartbeat_at: datetime
    last_health_check_at: Optional[datetime]
    last_health_ok: bool
    last_health_error: Optional[str]
    created_at: datetime
    updated_at: datetime


class AgentListResponse(BaseModel):
    items: list[AgentItem]
    total: int

