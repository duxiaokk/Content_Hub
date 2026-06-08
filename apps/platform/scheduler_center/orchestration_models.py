"""编排层数据模型

在现有 SchedulerTask 基础上增加编排层:
  - OrchestrationRun: 编排运行（顶层容器）
  - OrchestrationTask: 编排任务（关联 SchedulerTask + 依赖 + 工件）
  - OrchestrationRunLog: 运行级日志
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from scheduler_center.database import Base
from scheduler_center.dispatcher import new_task_id


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RunStatus:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    PARTIAL = "PARTIAL"


class TaskOrchStatus:
    PENDING = "PENDING"
    BLOCKED = "BLOCKED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    SKIPPED = "SKIPPED"
    TIMED_OUT = "TIMED_OUT"


class OrchestrationRun(Base):
    __tablename__ = "orchestration_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_task_id)
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(20), default=RunStatus.PENDING, index=True)
    cancel_requested: Mapped[int] = mapped_column(Integer, default=0)

    plan_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    global_timeout_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    per_task_timeout_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    total_tasks: Mapped[int] = mapped_column(Integer, default=0)
    succeeded_tasks: Mapped[int] = mapped_column(Integer, default=0)
    failed_tasks: Mapped[int] = mapped_column(Integer, default=0)
    skipped_tasks: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    tasks: Mapped[list["OrchestrationTask"]] = relationship(back_populates="run", cascade="all, delete-orphan", lazy="selectin")
    logs: Mapped[list["OrchestrationRunLog"]] = relationship(back_populates="run", cascade="all, delete-orphan", lazy="selectin")


class OrchestrationTask(Base):
    __tablename__ = "orchestration_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_task_id)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("orchestration_runs.id"), index=True)
    scheduler_task_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("scheduler_tasks.id"), nullable=True, index=True)

    task_key: Mapped[str] = mapped_column(String(100), index=True)
    task_type: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    depends_on_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    layer_index: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(String(20), default=TaskOrchStatus.PENDING, index=True)

    input_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)

    max_retries: Mapped[int] = mapped_column(Integer, default=2)
    retry_delay_seconds: Mapped[float] = mapped_column(Float, default=3.0)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)

    timeout_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    compensation_task_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    compensation_payload: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    run: Mapped["OrchestrationRun"] = relationship(back_populates="tasks")


class OrchestrationRunLog(Base):
    __tablename__ = "orchestration_run_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("orchestration_runs.id"), index=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    task_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    level: Mapped[str] = mapped_column(String(20), default="INFO", index=True)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)

    run: Mapped["OrchestrationRun"] = relationship(back_populates="logs")
