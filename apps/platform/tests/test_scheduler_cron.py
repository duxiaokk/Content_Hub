from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SECRET_KEY", "test-secret-key")
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from apps.platform.routers.internal_tasks import router
from apps.platform.scheduler_center.config import CONTENT_PIPELINE_DAILY_DIGEST, CONTENT_PIPELINE_RADAR
from apps.platform.scheduler_center.database import Base
from apps.platform.scheduler_center.models import SchedulerTask


def _make_session_local():
    __import__("apps.platform.scheduler_center.models")
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

    monkeypatch.setattr("apps.platform.routers.internal_tasks.get_scheduler_client", lambda: StubClient())
    monkeypatch.setattr("apps.platform.routers.internal_tasks.settings.internal_agent_token", "token")

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

    monkeypatch.setattr("apps.platform.routers.internal_tasks.get_scheduler_client", lambda: StubClient())
    monkeypatch.setattr("apps.platform.routers.internal_tasks.settings.internal_agent_token", "token")

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
    import apps.platform.scheduler_center.dispatcher as dispatcher_module

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
    import apps.platform.scheduler_center.dispatcher as dispatcher_module

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
