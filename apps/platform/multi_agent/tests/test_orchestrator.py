"""测试 Multi-Agent Orchestrator 核心流程。"""
from __future__ import annotations

import httpx
import pytest

from agents.base_agent import AgentConfig
from agents.tool_calling_agent import ToolCallingAgent
from apps.platform.multi_agent.agent_registry import AgentRegistry
from apps.platform.multi_agent.message_bus import MessageBus
from apps.platform.multi_agent.message_schemas import AgentMessage
from apps.platform.multi_agent.orchestrator import Orchestrator
from apps.platform.multi_agent.plan_runtime import PlanRuntime


@pytest.fixture
def message_bus(tmp_path):
    db = tmp_path / "test_messages.db"
    return MessageBus(str(db))


class TestMessageBus:
    def test_enqueue_and_dequeue(self, message_bus: MessageBus) -> None:
        msg = AgentMessage(
            sender="orchestrator",
            recipient="planner-agent",
            message_type="task",
            payload={"intent": "test"},
            trace_id="trace-001",
        )
        msg_id = message_bus.enqueue(msg)
        assert msg_id is not None

        received = message_bus.dequeue("planner-agent")
        assert len(received) == 1
        assert received[0].message_type == "task"
        assert received[0].status == "delivered"

    def test_ack(self, message_bus: MessageBus) -> None:
        msg = AgentMessage(
            sender="orchestrator",
            recipient="agent-1",
            message_type="task",
            payload={},
            trace_id="trace-002",
        )
        msg_id = message_bus.enqueue(msg)
        message_bus.dequeue("agent-1")
        assert message_bus.ack(msg_id) is True

    def test_get_messages_by_trace_id(self, message_bus: MessageBus) -> None:
        for i in range(3):
            message_bus.enqueue(
                AgentMessage(
                    sender="orchestrator",
                    recipient="agent-1",
                    message_type="task",
                    payload={"idx": i},
                    trace_id="trace-003",
                )
            )
        msgs = message_bus.get_messages("trace-003")
        assert len(msgs) == 3

    def test_count_pending(self, message_bus: MessageBus) -> None:
        message_bus.enqueue(
            AgentMessage(
                sender="orchestrator",
                recipient="agent-2",
                message_type="task",
                payload={},
                trace_id="trace-004",
            )
        )
        assert message_bus.count_pending("agent-2") == 1
        message_bus.dequeue("agent-2")
        assert message_bus.count_pending("agent-2") == 0


class TestOrchestratorFallback:
    def test_fallback_plan_fetch_analyze_generate(self) -> None:
        orchestrator = Orchestrator()
        plan = orchestrator._fallback_plan("抓取 GitHub 并分析生成摘要")
        assert len(plan["tasks"]) >= 2
        task_keys = [task["task_key"] for task in plan["tasks"]]
        assert "fetch" in task_keys
        assert "analyze" in task_keys
        assert "generate" in task_keys

    def test_fallback_plan_generate_only(self) -> None:
        orchestrator = Orchestrator()
        plan = orchestrator._fallback_plan("随便生成点什么")
        assert len(plan["tasks"]) == 1
        assert plan["tasks"][0]["task_key"] == "generate"

    def test_build_capability_list(self, message_bus: MessageBus, db_session) -> None:
        registry = AgentRegistry(db=db_session)
        orchestrator = Orchestrator(message_bus=message_bus, registry=registry)
        caps = orchestrator._build_capability_list()
        assert isinstance(caps, list)
        assert caps == []


