from __future__ import annotations

import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from routers.internal_tasks import router
from scheduler_center.config import CONTENT_FETCH_BATCH, CONTENT_PIPELINE_DAILY_DIGEST, CONTENT_PIPELINE_RADAR
from scheduler_center.database import Base
from scheduler_center.models import SchedulerTask
from services.content_domain_contracts import ContentDomainResult


def _make_session_local():
    import scheduler_center.models  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        pool_pre_ping=True,
    )
    session_local = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
        expire_on_commit=False,
    )
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return session_local


def test_trigger_radar_pipeline_submits_scheduler_task(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    calls: list[dict] = []

    class StubClient:
        def submit_task(self, **kwargs):
            calls.append(kwargs)
            return {"id": "task-radar-1", "trace_id": kwargs.get("trace_id")}

    monkeypatch.setattr("routers.internal_tasks.get_scheduler_client", lambda: StubClient())
    monkeypatch.setattr("routers.internal_tasks.settings.internal_agent_token", "token")

    client = TestClient(app)
    response = client.post(
        "/api/internal/tasks/content-pipeline/radar/run",
        headers={"x-internal-token": "token"},
        json={"limit": 10, "filter_config": {"keywords": ["agent"]}},
    )

    assert response.status_code == 200
    assert calls[0]["task_type"] == CONTENT_PIPELINE_RADAR
    assert calls[0]["payload"]["workflow_name"] == "radar_pipeline"
    assert calls[0]["payload"]["limit"] == 10


def test_trigger_daily_digest_pipeline_submits_scheduler_task(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)
    calls: list[dict] = []

    class StubClient:
        def submit_task(self, **kwargs):
            calls.append(kwargs)
            return {"id": "task-digest-1", "trace_id": kwargs.get("trace_id")}

    monkeypatch.setattr("routers.internal_tasks.get_scheduler_client", lambda: StubClient())
    monkeypatch.setattr("routers.internal_tasks.settings.internal_agent_token", "token")

    client = TestClient(app)
    response = client.post(
        "/api/internal/tasks/content-pipeline/daily-digest/run",
        headers={"x-internal-token": "token"},
        json={"lookback_hours": 48},
    )

    assert response.status_code == 200
    assert calls[0]["task_type"] == CONTENT_PIPELINE_DAILY_DIGEST
    assert calls[0]["payload"]["lookback_hours"] == 48


def test_dispatcher_cron_submits_scheduled_jobs(monkeypatch) -> None:
    import scheduler_center.dispatcher as dispatcher_module

    session_local = _make_session_local()
    monkeypatch.setattr(dispatcher_module, "SessionLocal", session_local)

    dispatcher = dispatcher_module.SchedulerDispatcher()
    dispatched = dispatcher._run_scheduled_jobs_once(datetime(2026, 6, 13, 9, 0))

    db = session_local()
    task = db.query(SchedulerTask).filter(SchedulerTask.task_type == CONTENT_PIPELINE_RADAR).first()
    assert dispatched
    assert task is not None
    assert task.status == dispatcher_module.TaskStatus.PENDING
    db.close()


def test_dispatcher_cron_respects_enable_flag(monkeypatch) -> None:
    import scheduler_center.dispatcher as dispatcher_module

    session_local = _make_session_local()
    monkeypatch.setattr(dispatcher_module, "SessionLocal", session_local)
    monkeypatch.setattr(dispatcher_module.scheduler_settings, "scheduler_cron_enabled", False)

    dispatcher = dispatcher_module.SchedulerDispatcher()
    if dispatcher_module.scheduler_settings.scheduler_cron_enabled:
        dispatched = dispatcher._run_scheduled_jobs_once(datetime(2026, 6, 13, 9, 0))
    else:
        dispatched = []

    db = session_local()
    assert dispatched == []
    assert db.query(SchedulerTask).count() == 0
    db.close()


def test_dispatcher_cron_submits_dynamic_source_fetch_jobs(monkeypatch) -> None:
    import scheduler_center.dispatcher as dispatcher_module
    from apps.platform import models as platform_models
    from apps.platform.database import Base as PlatformBase

    scheduler_session_local = _make_session_local()
    monkeypatch.setattr(dispatcher_module, "SessionLocal", scheduler_session_local)

    platform_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        pool_pre_ping=True,
    )
    platform_session_local = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=platform_engine,
        expire_on_commit=False,
    )
    PlatformBase.metadata.drop_all(bind=platform_engine)
    PlatformBase.metadata.create_all(bind=platform_engine)

    monkeypatch.setattr(
        dispatcher_module,
        "_load_platform_source_dependencies",
        lambda: (platform_session_local, platform_models, lambda **kwargs: []),
    )

    db = platform_session_local()
    source = platform_models.SourceConfig(
        name="Dynamic RSS",
        source_type="rss",
        enabled=True,
        channels='["https://example.com/feed.xml"]',
        keywords='["python"]',
        lookback_hours=24,
        item_limit=10,
        dedup_window_hours=24,
        config_json='{"feed_url":"https://example.com/feed.xml","schedule_expression":"*/15 * * * *"}',
    )
    db.add(source)
    db.commit()
    db.close()

    dispatcher = dispatcher_module.SchedulerDispatcher()
    dispatched = dispatcher._run_scheduled_jobs_once(datetime(2026, 6, 13, 9, 15))

    db = scheduler_session_local()
    task = db.query(SchedulerTask).filter(SchedulerTask.task_type == CONTENT_FETCH_BATCH).first()
    assert dispatched
    assert task is not None
    assert task.status == dispatcher_module.TaskStatus.PENDING
    assert f"source:{source.id}" in str(task.idempotency_key)
    db.close()


