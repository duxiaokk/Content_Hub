from __future__ import annotations

import os
import sys
import uuid

from fastapi.testclient import TestClient


def test_scheduler_center_submit_query_cancel_logs(monkeypatch):
    db_path = os.path.abspath(f"./.tmp_scheduler_test_{uuid.uuid4().hex}.db")
    monkeypatch.setenv("SCHEDULER_DB_PATH", db_path)
    monkeypatch.setenv("SCHEDULER_INTERNAL_TOKEN", "test-token")
    monkeypatch.setenv("SCHEDULER_DISABLE_DISPATCHER", "true")

    for name in list(sys.modules.keys()):
        if name == "scheduler_center" or name.startswith("scheduler_center."):
            sys.modules.pop(name, None)

    from scheduler_center.main import app

    headers = {"x-internal-token": "test-token", "x-trace-id": "trace-api-1", "x-idempotency-key": "idem-1"}

    with TestClient(app) as client:
        resp = client.post(
            "/api/internal/scheduler/tasks",
            headers=headers,
            json={"task_type": "demo", "payload": {"hello": "world"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        task_id = data["id"]
        assert data["trace_id"] == "trace-api-1"

        resp2 = client.post(
            "/api/internal/scheduler/tasks",
            headers=headers,
            json={"task_type": "demo", "payload": {"hello": "world"}},
        )
        assert resp2.status_code == 200
        assert resp2.json()["id"] == task_id

        resp = client.get(f"/api/internal/scheduler/tasks/{task_id}", headers=headers)
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["idempotency_key"] == "idem-1"
        assert detail["trace_id"] == "trace-api-1"
        assert detail["status"] in {"PENDING", "RUNNING", "CANCELED", "SUCCEEDED", "FAILED"}
        assert detail["events"]

        resp = client.get(
            "/api/internal/scheduler/tasks",
            headers=headers,
            params={"task_type": "demo", "status": "PENDING", "idempotency_key": "idem-1"},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1
        assert any(i["id"] == task_id for i in resp.json()["items"])

        resp = client.post(f"/api/internal/scheduler/tasks/{task_id}/cancel", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["cancel_requested"] is True
        assert resp.json()["trace_id"] == "trace-api-1"

        resp = client.get(f"/api/internal/scheduler/tasks/{task_id}/logs", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1
        assert any(i.get("trace_id") == "trace-api-1" for i in resp.json()["items"])