class TestPlanRuntime:
    @pytest.mark.anyio
    async def test_expand_sub_tasks_into_flat_dag(self) -> None:
        runtime = PlanRuntime.from_plan(
            {
                "plan_id": "plan-1",
                "intent": "test",
                "tasks": [
                    {
                        "task_key": "root",
                        "task_type": "root.task",
                        "sub_tasks": [
                            {"task_key": "child_a", "task_type": "child.a"},
                            {"task_key": "child_b", "task_type": "child.b", "depends_on": ["child_a"]},
                        ],
                    }
                ],
            }
        )

        assert [task.task_key for task in runtime.tasks] == [
            "root",
            "root.child_a",
            "root.child_b",
        ]
        assert runtime.tasks[1].depends_on == ["root"]
        assert runtime.tasks[2].depends_on == ["root.child_a"]

    @pytest.mark.anyio
    async def test_branch_on_success_activates_success_path_and_skips_failure_path(self) -> None:
        runtime = PlanRuntime.from_plan(
            {
                "plan_id": "plan-2",
                "intent": "test",
                "tasks": [
                    {
                        "task_key": "gate",
                        "task_type": "gate.task",
                        "branch_on": {"success": "success_path", "failure": "failure_path"},
                    },
                    {"task_key": "success_path", "task_type": "success.task", "depends_on": ["gate"]},
                    {"task_key": "failure_path", "task_type": "failure.task", "depends_on": ["gate"]},
                ],
            }
        )

        executed: list[str] = []

        async def executor(task):
            executed.append(task.task_key)
            return {"status": "SUCCEEDED", "output": {"task_key": task.task_key}}

        results = await runtime.run(executor)
        assert executed == ["gate", "success_path"]
        assert results["success_path"]["status"] == "SUCCEEDED"
        assert results["failure_path"]["status"] == "SKIPPED"

    @pytest.mark.anyio
    async def test_retry_uses_max_retries_and_eventually_succeeds(self) -> None:
        runtime = PlanRuntime.from_plan(
            {
                "plan_id": "plan-3",
                "intent": "test",
                "tasks": [
                    {
                        "task_key": "unstable",
                        "task_type": "unstable.task",
                        "max_retries": 2,
                        "retry_delay_seconds": 0.0,
                    }
                ],
            }
        )

        attempts = {"unstable": 0}

        async def executor(task):
            attempts[task.task_key] += 1
            if attempts[task.task_key] < 3:
                return {"status": "FAILED", "error": "temporary"}
            return {"status": "SUCCEEDED", "output": {"attempt": attempts[task.task_key]}}

        results = await runtime.run(executor)
        assert attempts["unstable"] == 3
        assert results["unstable"]["status"] == "SUCCEEDED"
        assert results["unstable"]["attempt_count"] == 3

    @pytest.mark.anyio
    async def test_branch_on_failure_activates_failure_path(self) -> None:
        runtime = PlanRuntime.from_plan(
            {
                "plan_id": "plan-4",
                "intent": "test",
                "tasks": [
                    {
                        "task_key": "gate",
                        "task_type": "gate.task",
                        "max_retries": 0,
                        "branch_on": {"success": "success_path", "failure": "failure_path"},
                    },
                    {"task_key": "success_path", "task_type": "success.task", "depends_on": ["gate"]},
                    {"task_key": "failure_path", "task_type": "failure.task", "depends_on": ["gate"]},
                ],
            }
        )

        executed: list[str] = []

        async def executor(task):
            executed.append(task.task_key)
            if task.task_key == "gate":
                return {"status": "FAILED", "error": "boom"}
            return {"status": "SUCCEEDED", "output": {"task_key": task.task_key}}

        results = await runtime.run(executor)
        assert executed == ["gate", "failure_path"]
        assert results["gate"]["status"] == "FAILED"
        assert results["failure_path"]["status"] == "SUCCEEDED"
        assert results["success_path"]["status"] == "SKIPPED"

    @pytest.mark.anyio
    async def test_condition_true_allows_task_execution(self) -> None:
        runtime = PlanRuntime.from_plan(
            {
                "plan_id": "plan-5",
                "intent": "test",
                "tasks": [
                    {"task_key": "fetch", "task_type": "fetch.task"},
                    {
                        "task_key": "publish",
                        "task_type": "publish.task",
                        "depends_on": ["fetch"],
                        "condition": 'statuses.fetch == "SUCCEEDED" and outputs.fetch.allow_publish is True',
                    },
                ],
            }
        )

        executed: list[str] = []

        async def executor(task):
            executed.append(task.task_key)
            if task.task_key == "fetch":
                return {"status": "SUCCEEDED", "output": {"allow_publish": True}}
            return {"status": "SUCCEEDED", "output": {"published": True}}

        results = await runtime.run(executor)
        assert executed == ["fetch", "publish"]
        assert results["publish"]["status"] == "SUCCEEDED"

    @pytest.mark.anyio
    async def test_condition_false_skips_task(self) -> None:
        runtime = PlanRuntime.from_plan(
            {
                "plan_id": "plan-6",
                "intent": "test",
                "tasks": [
                    {"task_key": "fetch", "task_type": "fetch.task"},
                    {
                        "task_key": "publish",
                        "task_type": "publish.task",
                        "depends_on": ["fetch"],
                        "condition": 'outputs.fetch.allow_publish is True',
                    },
                ],
            }
        )

        executed: list[str] = []

        async def executor(task):
            executed.append(task.task_key)
            return {"status": "SUCCEEDED", "output": {"allow_publish": False}}

        results = await runtime.run(executor)
        assert executed == ["fetch"]
        assert results["publish"]["status"] == "SKIPPED"


