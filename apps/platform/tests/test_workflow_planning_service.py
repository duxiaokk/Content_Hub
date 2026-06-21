from __future__ import annotations

from apps.platform.services.agent_memory_service import AgentMemoryService
from apps.platform.services.workflow_planning_service import WorkflowPlanningService


def test_workflow_planning_service_builds_tool_stage_plan() -> None:
    service = WorkflowPlanningService()

    plan, payload = service.plan_workflow(
        intent="抓取 GitHub 内容并搜索补充背景后生成中文摘要",
        context={"enable_tool_stage": True, "search_query": "GitHub Python trending"},
        constraints={"limit": 10},
    )

    assert len(plan.tasks) == 4
    assert payload["fetcher_name"] == "github_trending"
    assert payload["limit"] == 10
    assert any(node["stage"] == "tool" for node in payload["nodes"])


def test_workflow_planning_service_applies_memory_tuning(monkeypatch) -> None:
    monkeypatch.setattr(
        AgentMemoryService,
        "get_memory_value",
        lambda self, **kwargs: {"success_rate": 0.3, "suggested_limit": 8, "suggested_lookback_hours": 72},
    )

    service = WorkflowPlanningService()
    plan, payload = service.plan_workflow(
        intent="生成日报",
        context={"workflow_name": "content.workflow.planned"},
        constraints={"limit": 20, "lookback_hours": 24},
    )

    assert payload["limit"] == 8
    assert payload["lookback_hours"] == 72
    assert plan.metadata["memory_tuning"]["applied"] is True


def test_workflow_planning_service_uses_explicit_context_overrides() -> None:
    service = WorkflowPlanningService()

    plan, payload = service.plan_workflow(
        intent="生成日报",
        context={
            "fetcher_name": "reddit",
            "source_name": "reddit_python",
            "processor_name": "rewrite",
            "publisher_name": "markdown",
            "lookback_hours": 6,
        },
    )

    assert plan.metadata["source_name"] == "reddit_python"
    assert payload["fetcher_name"] == "reddit"
    assert payload["publisher_name"] == "markdown"
    assert payload["lookback_hours"] == 6


def test_workflow_planning_service_calls_planner_agent(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_decompose(self, *, intent, context, constraints):  # noqa: ANN001
        captured["intent"] = intent
        captured["context"] = context
        captured["constraints"] = constraints
        return {"plan_id": "planner-1", "tasks": [{"task_key": "tool", "task_type": "tool.execute"}]}

    monkeypatch.setattr(WorkflowPlanningService, "_decompose_with_planner", fake_decompose)

    service = WorkflowPlanningService()
    plan, payload = service.plan_workflow(
        intent="抓取 GitHub 内容并搜索补充背景后生成中文摘要",
        context={"workflow_name": "content.workflow.planned"},
    )

    assert captured["intent"] == "抓取 GitHub 内容并搜索补充背景后生成中文摘要"
    assert isinstance(captured["context"], dict)
    assert plan.plan_id == "planner-1"
    assert any(node["stage"] == "tool" for node in payload["nodes"])
