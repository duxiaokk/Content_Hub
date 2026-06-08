from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db_session
from app.core.mempool import pool as mempool
from app.main import app


client = TestClient(app)


def _override_db():
    yield None


@pytest.fixture(autouse=True)
def setup():
    app.dependency_overrides[get_db_session] = _override_db
    yield
    app.dependency_overrides.clear()


def test_comment_moderate_task():
    trace_id = "trace-test-1"
    resp = client.post(
        "/api/internal/agent/run",
        headers={"x-internal-token": os.getenv("SCHEDULER_INTERNAL_TOKEN", "local-dev-scheduler-token"), "x-trace-id": trace_id},
        json={
            "task_id": "t1",
            "task_type": "comment.moderate",
            "trace_id": trace_id,
            "payload": {"comment_id": 123, "content": "hello"},
            "attempt_no": 1,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["task_type"] == "comment.moderate"
    assert data["comment_id"] == 123
    assert data["decision"] == "approved"

    stored = mempool.get("comment-agent:moderate:123", default=None)
    assert isinstance(stored, dict)
    assert stored["comment_id"] == 123
    assert stored["decision"] == "approved"
