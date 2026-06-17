from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

os.environ.setdefault("SECRET_KEY", "test-secret-key")

from apps.platform.database import Base
from apps.platform.models import FetchRun, SourceConfig
from apps.platform.schemas.console import TriggerProcessFetchRunRequest
from apps.platform.services.console_service import sync_content_items_from_result, trigger_process_fetch_run


def test_sync_content_items_from_result_items() -> None:
    from apps.platform.services import console_service as console_service_module

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)

    class StubRepository:
        def upsert_fetched_item(self, item):  # noqa: ANN001
            return 1

        def attach_fetch_context(self, **kwargs):  # noqa: ANN003
            return None

    original_repository = console_service_module.ContentRepository
    console_service_module.ContentRepository = StubRepository
    try:
        with Session(bind=engine) as session:
            source = SourceConfig(
                name="rss-source",
                source_type="rss",
                enabled=True,
                lookback_hours=24,
                item_limit=20,
                dedup_window_hours=24,
            )
            session.add(source)
            session.commit()
            session.refresh(source)

            fetch_run = FetchRun(
                source_config_id=source.id,
                trigger_mode="manual",
                status="success",
                started_at=datetime.now(timezone.utc),
            )
            session.add(fetch_run)
            session.commit()
            session.refresh(fetch_run)

            inserted = sync_content_items_from_result(
                session,
                fetch_run,
                source,
                {
                    "items": [
                        {
                            "dedup_key": "rss:1",
                            "title": "Example title",
                            "content": "Example content",
                            "link": "https://example.com/item-1",
                        }
                    ]
                },
            )

            assert inserted == 1
    finally:
        console_service_module.ContentRepository = original_repository


def test_trigger_process_fetch_run_submits_radar_task(monkeypatch) -> None:
    submitted: dict[str, object] = {}

    class StubSchedulerClient:
        def submit_task(self, **kwargs):  # noqa: ANN003
            submitted.update(kwargs)
            return {"id": "task-radar-1", "trace_id": "trace-radar-1", "status": "pending"}

    monkeypatch.setattr("apps.platform.services.console_service.get_scheduler_client", lambda: StubSchedulerClient())

    result = trigger_process_fetch_run(
        SimpleNamespace(),
        SimpleNamespace(id=7),
        TriggerProcessFetchRunRequest(
            limit=8,
            source_type="rss",
            filter_config={"include_keywords": ["python"]},
            process_options={"rewrite_profile": "zh_tech_blog"},
        ),
        "tester",
    )

    assert result == {
        "fetch_run_id": 7,
        "task_id": "task-radar-1",
        "trace_id": "trace-radar-1",
        "status": "pending",
    }
    assert submitted["task_type"] == "content.pipeline.radar"
    assert submitted["payload"] == {
        "workflow_name": "radar_pipeline",
        "fetch_run_id": 7,
        "limit": 8,
        "source_type": "rss",
        "filter_config": {"include_keywords": ["python"]},
        "process_options": {"rewrite_profile": "zh_tech_blog"},
        "trigger_type": "manual",
        "requested_by": "tester",
    }
