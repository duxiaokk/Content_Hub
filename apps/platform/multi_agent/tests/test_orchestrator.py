"""测试 Multi-Agent Orchestrator 核心流程。"""
from __future__ import annotations

import pytest

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
