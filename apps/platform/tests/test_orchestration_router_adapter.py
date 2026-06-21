from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret-key")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from scheduler_center.database import Base, SessionLocal, engine
from scheduler_center.models import SchedulerTask
from scheduler_center.orchestration_router import router


def test_orchestration_adapter_submits_scheduler_workflow_task() -> None:
    Base.metadata.create_all(bind=engine)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/api/internal/orchestration/runs",
        headers={"x-internal-token": "local-dev-scheduler-token"},
        json={
            "intent": "run content workflow",
            "name": "workflow-a",
            "context": {
                "source_name": "cnblogs",
                "fetcher_name": "cnblogs",
                "processor_name": "rewrite",
                "publisher_name": "blog",
            },
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    run_id = payload["run_id"]

    db = SessionLocal()
    try:
        task = db.query(SchedulerTask).filter_by(id=run_id).first()
        assert task is not None
        assert task.task_type == "content.workflow.run"
    finally:
        db.close()


def test_orchestration_adapter_uses_standard_workflow_payload() -> None:
    Base.metadata.create_all(bind=engine)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/api/internal/orchestration/runs",
        headers={"x-internal-token": "local-dev-scheduler-token"},
        json={
            "intent": "run content workflow",
            "name": "workflow-b",
            "context": {
                "source_name": "reddit_ai",
                "fetcher_name": "reddit_ai",
                "processor_name": "rewrite",
                "publisher_name": "digest_markdown",
                "lookback_hours": 6,
                "limit": 8,
                "process_options": {"rewrite_profile": "zh_tech_blog"},
            },
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    run_id = payload["run_id"]

    db = SessionLocal()
    try:
        task = db.query(SchedulerTask).filter_by(id=run_id).first()
        assert task is not None
        assert '"source_name": "reddit_ai"' in task.payload_json
        assert '"publisher_name": "digest_markdown"' in task.payload_json
        assert '"lookback_hours": 6' in task.payload_json
    finally:
        db.close()


def test_orchestration_adapter_plans_workflow_when_use_planner_enabled() -> None:
    Base.metadata.create_all(bind=engine)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/api/internal/orchestration/runs",
        headers={"x-internal-token": "local-dev-scheduler-token"},
        json={
            "intent": "抓取 GitHub 内容并搜索补充背景后生成中文摘要",
            "name": "planned-workflow",
            "context": {
                "enable_tool_stage": True,
                "search_query": "GitHub Python trending background",
            },
            "use_planner": True,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["plan"] is not None
    assert payload["total_tasks"] >= 4

    run_id = payload["run_id"]
    db = SessionLocal()
    try:
        task = db.query(SchedulerTask).filter_by(id=run_id).first()
        assert task is not None
        assert '"nodes"' in task.payload_json
        assert '"stage": "tool"' in task.payload_json
        assert '"component_name": "github_trending"' in task.payload_json
    finally:
        db.close()


def test_orchestration_adapter_lists_scheduler_runs() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get(
        "/api/internal/orchestration/runs",
        headers={"x-internal-token": "local-dev-scheduler-token"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert "items" in payload
