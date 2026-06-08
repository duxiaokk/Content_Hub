from __future__ import annotations

import os
import sys
import uuid

from fastapi.testclient import TestClient


def test_scheduler_center_agent_register_and_list(monkeypatch):
    db_path = os.path.abspath(f"./.tmp_scheduler_agents_test_{uuid.uuid4().hex}.db")
    monkeypatch.setenv("SCHEDULER_DB_PATH", db_path)
    monkeypatch.setenv("SCHEDULER_INTERNAL_TOKEN", "test-token")
    monkeypatch.setenv("SCHEDULER_DISABLE_DISPATCHER", "true")

    for name in list(sys.modules.keys()):
        if name == "scheduler_center" or name.startswith("scheduler_center."):
            sys.modules.pop(name, None)

    from scheduler_center.main import app

    headers = {"x-internal-token": "test-token"}
    with TestClient(app) as client:
        resp = client.post(
            "/api/internal/scheduler/agents/register",
            headers=headers,
            json={
                "agent_key": "agent-1",
                "name": "Agent One",
                "base_url": "http://127.0.0.1:9999",
                "task_types": ["demo"],
                "health_path": "/health",
                "capabilities": {"k": "v"},
                "status": 1,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_key"] == "agent-1"
        assert data["base_url"] == "http://127.0.0.1:9999"
        assert data["task_types"] == ["demo"]

        resp = client.get(
            "/api/internal/scheduler/agents",
            headers=headers,
            params={"task_type": "demo"},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

