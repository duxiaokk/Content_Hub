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


def test_agent_memory_service_can_search_and_merge_preferences() -> None:
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
        value={"voice": "technical", "blocked_tags": ["营销"]},
        source="test",
    )
    service.upsert_memory(
        scope="workflow",
        scope_key="workflow-a",
        memory_type="feedback",
        memory_key="review-note",
        value={"comment": "需要事实核查"},
        source="test",
    )

    results = service.search_memories(keyword="事实核查", scopes=["workflow"], memory_type="feedback")
    preferences = service.build_rewrite_preferences({"user_id": "user-1"})

    assert len(results) == 1
    assert results[0]["memory_key"] == "review-note"
    assert preferences["tone"] == "concise"
    assert preferences["voice"] == "technical"


def test_agent_memory_service_supports_structured_write_helpers() -> None:
    db = _create_session()
    service = AgentMemoryService(db)

    service.record_preference(
        scope="user",
        scope_key="user-2",
        preference_key="writing_style",
        value={"tone": "formal"},
        source="test",
    )
    service.record_manual_feedback(
        scope="workflow",
        scope_key="workflow-b",
        feedback_key="manual-note",
        value={"comment": "need fact check"},
        source="test",
    )
    service.record_workflow_outcome(
        workflow_name="workflow-b",
        payload={"success_rate": 0.9, "items_total": 10},
        source="test",
    )

    preferences = service.build_rewrite_preferences({"user_id": "user-2"})
    outcome = service.get_memory_value(
        scope="workflow",
        scope_key="workflow-b",
        memory_type="outcome",
        memory_key="last_run",
    )
    feedback_results = service.search_memories(keyword="fact check", scopes=["workflow"], memory_type="feedback")

    assert preferences["tone"] == "formal"
    assert outcome["items_total"] == 10
    assert len(feedback_results) == 1
    assert feedback_results[0]["memory_key"] == "manual-note"
