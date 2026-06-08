"""Agent 测试套件

覆盖:
  1. BaseAgent 生命周期 (创建/注册/心跳/错误上报)
  2. 5 类 Agent execute 逻辑
  3. Agent schemas 验证
  4. 状态同步机制
  5. 负载/心跳/能力标签

运行:  pytest tests/test_agents.py -v
"""
from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from agents.base_agent import AgentConfig, BaseAgent
from agents.schemas import (
    AgentErrorReport,
    AgentHeartbeat,
    AggregatorInput,
    AggregatorOutput,
    ContentGeneratorInput,
    ContentGeneratorOutput,
    DataProcessorInput,
    DataProcessorOutput,
    PlannerInput,
    PlannerOutput,
    TaskResultItem,
    ToolCallingInput,
    ToolCallingOutput,
    ToolCallResult,
)
from agents.state_sync import AgentSync

# =========================================================================
# 1. BaseAgent 测试
# =========================================================================


class DummyAgent(BaseAgent):
    """测试用虚拟 Agent。"""

    async def execute(self, task_type: str, payload: dict, trace_id: str | None) -> dict:
        return {"echo": payload, "task_type": task_type, "trace_id": trace_id}

    def supported_task_types(self) -> list[str]:
        return ["test.echo", "*"]


class TestBaseAgent:
    """BaseAgent 生命周期。"""

    @pytest.fixture
    def agent(self) -> DummyAgent:
        config = AgentConfig(
            agent_key="test-agent",
            agent_name="Test Agent",
            base_url="http://127.0.0.1:8000",
            task_types=["test.echo", "*"],
            internal_token="test-token",
            mock_llm=True,
        )
        return DummyAgent(config)

    def test_create_app(self, agent: DummyAgent) -> None:
        app = agent.create_app()
        assert app is not None
        assert app.title == "Test Agent Agent"

    def test_health_endpoint(self, agent: DummyAgent) -> None:
        app = agent.create_app()
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["agent"] == "test-agent"

    def test_capabilities_endpoint(self, agent: DummyAgent) -> None:
        app = agent.create_app()
        client = TestClient(app)
        resp = client.get("/capabilities", headers={"x-internal-token": "test-token"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_key"] == "test-agent"
        assert "test.echo" in data["task_types"]

    def test_capabilities_unauthorized(self, agent: DummyAgent) -> None:
        app = agent.create_app()
        client = TestClient(app)
        resp = client.get("/capabilities")
        assert resp.status_code == 401

    def test_heartbeat_endpoint(self, agent: DummyAgent) -> None:
        app = agent.create_app()
        client = TestClient(app)
        resp = client.get("/heartbeat", headers={"x-internal-token": "test-token"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_key"] == "test-agent"
        assert "current_load" in data

    def test_run_endpoint(self, agent: DummyAgent) -> None:
        app = agent.create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/internal/agent/run",
            json={"task_type": "test.echo", "payload": {"msg": "hello"}, "trace_id": "tr-1"},
            headers={"x-internal-token": "test-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["result"]["echo"]["msg"] == "hello"

    def test_run_unauthorized(self, agent: DummyAgent) -> None:
        app = agent.create_app()
        client = TestClient(app)
        resp = client.post("/api/internal/agent/run", json={"task_type": "test.echo", "payload": {}})
        assert resp.status_code == 401

    def test_run_unsupported_type(self) -> None:
        config = AgentConfig(agent_key="strict", task_types=["only.this"], internal_token="test-token")
        strict_agent = DummyAgent(config)

        # Remove wildcard from supported types
        import types
        strict_agent.supported_task_types = types.MethodType(lambda self: ["only.this"], strict_agent)

        app = strict_agent.create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/internal/agent/run",
            json={"task_type": "wrong.type", "payload": {}},
            headers={"x-internal-token": "test-token"},
        )
        assert resp.status_code == 400

    def test_load_tracking(self, agent: DummyAgent) -> None:
        info = agent.get_heartbeat()
        assert info.current_load == 0
        assert info.uptime_seconds >= 0

    def test_capability_tags(self, agent: DummyAgent) -> None:
        tags = agent.get_capability_tags()
        assert tags["agent_key"] == "test-agent"
        assert "test.echo" in tags["task_types"]
        assert "max_concurrency" in tags


# =========================================================================
# 2. Agent Schemas 测试
# =========================================================================


class TestAgentSchemas:
    """验证所有 Pydantic schema 可正常构造。"""

    def test_planner_input(self) -> None:
        inp = PlannerInput(intent="test", context={"data": 1}, available_capabilities=[{"name": "c1", "task_types": ["t1"]}])
        assert inp.intent == "test"

    def test_planner_output(self) -> None:
        from agents.schemas import PlannerTask
        task = PlannerTask(task_key="a", task_type="t1")
        out = PlannerOutput(plan_id="p1", intent="test", tasks=[task])
        assert len(out.tasks) == 1

    def test_data_processor_input(self) -> None:
        inp = DataProcessorInput(operation="transform", data={"x": 1})
        assert inp.operation == "transform"

    def test_data_processor_output(self) -> None:
        out = DataProcessorOutput(operation="transform", result={"y": 2}, processed_count=1)
        assert out.processed_count == 1

    def test_tool_calling_input(self) -> None:
        from agents.schemas import ToolDefinition, ToolCallRequest
        inp = ToolCallingInput(
            intent="search for something",
            available_tools=[ToolDefinition(name="search", description="search")]
        )
        assert inp.intent == "search for something"

    def test_tool_calling_output(self) -> None:
        out = ToolCallingOutput(
            results=[ToolCallResult(tool_name="s", success=True, result={"a": 1}, duration_ms=10.0)],
            summary="1/1 succeeded"
        )
        assert len(out.results) == 1

    def test_content_generator_input(self) -> None:
        inp = ContentGeneratorInput(
            content_type="blog_post", topic="AI in 2026",
            style="professional", target_audience="developers"
        )
        assert inp.content_type == "blog_post"

    def test_content_generator_output(self) -> None:
        out = ContentGeneratorOutput(
            content_type="blog_post", title="AI in 2026",
            content="AI is changing...", tags=["AI", "2026"], token_count=100
        )
        assert out.title == "AI in 2026"

    def test_aggregator_input(self) -> None:
        inp = AggregatorInput(
            run_id="r1", intent="test",
            task_results=[TaskResultItem(task_key="a", task_type="t1", status="SUCCEEDED", output={"x": 1})]
        )
        assert len(inp.task_results) == 1

    def test_aggregator_output(self) -> None:
        out = AggregatorOutput(run_id="r1", success=True, aggregated_result={"x": 1}, summary="ok")
        assert out.success

    def test_heartbeat(self) -> None:
        hb = AgentHeartbeat(agent_key="a", status="healthy", current_load=2, max_load=10, avg_latency_ms=15.5)
        assert hb.current_load == 2

    def test_error_report(self) -> None:
        err = AgentErrorReport(
            agent_key="a", error_type="Timeout", error_message="timeout after 30s",
            severity="high", retry_recommended=True
        )
        assert err.severity == "high"
        assert err.retry_recommended


# =========================================================================
# 3. 状态同步测试
# =========================================================================


class TestAgentSync:
    """AgentSync 机制。"""

    @pytest.fixture
    def sync(self) -> AgentSync:
        return AgentSync()

    def test_write_read_state(self, sync: AgentSync) -> None:
        sync.write_state("test:state", {"a": 1, "b": 2})
        state = sync.read_state("test:state")
        assert state["a"] == 1

    def test_update_field(self, sync: AgentSync) -> None:
        sync.write_state("test:field", {"a": 1})
        sync.update_state_field("test:field", "a", 100)
        assert sync.read_state("test:field")["a"] == 100

    def test_append_to_list(self, sync: AgentSync) -> None:
        sync.write_state("test:list", {"items": [1]})
        sync.append_to_state_list("test:list", "items", 2)
        items = sync.read_state("test:list")["items"]
        assert items == [1, 2]

    def test_acquire_release_lock(self, sync: AgentSync) -> None:
        assert sync.acquire_lock("test-lock", "owner-1") is True
        assert sync.acquire_lock("test-lock", "owner-2") is False  # 已被锁
        sync.release_lock("test-lock")
        assert sync.acquire_lock("test-lock", "owner-3") is True
        sync.release_lock("test-lock")

    def test_pass_result(self, sync: AgentSync) -> None:
        sync.pass_result_to_next("task-a", "task-b", "run-1", {"data": "hello"})
        key = "pass:run-1:task-a→task-b"
        state = sync.read_state(key)
        assert state["source_task"] == "task-a"
        assert state["result"]["data"] == "hello"

    def test_retry_tracking(self, sync: AgentSync) -> None:
        key = "task:retry-test:run-1:status"
        sync.write_state(key, {"status": "pending", "attempts": 0})
        assert sync.should_retry_task("retry-test", "run-1", max_retries=3)
        sync.record_retry_attempt("retry-test", "run-1")
        sync.record_retry_attempt("retry-test", "run-1")
        sync.record_retry_attempt("retry-test", "run-1")
        assert not sync.should_retry_task("retry-test", "run-1", max_retries=3)

    def test_sync_event_log(self, sync: AgentSync) -> None:
        sync.log_sync_event("run-1", "task-a", "STARTED", {"time": 1})
        sync.log_sync_event("run-1", "task-a", "COMPLETED", {"time": 2})
        events = sync.get_sync_log("run-1")
        assert len(events) == 2
        assert events[0]["event"] == "STARTED"


# =========================================================================
# 4. DataProcessor Agent 功能测试
# =========================================================================


class TestDataProcessorAgent:
    """DataProcessor 各操作。"""

    @pytest.fixture
    def agent_app(self):
        from agents.data_processor_agent import app
        return app

    def test_extract(self, agent_app) -> None:
        client = TestClient(agent_app)
        resp = client.post(
            "/api/internal/agent/run",
            json={
                "task_type": "data.extract",
                "payload": {
                    "operation": "extract",
                    "data": {"name": "John", "age": 30, "city": "HK"},
                    "rules": [{"field": "name"}, {"field": "city"}],
                },
            },
            headers={"x-internal-token": "local-dev-scheduler-token"},
        )
        assert resp.status_code == 200
        result = resp.json()["result"]["result"]
        assert "name" in result
        assert "city" in result
        assert "age" not in result

    def test_transform(self, agent_app) -> None:
        client = TestClient(agent_app)
        resp = client.post(
            "/api/internal/agent/run",
            json={
                "task_type": "data.transform",
                "payload": {
                    "operation": "transform",
                    "data": {"old_name": "data"},
                    "rules": [{"field": "old_name", "action": "rename", "value": "new_name"}],
                },
            },
            headers={"x-internal-token": "local-dev-scheduler-token"},
        )
        assert resp.status_code == 200
        result = resp.json()["result"]["result"]
        assert "old_name" not in result
        assert "new_name" in result

    def test_clean(self, agent_app) -> None:
        client = TestClient(agent_app)
        resp = client.post(
            "/api/internal/agent/run",
            json={
                "task_type": "data.clean",
                "payload": {
                    "operation": "clean",
                    "data": {"name": "  John  ", "empty": "", "null_val": None},
                },
            },
            headers={"x-internal-token": "local-dev-scheduler-token"},
        )
        assert resp.status_code == 200
        result = resp.json()["result"]["result"]
        assert result["name"] == "John"
        assert "empty" not in result

    def test_validate(self, agent_app) -> None:
        client = TestClient(agent_app)
        resp = client.post(
            "/api/internal/agent/run",
            json={
                "task_type": "data.validate",
                "payload": {
                    "operation": "validate",
                    "data": {"name": "John", "age": "not-a-number"},
                    "schema_hint": {"name": "string", "age": "number"},
                },
            },
            headers={"x-internal-token": "local-dev-scheduler-token"},
        )
        assert resp.status_code == 200
        result = resp.json()["result"]["result"]
        assert result["valid"] is False
        assert len(result["errors"]) > 0


# =========================================================================
# 5. ContentGenerator Agent 功能测试 (Mock 模式)
# =========================================================================


class TestContentGeneratorAgent:
    """ContentGenerator Mock 测试。"""

    @pytest.fixture
    def agent_app(self):
        import os
        os.environ.setdefault("AGENT_KEY", "test-content-gen")
        from agents.content_generator_agent import app
        return app

    def test_generate_blog_post(self, agent_app) -> None:
        client = TestClient(agent_app)
        resp = client.post(
            "/api/internal/agent/run",
            json={
                "task_type": "content.blog_post",
                "payload": {
                    "content_type": "blog_post",
                    "topic": "AI Agents in 2026",
                    "instructions": "Write about AI agents",
                    "style": "professional",
                },
            },
            headers={"x-internal-token": "local-dev-scheduler-token"},
        )
        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["content_type"] == "blog_post"
        assert "AI" in result.get("title", "")

    def test_health(self, agent_app) -> None:
        client = TestClient(agent_app)
        resp = client.get("/health")
        assert resp.status_code == 200


# =========================================================================
# 6. ToolCalling Agent 功能测试
# =========================================================================


class TestToolCallingAgent:
    """ToolCalling 工具测试。"""

    @pytest.fixture
    def agent_app(self):
        from agents.tool_calling_agent import app
        return app

    def test_text_stats(self, agent_app) -> None:
        client = TestClient(agent_app)
        resp = client.post(
            "/api/internal/agent/run",
            json={
                "task_type": "tool.execute",
                "payload": {
                    "tool_calls": [{"tool_name": "text_stats", "parameters": {"text": "Hello World!"}}],
                },
            },
            headers={"x-internal-token": "local-dev-scheduler-token"},
        )
        assert resp.status_code == 200
        results = resp.json()["result"]["results"]
        assert results[0]["success"]
        assert results[0]["result"]["word_count"] == 2

    def test_web_search(self, agent_app) -> None:
        client = TestClient(agent_app)
        resp = client.post(
            "/api/internal/agent/run",
            json={
                "task_type": "tool.search",
                "payload": {
                    "tool_calls": [{"tool_name": "web_search", "parameters": {"query": "Python"}}],
                },
            },
            headers={"x-internal-token": "local-dev-scheduler-token"},
        )
        assert resp.status_code == 200
        results = resp.json()["result"]["results"]
        assert results[0]["success"]
