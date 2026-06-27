from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apps.platform.database import Base
from apps.platform.models import FetchRun, SourceConfig
from apps.platform.services.fetch_monitoring_service import (
    build_fetch_monitor_overview,
    get_fetch_run_monitor_detail,
)


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return Session(bind=engine)


def test_build_fetch_monitor_overview_collects_success_rate_and_alerts(monkeypatch) -> None:
    session = _make_session()
    source = SourceConfig(
        name="RSS Source",
        source_type="rss",
        enabled=True,
        channels='["https://example.com/feed.xml"]',
        keywords='[]',
        lookback_hours=24,
        item_limit=10,
        dedup_window_hours=24,
        config_json='{"schedule_expression":"0 */6 * * *"}',
    )
    session.add(source)
    session.commit()
    session.refresh(source)

    session.add_all(
        [
            FetchRun(
                source_config_id=source.id,
                trigger_mode="scheduled",
                status="success",
                task_id="task-success-1",
                fetched_count=5,
                inserted_count=4,
                deduped_count=1,
                started_at=datetime.now(timezone.utc),
            ),
            FetchRun(
                source_config_id=source.id,
                trigger_mode="scheduled",
                status="failure",
                task_id="task-failed-1",
                fetched_count=0,
                inserted_count=0,
                deduped_count=0,
                error_message="timeout",
                started_at=datetime.now(timezone.utc),
            ),
        ]
    )
    session.commit()

    monkeypatch.setattr(
        "apps.platform.services.fetch_monitoring_service.get_scheduler_task_detail",
        lambda task_id: {
            "result": {
                "alerts": [
                    {
                        "source": "rss",
                        "alert_type": "source_unavailable" if "failed" in task_id else "invalid_ratio_high",
                        "severity": "critical" if "failed" in task_id else "warning",
                        "message": "simulated",
                    }
                ]
            }
        },
    )

    overview = build_fetch_monitor_overview(session)

    assert overview["total_runs"] == 2
    assert overview["successful_runs"] == 1
    assert overview["failed_runs"] == 1
    assert overview["success_rate"] == 50.0
    assert len(overview["recent_alerts"]) == 2
    assert overview["source_summaries"][0]["source_name"] == "RSS Source"


def test_get_fetch_run_monitor_detail_returns_logs_and_stats(monkeypatch) -> None:
    session = _make_session()
    source = SourceConfig(
        name="Reddit Source",
        source_type="reddit",
        enabled=True,
        channels='["r/python"]',
        keywords='[]',
        lookback_hours=24,
        item_limit=10,
        dedup_window_hours=24,
        config_json='{"schedule_expression":"0 */6 * * *"}',
    )
    session.add(source)
    session.commit()
    session.refresh(source)

    fetch_run = FetchRun(
        source_config_id=source.id,
        trigger_mode="manual",
        status="success",
        task_id="task-detail-1",
        fetched_count=3,
        inserted_count=2,
        deduped_count=1,
        started_at=datetime.now(timezone.utc),
    )
    session.add(fetch_run)
    session.commit()
    session.refresh(fetch_run)

    monkeypatch.setattr(
        "apps.platform.services.fetch_monitoring_service.get_scheduler_task_detail",
        lambda task_id: {
            "id": task_id,
            "result": {
                "stats": {"total_fetched": 3, "total_invalid": 1},
                "alerts": [{"source": "reddit", "alert_type": "invalid_ratio_high", "severity": "warning", "message": "high invalid"}],
                "validation_issues": [{"source_id": "bad-1", "reason": "missing_source_url"}],
                "source_stats": [{"source": "reddit", "fetched_count": 3, "inserted_count": 2, "invalid_count": 1, "retried_count": 0, "deduped_count": 0, "status": "success", "elapsed_ms": 10}],
                "checkpoints": {"reddit": {"resume_cursor": "cursor-1"}},
            },
        },
    )
    monkeypatch.setattr(
        "apps.platform.services.fetch_monitoring_service.get_scheduler_task_logs",
        lambda task_id: [{"id": 1, "level": "INFO", "message": "done", "created_at": "2026-06-25T10:00:00"}],
    )

    detail = get_fetch_run_monitor_detail(session, fetch_run.id)

    assert detail["fetch_run"]["id"] == fetch_run.id
    assert detail["stats"]["total_invalid"] == 1
    assert detail["alerts"][0]["alert_type"] == "invalid_ratio_high"
    assert detail["logs"][0]["message"] == "done"
