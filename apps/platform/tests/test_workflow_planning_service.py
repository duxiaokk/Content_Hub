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

    assert len(plan.tasks) >= 4
    assert payload["fetcher_name"] == "github_trending"
    assert payload["limit"] == 10
    assert any(node["stage"] == "tool" for node in payload["nodes"])
    assert any(task.task_type == "workflow.publish" for task in plan.tasks)


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


def test_workflow_planning_service_maps_multiple_planner_tasks(monkeypatch) -> None:
    def fake_decompose(self, *, intent, context, constraints):  # noqa: ANN001
        return {
            "plan_id": "planner-2",
            "tasks": [
                {"task_key": "fetch", "task_type": "workflow.fetch", "input_payload": {"fetcher_name": "github_trending"}},
                {
                    "task_key": "tool_search",
                    "task_type": "tool.execute",
                    "depends_on": ["fetch"],
                    "description": "搜索补充背景",
                    "input_payload": {
                        "tool_calls": [{"tool_name": "web_search", "parameters": {"query": "GitHub Python trending"}}],
                        "result_key": "search_context",
                    },
                },
                {
                    "task_key": "process",
                    "task_type": "workflow.process",
                    "depends_on": ["tool_search"],
                    "input_payload": {"processor_name": "summarize"},
                },
            ],
        }

    monkeypatch.setattr(WorkflowPlanningService, "_decompose_with_planner", fake_decompose)
    monkeypatch.setattr(
        AgentMemoryService,
        "build_rewrite_preferences",
        lambda self, context=None: {"voice": "technical", "tone": "concise"},
    )

    service = WorkflowPlanningService()
    plan, payload = service.plan_workflow(
        intent="抓取 GitHub 内容并搜索补充背景后生成中文摘要",
        context={"workflow_name": "content.workflow.planned"},
    )

    assert plan.plan_id == "planner-2"
    assert [node["stage"] for node in payload["nodes"]] == ["fetch", "tool", "process", "publish"]
    assert payload["nodes"][1]["options"]["result_key"] == "search_context"
    assert payload["nodes"][2]["options"]["preferred_voice"] == "technical"
    assert plan.metadata["rewrite_preferences"]["tone"] == "concise"


def test_workflow_planning_service_inserts_tool_stage_from_observations(monkeypatch) -> None:
    monkeypatch.setattr(
        AgentMemoryService,
        "get_memory_value",
        lambda self, **kwargs: {
            "success_rate": 0.9,
            "observations": {
                "fetch_quality": {"quality_score": 0.3},
                "tool_hit_rate": {"attempts": 0, "hits": 0, "hit_rate": 0.0},
                "process_quality": {"average_quality_score": 0.9},
                "review_failure_reasons": {"top_reasons": [], "counts": {}},
            },
        },
    )

    service = WorkflowPlanningService()
    plan, payload = service.plan_workflow(
        intent="生成日报",
        context={"workflow_name": "content.workflow.planned"},
    )

    assert any(node["stage"] == "tool" for node in payload["nodes"])
    assert plan.metadata["observation_tuning"]["insert_tool_before_process"] is True


def test_workflow_planning_service_enables_quality_gate_from_observations(monkeypatch) -> None:
    monkeypatch.setattr(
        AgentMemoryService,
        "get_memory_value",
        lambda self, **kwargs: {
            "success_rate": 0.9,
            "observations": {
                "fetch_quality": {"quality_score": 0.9},
                "tool_hit_rate": {"attempts": 1, "hits": 1, "hit_rate": 1.0},
                "process_quality": {"average_quality_score": 0.5},
                "review_failure_reasons": {"top_reasons": [{"reason": "rewrite_quality", "count": 2}], "counts": {"rewrite_quality": 2}},
            },
        },
    )

    service = WorkflowPlanningService()
    plan, payload = service.plan_workflow(
        intent="生成日报",
        context={"workflow_name": "content.workflow.planned"},
    )

    assert payload["publish_options"]["enable_quality_gate"] is True
    assert payload["process_options"]["rewrite_self_critique_rounds"] == 2
    assert plan.metadata["next_run_suggestions"]
