"""测试 Multi-Agent Orchestrator 核心流程。"""
from __future__ import annotations

import pytest
from apps.platform.multi_agent.agent_registry import AgentRegistry
from apps.platform.multi_agent.message_bus import MessageBus
from apps.platform.multi_agent.message_schemas import AgentMessage
from apps.platform.multi_agent.orchestrator import Orchestrator


@pytest.fixture
def message_bus(tmp_path):
    db = tmp_path / "test_messages.db"
    return MessageBus(str(db))


class TestMessageBus:
    """Message Bus 基础功能测试。"""

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
    """Orchestrator 降级逻辑测试（不依赖外部 Agent 服务）。"""

    def test_fallback_plan_fetch_analyze_generate(self) -> None:
        orchestrator = Orchestrator()
        plan = orchestrator._fallback_plan("抓取 GitHub 并分析生成摘要")
        assert len(plan["tasks"]) >= 2
        task_keys = [t["task_key"] for t in plan["tasks"]]
        assert "fetch" in task_keys
        assert "analyze" in task_keys
        assert "generate" in task_keys

    def test_fallback_plan_generate_only(self) -> None:
        orchestrator = Orchestrator()
        plan = orchestrator._fallback_plan("随便生成点什么")
        assert len(plan["tasks"]) == 1
        assert plan["tasks"][0]["task_key"] == "generate"

    def test_build_capability_list(self, message_bus: MessageBus, db_session) -> None:
        # 没有注册 Agent 时返回空列表
        registry = AgentRegistry(db=db_session)
        orchestrator = Orchestrator(message_bus=message_bus, registry=registry)
        caps = orchestrator._build_capability_list()
        assert isinstance(caps, list)
        assert caps == []
