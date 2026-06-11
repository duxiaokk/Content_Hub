from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret-key")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scheduler_center.dag import DAG
from scheduler_center.orchestration_schemas import (
    AggregatorRequest,
    AgentCapability,
    PlannerRequest,
    TaskResult,
)
from services.aggregator_service import AggregatorAgent, AggregatorConfig
from services.planner_service import PlannerAgent, PlannerConfig


class TestDAG:
    def test_build_simple_chain(self) -> None:
        dag = DAG()
        dag.add_node("A")
        dag.add_node("B", depends_on=["A"])
        dag.add_node("C", depends_on=["B"])
        assert dag.is_valid()
        assert dag.topological_order() == ["A", "B", "C"]

    def test_parallel_tasks(self) -> None:
        dag = DAG()
        dag.add_node("A")
        dag.add_node("B", depends_on=["A"])
        dag.add_node("C", depends_on=["A"])
        dag.add_node("D", depends_on=["B", "C"])
        assert dag.topological_layers() == [["A"], ["B", "C"], ["D"]]
        assert dag.max_parallelism() == 2


class TestPlanner:
    CAPS = [
        AgentCapability(agent_key="gen", name="Generator", task_types=["generate_draft"], description="draft"),
        AgentCapability(agent_key="audit", name="Auditor", task_types=["audit_draft"], description="audit"),
        AgentCapability(agent_key="analyze", name="Analyzer", task_types=["analyze_blog"], description="analyze"),
    ]

    def test_plan_generate_and_audit(self) -> None:
        planner = PlannerAgent(PlannerConfig(use_mock=True))
        req = PlannerRequest(intent="生成一篇博客并审核", available_capabilities=self.CAPS)
        resp = planner.plan(req)
        assert resp.success
        assert resp.plan is not None
        task_types = {t.task_type for t in resp.plan.tasks}
        assert task_types & {"generate_draft", "audit_draft"}

    def test_plan_empty_capabilities(self) -> None:
        planner = PlannerAgent(PlannerConfig(use_mock=True))
        resp = planner.plan(PlannerRequest(intent="test", available_capabilities=[]))
        assert not resp.success
        assert resp.error is not None


class TestAggregator:
    def test_merge_all_success(self) -> None:
        agg = AggregatorAgent(AggregatorConfig(mode="merge"))
        req = AggregatorRequest(
            run_id="run-1",
            intent="test",
            task_results=[
                TaskResult(task_key="a", task_type="t1", status="SUCCEEDED", output={"x": 1}),
                TaskResult(task_key="b", task_type="t2", status="SUCCEEDED", output={"y": 2}),
            ],
        )
        resp = agg.aggregate(req)
        assert resp.success
        assert resp.status == "SUCCEEDED"

    def test_merge_partial_failure(self) -> None:
        agg = AggregatorAgent(AggregatorConfig(mode="merge"))
        req = AggregatorRequest(
            run_id="run-2",
            intent="test",
            task_results=[
                TaskResult(task_key="a", task_type="t1", status="SUCCEEDED", output={"x": 1}),
                TaskResult(task_key="b", task_type="t2", status="FAILED", output={}, error="timeout"),
            ],
        )
        resp = agg.aggregate(req)
        assert resp.success
        assert resp.status == "PARTIAL"