def test_dispatch_scheduled_task_is_idempotent_under_concurrency(monkeypatch) -> None:
    import scheduler_center.dispatcher as dispatcher_module

    session_local = _make_session_local()
    monkeypatch.setattr(dispatcher_module, "SessionLocal", session_local)

    dispatcher = dispatcher_module.SchedulerDispatcher()
    scheduled_for = datetime(2026, 6, 13, 9, 30)

    def _submit() -> str:
        return dispatcher.dispatch_scheduled_task(
            task_type=CONTENT_FETCH_BATCH,
            payload={"source_config_id": 1, "source_type": "rss"},
            scheduled_for=scheduled_for,
            idempotency_key="content.fetch.batch:source:1:2026-06-13T09:30",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: _submit(), range(8)))

    db = session_local()
    tasks = (
        db.query(SchedulerTask)
        .filter(SchedulerTask.idempotency_key == "content.fetch.batch:source:1:2026-06-13T09:30")
        .all()
    )
    assert len(set(results)) == 1
    assert len(tasks) == 1
    db.close()


def test_dispatcher_executes_content_workflow_via_content_domain_client(monkeypatch) -> None:
    import scheduler_center.dispatcher as dispatcher_module

    session_local = _make_session_local()
    monkeypatch.setattr(dispatcher_module, "SessionLocal", session_local)

    calls: list[dict] = []

    class StubContentDomainClient:
        async def run_content_workflow(self, payload):
            calls.append(payload)
            return ContentDomainResult(
                run_id=str(payload["run_id"]),
                status="success",
                summary="workflow content.workflow.run completed",
                trace_ref=str(payload["run_id"]),
                data={"workflow_name": payload["workflow_name"], "status": "succeeded"},
            )

    monkeypatch.setattr(dispatcher_module, "_load_content_domain_client", lambda: StubContentDomainClient)

    db = session_local()
    task = SchedulerTask(
        id=str(uuid.uuid4()),
        idempotency_key=None,
        trace_id="trace-workflow-1",
        task_type="content.workflow.run",
        payload_json='{"workflow_name":"content.workflow.run","source_name":"cnblogs"}',
        status=dispatcher_module.TaskStatus.RUNNING,
        cancel_requested=0,
        max_retries=0,
        retry_delay_seconds=0.0,
        attempt_count=0,
        next_run_at=None,
        last_agent=None,
        result_json=None,
        last_error=None,
    )
    db.add(task)
    db.commit()
    db.close()

    dispatcher = dispatcher_module.SchedulerDispatcher()
    dispatcher._execute_task(task.id)

    db = session_local()
    refreshed = db.query(SchedulerTask).filter(SchedulerTask.id == task.id).first()
    assert refreshed is not None
    assert refreshed.status == dispatcher_module.TaskStatus.SUCCEEDED
    assert refreshed.last_error is None
    assert refreshed.result_json is not None
    assert calls[0]["run_id"] == "trace-workflow-1"
    db.close()


