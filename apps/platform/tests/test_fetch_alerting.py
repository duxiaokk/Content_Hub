from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apps.platform.database import Base
from apps.platform.models import FetchRun, SourceConfig
from apps.platform.services.fetch_alert_service import dispatch_fetch_alerts


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return Session(bind=engine)


def test_dispatch_fetch_alerts_generates_failure_and_volume_alerts() -> None:
    session = _make_session()
    source = SourceConfig(
        name="Alert Source",
        source_type="rss",
        enabled=True,
        channels='["https://example.com/feed.xml"]',
        keywords='[]',
        lookback_hours=24,
        item_limit=20,
        dedup_window_hours=24,
        config_json='{"alert_policy":{"channels":["log"],"volume_anomaly_ratio":0.2}}',
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
                fetched_count=10,
                inserted_count=10,
                deduped_count=0,
                started_at=datetime.now(timezone.utc),
            ),
            FetchRun(
                source_config_id=source.id,
                trigger_mode="scheduled",
                status="success",
                fetched_count=12,
                inserted_count=12,
                deduped_count=0,
                started_at=datetime.now(timezone.utc),
            ),
        ]
    )
    session.commit()

    fetch_run = FetchRun(
        source_config_id=source.id,
        trigger_mode="scheduled",
        status="failure",
        fetched_count=1,
        inserted_count=0,
        deduped_count=0,
        error_message="source timeout",
        started_at=datetime.now(timezone.utc),
    )
    session.add(fetch_run)
    session.commit()
    session.refresh(fetch_run)

    logs: list[tuple[str, str]] = []
    alerts = dispatch_fetch_alerts(
        session,
        source=source,
        fetch_run=fetch_run,
        task_result={"stats": {"total_fetched": 1, "sources_failed": 1}, "alerts": []},
        append_log=lambda level, message: logs.append((level, message)),
    )

    assert len(alerts) >= 2
    assert any(alert["alert_type"] == "fetch_run_failed" for alert in alerts)
    assert any(alert["alert_type"] == "volume_anomaly" for alert in alerts)
    assert logs
