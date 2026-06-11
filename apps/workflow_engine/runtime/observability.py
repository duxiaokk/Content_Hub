from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class WorkflowRunTrace:
    run_id: str
    workflow_name: str
    status: str = "pending"
    started_at: datetime = field(default_factory=_utcnow)
    finished_at: datetime | None = None
    items_total: int = 0
    items_succeeded: int = 0
    items_failed: int = 0
    logs: list[dict[str, Any]] = field(default_factory=list)

    def mark_running(self) -> None:
        self.status = "running"
        self.log("INFO", "run started")

    def mark_finished(self, *, status: str) -> None:
        self.status = status
        self.finished_at = _utcnow()
        self.log("INFO", f"run finished with status={status}")

    def record_item(self, *, succeeded: bool, message: str, payload: dict[str, Any] | None = None) -> None:
        self.items_total += 1
        if succeeded:
            self.items_succeeded += 1
            level = "INFO"
        else:
            self.items_failed += 1
            level = "ERROR"
        self.log(level, message, payload=payload)

    def log(self, level: str, message: str, *, payload: dict[str, Any] | None = None) -> None:
        self.logs.append(
            {
                "timestamp": _utcnow().isoformat(),
                "level": level,
                "message": message,
                "payload": payload or {},
            }
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "workflow_name": self.workflow_name,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "items_total": self.items_total,
            "items_succeeded": self.items_succeeded,
            "items_failed": self.items_failed,
            "logs": list(self.logs),
        }
