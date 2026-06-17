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
    total_token_cost: int = 0
    total_elapsed_ms: int = 0
    error_summary: str | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)
    logs: list[dict[str, Any]] = field(default_factory=list)

    def mark_running(self) -> None:
        self.status = "running"
        self.log("INFO", "run started")

    def mark_finished(self, *, status: str) -> None:
        self.status = status
        self.finished_at = _utcnow()
        if self.finished_at and self.started_at:
            self.total_elapsed_ms = int((self.finished_at - self.started_at).total_seconds() * 1000)
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

    def log_step_start(self, step_name: str, *, items_in: int = 0) -> None:
        self.steps.append(
            {
                "name": step_name,
                "status": "running",
                "started_at": _utcnow().isoformat(),
                "finished_at": None,
                "duration_ms": None,
                "items_in": items_in,
                "items_out": 0,
                "error": None,
            }
        )
        self.log("INFO", f"step started: {step_name}", payload={"step_name": step_name, "items_in": items_in})

    def log_step_end(
        self,
        step_name: str,
        *,
        status: str,
        items_out: int = 0,
        error: str | None = None,
    ) -> None:
        for step in reversed(self.steps):
            if step["name"] == step_name and step["status"] == "running":
                finished_at = _utcnow()
                started_at = datetime.fromisoformat(step["started_at"])
                step["finished_at"] = finished_at.isoformat()
                step["duration_ms"] = int((finished_at - started_at).total_seconds() * 1000)
                step["items_out"] = items_out
                step["status"] = status
                step["error"] = error
                self.log(
                    "ERROR" if status == "failed" else "INFO",
                    f"step finished: {step_name}",
                    payload={"step_name": step_name, "status": status, "items_out": items_out, "error": error},
                )
                return

    def log_token_usage(self, tokens: int) -> None:
        self.total_token_cost += max(tokens, 0)
        self.log("INFO", "token usage recorded", payload={"tokens": max(tokens, 0)})

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
            "error_summary": self.error_summary,
            "steps": list(self.steps),
            "total_token_cost": self.total_token_cost,
            "total_elapsed_ms": self.total_elapsed_ms,
            "logs": list(self.logs),
        }
