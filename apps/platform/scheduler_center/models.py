from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    from scheduler_center.database import Base
except ImportError:  # pragma: no cover - package import fallback
    from apps.platform.scheduler_center.database import Base


def _utcnow() -> datetime:
    """返回 UTC aware datetime，兼容 PostgreSQL TIMESTAMPTZ。"""
    return datetime.now(UTC)


class SchedulerTask(Base):
    __tablename__ = "scheduler_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        unique=True,
        index=True,
    )
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    task_type: Mapped[str] = mapped_column(String(100), index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")

    status: Mapped[str] = mapped_column(String(20), index=True)
    cancel_requested: Mapped[int] = mapped_column(Integer, default=0)

    max_retries: Mapped[int] = mapped_column(Integer, default=2)
    retry_delay_seconds: Mapped[float] = mapped_column(Float, default=3.0)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)

    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    last_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utcnow,
        onupdate=_utcnow,
        index=True,
    )

    attempts: Mapped[list["SchedulerTaskAttempt"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    events: Mapped[list["SchedulerTaskEvent"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    logs: Mapped[list["SchedulerTaskLog"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class SchedulerTaskAttempt(Base):
    __tablename__ = "scheduler_task_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("scheduler_tasks.id"), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, index=True)
    agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    request_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    request_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retryable: Mapped[int] = mapped_column(Integer, default=0, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    task: Mapped[SchedulerTask] = relationship(back_populates="attempts")


class SchedulerTaskEvent(Base):
    __tablename__ = "scheduler_task_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("scheduler_tasks.id"), index=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    event_type: Mapped[str] = mapped_column(String(50), index=True)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    attempt_no: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)

    task: Mapped[SchedulerTask] = relationship(back_populates="events")


class SchedulerTaskLog(Base):
    __tablename__ = "scheduler_task_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("scheduler_tasks.id"), index=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    level: Mapped[str] = mapped_column(String(20), default="INFO", index=True)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)

    task: Mapped[SchedulerTask] = relationship(back_populates="logs")


class SchedulerAgent(Base):
    __tablename__ = "scheduler_agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    base_url: Mapped[str] = mapped_column(String(500))
    task_types_json: Mapped[str] = mapped_column(Text, default="[]")
    capabilities_json: Mapped[str] = mapped_column(Text, default="{}")
    health_path: Mapped[str] = mapped_column(String(200), default="/health")
    status: Mapped[int] = mapped_column(Integer, default=1, index=True)
    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_health_ok: Mapped[int] = mapped_column(Integer, default=1, index=True)
    last_health_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utcnow,
        onupdate=_utcnow,
        index=True,
    )