def test_dispatcher_marks_content_workflow_failed_when_domain_client_errors(monkeypatch) -> None:
    import scheduler_center.dispatcher as dispatcher_module

    session_local = _make_session_local()
    monkeypatch.setattr(dispatcher_module, "SessionLocal", session_local)

    class StubContentDomainClient:
        async def run_content_workflow(self, payload):
            raise RuntimeError(f"workflow failed for {payload['workflow_name']}")

    monkeypatch.setattr(dispatcher_module, "_load_content_domain_client", lambda: StubContentDomainClient)

    db = session_local()
    task = SchedulerTask(
        id=str(uuid.uuid4()),
        idempotency_key=None,
        trace_id="trace-workflow-2",
        task_type="content.workflow.run",
        payload_json='{"workflow_name":"content.workflow.run"}',
        status=dispatcher_module.TaskStatus.RUNNING,
        cancel_requested=0,
        max_retries=0,
        retry_delay_seconds=0.0,
        attempt_count=0,
        next_run_at=None,
        last_agent=None,
        result_json=None,
        last_error=None,
    )
    db.add(task)
    db.commit()
    db.close()

    dispatcher = dispatcher_module.SchedulerDispatcher()
    dispatcher._execute_task(task.id)

    db = session_local()
    refreshed = db.query(SchedulerTask).filter(SchedulerTask.id == task.id).first()
    assert refreshed is not None
    assert refreshed.status == dispatcher_module.TaskStatus.FAILED
    assert "workflow failed for content.workflow.run" in str(refreshed.last_error)
    db.close()


def test_dispatcher_executes_publish_approved_content_success(monkeypatch) -> None:
    import scheduler_center.dispatcher as dispatcher_module

    session_local = _make_session_local()
    monkeypatch.setattr(dispatcher_module, "SessionLocal", session_local)

    calls: list[dict] = []

    class StubContentDomainClient:
        async def publish_approved_content(self, payload):
            calls.append(payload)
            return ContentDomainResult(
                run_id=str(payload["run_id"]),
                status="success",
                summary="draft published",
                trace_ref=str(payload["run_id"]),
                data={"content_item_id": payload["content_item_id"], "status": "success", "target_type": "blog"},
            )

    monkeypatch.setattr(dispatcher_module, "_load_content_domain_client", lambda: StubContentDomainClient)

    db = session_local()
    task = SchedulerTask(
        id=str(uuid.uuid4()),
        idempotency_key=None,
        trace_id="trace-publish-1",
        task_type="content.publish.approved",
        payload_json='{"content_item_id":12,"target_type":"blog"}',
        status=dispatcher_module.TaskStatus.RUNNING,
        cancel_requested=0,
        max_retries=0,
        retry_delay_seconds=0.0,
        attempt_count=0,
        next_run_at=None,
        last_agent=None,
        result_json=None,
        last_error=None,
    )
    db.add(task)
    db.commit()
    db.close()

    dispatcher = dispatcher_module.SchedulerDispatcher()
    dispatcher._execute_task(task.id)

    db = session_local()
    refreshed = db.query(SchedulerTask).filter(SchedulerTask.id == task.id).first()
    assert refreshed is not None
    assert refreshed.status == dispatcher_module.TaskStatus.SUCCEEDED
    assert refreshed.last_error is None
    assert calls[0]["target_type"] == "blog"
    db.close()


def test_dispatcher_marks_publish_approved_content_failed_for_invalid_target(monkeypatch) -> None:
    import scheduler_center.dispatcher as dispatcher_module
    from services.content_domain_client import UnsupportedPublishTargetError

    session_local = _make_session_local()
    monkeypatch.setattr(dispatcher_module, "SessionLocal", session_local)

    class StubContentDomainClient:
        async def publish_approved_content(self, payload):
            raise UnsupportedPublishTargetError(
                f"unsupported publish target_type: {payload['target_type']}"
            )

    monkeypatch.setattr(dispatcher_module, "_load_content_domain_client", lambda: StubContentDomainClient)

    db = session_local()
    task = SchedulerTask(
        id=str(uuid.uuid4()),
        idempotency_key=None,
        trace_id="trace-publish-2",
        task_type="content.publish.approved",
        payload_json='{"content_item_id":12,"target_type":"digest"}',
        status=dispatcher_module.TaskStatus.RUNNING,
        cancel_requested=0,
        max_retries=0,
        retry_delay_seconds=0.0,
        attempt_count=0,
        next_run_at=None,
        last_agent=None,
        result_json=None,
        last_error=None,
    )
    db.add(task)
    db.commit()
    db.close()

    dispatcher = dispatcher_module.SchedulerDispatcher()
    dispatcher._execute_task(task.id)

    db = session_local()
    refreshed = db.query(SchedulerTask).filter(SchedulerTask.id == task.id).first()
    assert refreshed is not None
    assert refreshed.status == dispatcher_module.TaskStatus.FAILED
    assert "unsupported publish target_type: digest" in str(refreshed.last_error)
    db.close()
