from __future__ import annotations

import json
import logging
from typing import Any, Callable

import httpx
from sqlalchemy.orm import Session

from apps.platform import models


logger = logging.getLogger(__name__)


def dispatch_fetch_alerts(
    db: Session,
    *,
    source: models.SourceConfig,
    fetch_run: models.FetchRun | None,
    task_result: dict[str, Any],
    append_log: Callable[[str, str], None] | None = None,
) -> list[dict[str, Any]]:
    alerts = _collect_alerts(db, source=source, fetch_run=fetch_run, task_result=task_result)
    if not alerts:
        return []

    alert_policy = _get_alert_policy(source)
    channels = [str(v).strip().lower() for v in alert_policy.get("channels", ["log"]) if str(v).strip()]
    for alert in alerts:
        message = f"[{alert['severity']}] {alert['alert_type']}: {alert['message']}"
        if append_log is not None and ("log" in channels or not channels):
            append_log(str(alert["severity"]).upper(), message)
        logger.warning(message, extra={"source_id": source.id, "fetch_run_id": getattr(fetch_run, "id", None)})

    webhook_url = str(alert_policy.get("webhook_url") or "").strip()
    if webhook_url and "webhook" in channels:
        _send_webhook_alerts(webhook_url, alerts)
    return alerts


def _collect_alerts(
    db: Session,
    *,
    source: models.SourceConfig,
    fetch_run: models.FetchRun | None,
    task_result: dict[str, Any],
) -> list[dict[str, Any]]:
    alerts = list(task_result.get("alerts") or [])
    stats = task_result.get("stats") if isinstance(task_result.get("stats"), dict) else {}
    if getattr(fetch_run, "status", None) == "failure" or int(stats.get("sources_failed") or 0) > 0:
        alerts.append(
            {
                "source": source.source_type,
                "alert_type": "fetch_run_failed",
                "severity": "critical",
                "message": getattr(fetch_run, "error_message", None) or "fetch run failed",
                "payload": {"fetch_run_id": getattr(fetch_run, "id", None)},
            }
        )

    current_count = int(stats.get("total_fetched") or getattr(fetch_run, "fetched_count", 0) or 0)
    previous_runs = (
        db.query(models.FetchRun)
        .filter(models.FetchRun.source_config_id == source.id)
        .filter(models.FetchRun.id != getattr(fetch_run, "id", -1))
        .filter(models.FetchRun.status == "success")
        .order_by(models.FetchRun.created_at.desc())
        .limit(5)
        .all()
    )
    samples = [int(row.fetched_count or 0) for row in previous_runs if int(row.fetched_count or 0) > 0]
    if samples:
        baseline = sum(samples) / len(samples)
        ratio = float(_get_alert_policy(source).get("volume_anomaly_ratio", 0.7))
        lower_bound = baseline * max(0.0, 1 - ratio)
        upper_bound = baseline * (1 + ratio)
        if current_count < lower_bound or current_count > upper_bound:
            alerts.append(
                {
                    "source": source.source_type,
                    "alert_type": "volume_anomaly",
                    "severity": "warning",
                    "message": f"Fetched count {current_count} deviates from baseline {baseline:.2f}",
                    "payload": {
                        "baseline": baseline,
                        "current_count": current_count,
                    },
                }
            )
    return alerts


def _get_alert_policy(source: models.SourceConfig) -> dict[str, Any]:
    try:
        config = json.loads(source.config_json) if source.config_json else {}
    except json.JSONDecodeError:
        config = {}
    if not isinstance(config, dict):
        return {}
    policy = config.get("alert_policy")
    return policy if isinstance(policy, dict) else {}


def _send_webhook_alerts(webhook_url: str, alerts: list[dict[str, Any]]) -> None:
    try:
        with httpx.Client(timeout=httpx.Timeout(5.0)) as client:
            client.post(webhook_url, json={"alerts": alerts})
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("Failed to send fetch alert webhook", extra={"error": str(exc), "webhook_url": webhook_url})
