from __future__ import annotations

import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from agents.base_agent import AgentConfig
from agents.planner_agent import PlannerAgent
from apps.platform.database import Base
from apps.platform.services.agent_memory_service import AgentMemoryService


def _create_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return factory()


def test_agent_memory_service_builds_planner_context() -> None:
    db = _create_session()
    service = AgentMemoryService(db)
    service.upsert_memory(
        scope="global",
        scope_key=None,
        memory_type="preference",
        memory_key="default_style",
        value={"tone": "concise"},
        source="test",
    )
    service.upsert_memory(
        scope="user",
        scope_key="user-1",
        memory_type="preference",
        memory_key="rewrite_style",
        value={"language": "zh", "voice": "technical"},
        source="test",
    )
    service.upsert_memory(
        scope="workflow",
        scope_key="radar",
        memory_type="outcome",
        memory_key="last_run",
        value={"success_rate": 0.8},
        source="test",
    )

    context = service.build_planner_context({"user_id": "user-1", "workflow_name": "radar"})

    assert context["global"]["preference"]["default_style"]["tone"] == "concise"
    assert context["user"]["preference"]["rewrite_style"]["voice"] == "technical"
    assert context["workflow"]["outcome"]["last_run"]["success_rate"] == 0.8


def test_planner_agent_injects_memory_context(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_plan_with_rules(self, intent, capabilities, context, is_complex=False):  # noqa: ANN001
        captured["intent"] = intent
        captured["context"] = context
        return {"plan_id": "plan-1", "intent": intent, "tasks": []}

    monkeypatch.setattr(PlannerAgent, "_plan_with_rules", fake_plan_with_rules)
    monkeypatch.setattr(
        PlannerAgent,
        "_load_memory_context",
        staticmethod(lambda context: {"user": {"preference": {"rewrite_style": {"voice": "technical"}}}}),
    )

    agent = PlannerAgent(
        AgentConfig(
            agent_key="planner-agent",
            task_types=["plan.decompose"],
            mock_llm=True,
        )
    )
    asyncio.run(
        agent.execute(
            "plan.decompose",
            {"intent": "generate workflow", "context": {"user_id": "user-1"}, "available_capabilities": []},
            None,
        )
    )

    injected_context = captured["context"]
    assert isinstance(injected_context, dict)
    assert injected_context["memory_context"]["user"]["preference"]["rewrite_style"]["voice"] == "technical"


def test_agent_memory_service_returns_latest_memory_value() -> None:
    db = _create_session()
    service = AgentMemoryService(db)
    service.upsert_memory(
        scope="workflow",
        scope_key="content.workflow.planned",
        memory_type="outcome",
        memory_key="last_run",
        value={"success_rate": 0.4, "suggested_limit": 8},
        source="test",
    )

    value = service.get_memory_value(
        scope="workflow",
        scope_key="content.workflow.planned",
        memory_type="outcome",
        memory_key="last_run",
    )

    assert isinstance(value, dict)
    assert value["success_rate"] == 0.4
    assert value["suggested_limit"] == 8
