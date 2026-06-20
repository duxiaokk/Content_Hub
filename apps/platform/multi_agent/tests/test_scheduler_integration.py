"""端到端测试 Multi-Agent Orchestrator 集成端点。

验证调度中心 `/api/internal/orchestrate` 端点的可用性和降级行为。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from scheduler_center.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestOrchestrateEndpoint:
    """测试 /api/internal/orchestrate 端点。"""

    def test_orchestrate_endpoint_available(self, client: TestClient) -> None:
        """端点可访问，对简单意图返回成功响应。"""
        response = client.post(
            "/api/internal/orchestrate",
            json={"intent": "生成一段关于 AI 的摘要"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "trace_id" in data
        assert "success" in data
        assert "summary" in data
        assert "task_count" in data

    def test_orchestrate_with_context(self, client: TestClient) -> None:
        """支持传入 context 参数。"""
        response = client.post(
            "/api/internal/orchestrate",
            json={
                "intent": "抓取 GitHub 并分析",
                "context": {"source": "github", "limit": 5},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["task_count"] >= 2

    def test_orchestrate_invalid_request(self, client: TestClient) -> None:
        """缺少 intent 时返回 422。"""
        response = client.post(
            "/api/internal/orchestrate",
            json={},
        )
        assert response.status_code == 422

    def test_orchestrate_fallback_plan(self, client: TestClient) -> None:
        """降级计划被正确触发，没有外部 Agent 时也能返回结果。"""
        response = client.post(
            "/api/internal/orchestrate",
            json={"intent": "抓取 Reddit 并分析生成摘要"},
        )
        assert response.status_code == 200
        data = response.json()
        # 降级计划至少包含 fetch 和 analyze（任务数量 >= 2）
        assert data["task_count"] >= 2
        # trace_id 存在且 success 为 True（Orchestrator 自身成功执行了降级流程）
        assert data["trace_id"] is not None
        assert data["success"] is True