class TestOrchestratorToolPlan:
    @pytest.mark.anyio
    async def test_orchestrator_executes_tool_plan_via_tool_calling_agent(self, monkeypatch, tmp_path) -> None:
        class StubAgent:
            def __init__(self, agent_key: str, base_url: str) -> None:
                self.agent_key = agent_key
                self.base_url = base_url
                self.task_types = []
                self.capabilities = {}

        class StubRegistry:
            def find_agent_by_task_type(self, task_type: str):  # noqa: ANN001
                if task_type == "tool.execute":
                    return StubAgent("tool-calling-agent", "http://tool-agent")
                if task_type == "aggregate.merge":
                    return StubAgent("aggregator-agent", "http://aggregator-agent")
                return None

            def list_agents(self) -> list[object]:
                return []

        class FakeResponse:
            def __init__(self, payload: dict[str, object]) -> None:
                self._payload = payload
                self.status_code = 200

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return self._payload

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
                return None

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
                return None

            async def post(self, url: str, json: dict, headers: dict | None = None):  # noqa: A002
                if url.startswith("http://tool-agent"):
                    agent = ToolCallingAgent(
                        AgentConfig(
                            agent_key="tool-calling-agent",
                            task_types=["tool.execute"],
                            mock_llm=True,
                        )
                    )
                    result = await agent.execute(json["task_type"], json["payload"], json.get("trace_id"))
                    return FakeResponse({"result": result})
                if url.startswith("http://aggregator-agent"):
                    task_results = json["payload"]["task_results"]
                    return FakeResponse(
                        {
                            "result": {
                                "success": True,
                                "aggregated_result": {"tasks": task_results},
                                "summary": "ok",
                            }
                        }
                    )
                raise AssertionError(f"unexpected url: {url}")

        async def fake_call_planner(self, intent: str, trace_id: str, context: dict | None):  # noqa: ANN001
            return {
                "plan_id": "plan-tool",
                "intent": intent,
                "tasks": [
                    {
                        "task_key": "tool_chain",
                        "task_type": "tool.execute",
                        "input_payload": {
                            "context": {"fetched_items": [{"title": "Hello Tool Plan"}]},
                            "tool_plan": {
                                "steps": [
                                    {
                                        "id": "stats",
                                        "tool_name": "text_stats",
                                        "input_template": {"text": "{context.fetched_items.0.title}"},
                                        "output_key": "stats",
                                    },
                                    {
                                        "id": "search",
                                        "tool_name": "web_search",
                                        "input_template": {"query": "count-{outputs.stats.result.word_count}"},
                                        "output_key": "search",
                                    },
                                ]
                            },
                        },
                    }
                ],
            }

        monkeypatch.setattr(Orchestrator, "_call_planner", fake_call_planner)
        monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

        orchestrator = Orchestrator(
            message_bus=MessageBus(str(tmp_path / "tool_plan_messages.db")),
            registry=StubRegistry(),
        )
        result = await orchestrator.execute("执行 tool plan")

        assert result.success is True
        tasks = result.aggregated_result["tasks"]
        assert tasks[0]["task_key"] == "tool_chain"
        assert tasks[0]["output"]["outputs"]["search"]["result"]["query"] == "count-3"
