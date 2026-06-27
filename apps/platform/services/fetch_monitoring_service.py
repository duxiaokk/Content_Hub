from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from apps.platform import models
from apps.platform.services.console_service import (
    get_scheduler_task_detail,
    get_scheduler_task_logs,
    serialize_fetch_run,
)


def build_fetch_monitor_overview(db: Session) -> dict[str, Any]:
    runs = db.query(models.FetchRun).order_by(models.FetchRun.created_at.desc()).limit(50).all()
    source_configs = {
        row.id: row
        for row in db.query(models.SourceConfig).filter(models.SourceConfig.enabled.is_(True)).all()
    }

    total_runs = len(runs)
    successful_runs = sum(1 for run in runs if run.status == "success")
    failed_runs = sum(1 for run in runs if run.status == "failure")
    running_runs = sum(1 for run in runs if run.status in {"pending", "running", "retrying"})
    success_rate = round((successful_runs / total_runs) * 100, 2) if total_runs else 0.0

    source_summaries: list[dict[str, Any]] = []
    grouped: dict[int, list[models.FetchRun]] = {}
    for run in runs:
        grouped.setdefault(int(run.source_config_id), []).append(run)

    for source_id, items in grouped.items():
        source = source_configs.get(source_id)
        total = len(items)
        success = sum(1 for row in items if row.status == "success")
        source_summaries.append(
            {
                "source_config_id": source_id,
                "source_name": source.name if source else f"source-{source_id}",
                "source_type": source.source_type if source else "unknown",
                "total_runs": total,
                "success_runs": success,
                "failure_runs": sum(1 for row in items if row.status == "failure"),
                "success_rate": round((success / total) * 100, 2) if total else 0.0,
                "last_run_at": items[0].created_at.isoformat() if items and items[0].created_at else None,
                "last_status": items[0].status if items else None,
            }
        )

    recent_alerts: list[dict[str, Any]] = []
    for run in runs[:15]:
        if not run.task_id:
            continue
        try:
            detail = get_scheduler_task_detail(run.task_id)
        except Exception:
            continue
        alerts = detail.get("result", {}).get("alerts") if isinstance(detail.get("result"), dict) else []
        if isinstance(alerts, list):
            for alert in alerts:
                if not isinstance(alert, dict):
                    continue
                recent_alerts.append(
                    {
                        "fetch_run_id": run.id,
                        "source_config_id": run.source_config_id,
                        "source_name": source_configs.get(run.source_config_id).name if source_configs.get(run.source_config_id) else None,
                        **alert,
                    }
                )
        if len(recent_alerts) >= 20:
            break

    return {
        "total_runs": total_runs,
        "successful_runs": successful_runs,
        "failed_runs": failed_runs,
        "running_runs": running_runs,
        "success_rate": success_rate,
        "source_summaries": source_summaries,
        "recent_alerts": recent_alerts[:20],
    }


def get_fetch_run_monitor_detail(db: Session, fetch_run_id: int) -> dict[str, Any]:
    row = db.query(models.FetchRun).filter(models.FetchRun.id == fetch_run_id).first()
    if row is None:
        raise ValueError("fetch run not found")
    source = db.query(models.SourceConfig).filter(models.SourceConfig.id == row.source_config_id).first()
    if source is None:
        raise ValueError("source config not found")

    run_data = serialize_fetch_run(row, source)
    task_detail = get_scheduler_task_detail(row.task_id or "") if row.task_id else {}
    task_logs = get_scheduler_task_logs(row.task_id or "") if row.task_id else []
    result = task_detail.get("result") if isinstance(task_detail.get("result"), dict) else {}
    return {
        "fetch_run": run_data,
        "task": task_detail,
        "logs": task_logs,
        "stats": result.get("stats") if isinstance(result.get("stats"), dict) else {},
        "alerts": result.get("alerts") if isinstance(result.get("alerts"), list) else [],
        "validation_issues": result.get("validation_issues") if isinstance(result.get("validation_issues"), list) else [],
        "source_stats": result.get("source_stats") if isinstance(result.get("source_stats"), list) else [],
        "checkpoints": result.get("checkpoints") if isinstance(result.get("checkpoints"), dict) else {},
    }
