from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("SECRET_KEY", "test-secret-key")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from routers.internal_tasks import router


def test_trigger_content_workflow_submits_scheduler_task(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)

    calls: list[dict] = []

    class StubClient:
        def submit_task(self, **kwargs):  # noqa: ANN003
            calls.append(kwargs)
            return {"id": "task-1", "trace_id": kwargs.get("trace_id")}

    monkeypatch.setattr("routers.internal_tasks.get_scheduler_client", lambda: StubClient())
    monkeypatch.setattr("routers.internal_tasks.settings.internal_agent_token", "token")

    client = TestClient(app)
    response = client.post(
        "/api/internal/tasks/content-workflow/run",
        headers={"x-internal-token": "token"},
        json={
            "workflow_name": "content.workflow.run",
            "source_name": "cnblogs",
            "fetcher_name": "cnblogs",
            "processor_name": "rewrite",
            "publisher_name": "blog",
            "lookback_hours": 12,
            "limit": 5,
        },
    )

    assert response.status_code == 200
    assert calls[0]["task_type"] == "content.workflow.run"
    assert calls[0]["payload"]["source_name"] == "cnblogs"
    assert calls[0]["payload"]["workflow_name"] == "content.workflow.run"


def test_trigger_publish_approved_content_submits_scheduler_task(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)

    calls: list[dict] = []

    class StubClient:
        def submit_task(self, **kwargs):  # noqa: ANN003
            calls.append(kwargs)
            return {"id": "task-publish-1", "trace_id": kwargs.get("trace_id")}

    monkeypatch.setattr("routers.internal_tasks.get_scheduler_client", lambda: StubClient())
    monkeypatch.setattr("routers.internal_tasks.settings.internal_agent_token", "token")

    client = TestClient(app)
    response = client.post(
        "/api/internal/tasks/content-publish/approved/run",
        headers={"x-internal-token": "token"},
        json={"content_item_id": 12, "target_type": "blog"},
    )

    assert response.status_code == 200
    assert calls[0]["task_type"] == "content.publish.approved"
    assert calls[0]["payload"]["content_item_id"] == 12


def test_trigger_publish_approved_content_rejects_non_blog_target(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router)

    class StubClient:
        def submit_task(self, **kwargs):  # noqa: ANN003
            return {"id": "task-publish-2", "trace_id": kwargs.get("trace_id")}

    monkeypatch.setattr("routers.internal_tasks.get_scheduler_client", lambda: StubClient())
    monkeypatch.setattr("routers.internal_tasks.settings.internal_agent_token", "token")

    client = TestClient(app)
    response = client.post(
        "/api/internal/tasks/content-publish/approved/run",
        headers={"x-internal-token": "token"},
        json={"content_item_id": 12, "target_type": "digest"},
    )

    assert response.status_code == 422
