"""编排内核测试

覆盖: DAG 引擎, Planner, Aggregator, 命名规范, 编排引擎集成

运行: pytest tests/test_orchestration.py -v
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from scheduler_center.dag import DAG, DAGNode
from scheduler_center.database import Base as SchBase
from scheduler_center.orchestration_models import Base as OrchBase, OrchestrationRun, OrchestrationTask, RunStatus, TaskOrchStatus
from scheduler_center.orchestration_schemas import (
    AgentCapability,
    ExecutionPlan,
    PlannerRequest,
    PlannerResponse,
    PlanTask,
    AggregatorRequest,
    AggregatorResponse,
    TaskResult,
)
from services.planner_service import PlannerAgent, PlannerConfig
from services.aggregator_service import AggregatorAgent, AggregatorConfig
from core.memory_naming import RunNaming, TaskNaming


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture(scope="module")
def db_engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SchBase.metadata.create_all(bind=eng)
    OrchBase.metadata.create_all(bind=eng)
    yield eng
    OrchBase.metadata.drop_all(bind=eng)
    SchBase.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture
def db_session(db_engine) -> Session:
    conn = db_engine.connect()
    trans = conn.begin()
    session = Session(bind=conn)
    yield session
    session.close()
    trans.rollback()
    conn.close()


# =========================================================================
# 1. DAG 引擎测试
# =========================================================================


class TestDAG:
    """DAG 构建、验证、排序、依赖解析。"""

    def test_build_simple_chain(self):
        dag = DAG()
        dag.add_node("A")
        dag.add_node("B", depends_on=["A"])
        dag.add_node("C", depends_on=["B"])
        assert dag.is_valid()
        assert dag.topological_order() == ["A", "B", "C"]

    def test_parallel_tasks(self):
        dag = DAG()
        dag.add_node("A")
        dag.add_node("B", depends_on=["A"])
        dag.add_node("C", depends_on=["A"])
        dag.add_node("D", depends_on=["B", "C"])
        assert dag.is_valid()
        layers = dag.topological_layers()
        assert layers == [["A"], ["B", "C"], ["D"]]
        assert dag.max_parallelism() == 2

    def test_cycle_detection(self):
        dag = DAG()
        dag.add_node("A", depends_on=["B"])
        dag.add_node("B", depends_on=["A"])
        assert dag.has_cycle()
        with pytest.raises(ValueError, match="cycle"):
            dag.is_valid()

    def test_diamond_dag(self):
        dag = DAG()
        dag.add_node("A")
        dag.add_node("B", depends_on=["A"])
        dag.add_node("C", depends_on=["A"])
        dag.add_node("D", depends_on=["B", "C"])
        assert dag.get_root_nodes() == {"A"}
        assert dag.get_leaf_nodes() == {"D"}
        assert dag.all_dependencies_of("D") == {"A", "B", "C"}

    def test_ready_nodes(self):
        dag = DAG()
        dag.add_node("A")
        dag.add_node("B", depends_on=["A"])
        dag.add_node("C", depends_on=["A"])

        assert dag.ready_nodes(set()) == {"A"}
        assert dag.ready_nodes({"A"}) == {"B", "C"}
        assert dag.ready_nodes({"A", "B"}) == {"C"}
        assert dag.ready_nodes({"A", "B", "C"}) == set()

    def test_empty_dag(self):
        dag = DAG()
        assert dag.is_valid()
        assert dag.topological_order() == []
        assert dag.topological_layers() == []

    def test_single_node(self):
        dag = DAG()
        dag.add_node("single")
        assert dag.topological_order() == ["single"]
        assert dag.topological_layers() == [["single"]]
        assert dag.max_parallelism() == 1

    def test_serialization(self):
        dag = DAG()
        dag.add_node("A", data={"type": "generate"})
        dag.add_node("B", depends_on=["A"])
        d = dag.to_dict()
        restored = DAG.from_dict(d)
        assert restored.topological_order() == ["A", "B"]
        assert restored.nodes["A"].data == {"type": "generate"}

    def test_missing_dependency_auto_created(self):
        """add_node 会自动创建不存在的父节点（容错设计）。"""
        dag = DAG()
        dag.add_node("A")
        dag.add_node("B", depends_on=["C"])  # C 自动创建
        assert dag.is_valid()
        assert "C" in dag.nodes
        assert dag.topological_order() == ["A", "C", "B"]


# =========================================================================
# 2. Planner 测试
# =========================================================================


class TestPlanner:
    """Planner Agent 任务拆解。"""

    CAPS = [
        AgentCapability(agent_key="gen", name="Generator", task_types=["generate_draft"], description="生成草稿"),
        AgentCapability(agent_key="audit", name="Auditor", task_types=["audit_draft"], description="审核草稿"),
        AgentCapability(agent_key="analyze", name="Analyzer", task_types=["analyze_blog"], description="分析"),
    ]

    def test_plan_generate_and_audit(self):
        planner = PlannerAgent(PlannerConfig(use_mock=True))
        req = PlannerRequest(
            intent="生成一篇博文并审核",
            available_capabilities=self.CAPS,
        )
        resp = planner.plan(req)
        assert resp.success
        assert resp.plan is not None
        assert len(resp.plan.tasks) >= 1
        task_types = {t.task_type for t in resp.plan.tasks}
        assert "generate_draft" in task_types or "audit_draft" in task_types

    def test_plan_analyze(self):
        planner = PlannerAgent(PlannerConfig(use_mock=True))
        req = PlannerRequest(
            intent="分析平台数据并推荐选题",
            available_capabilities=self.CAPS,
        )
        resp = planner.plan(req)
        assert resp.success
        task_types = {t.task_type for t in resp.plan.tasks}
        assert "analyze_blog" in task_types

    def test_plan_empty_capabilities(self):
        planner = PlannerAgent(PlannerConfig(use_mock=True))
        req = PlannerRequest(intent="test", available_capabilities=[])
        resp = planner.plan(req)
        assert not resp.success
        assert resp.error is not None

    def test_plan_contains_dependencies(self):
        planner = PlannerAgent(PlannerConfig(use_mock=True))
        req = PlannerRequest(
            intent="搬运YouTube内容并审核",
            available_capabilities=self.CAPS,
        )
        resp = planner.plan(req)
        if resp.plan and len(resp.plan.tasks) > 1:
            has_dep = any(t.depends_on for t in resp.plan.tasks)
            # 搬运+审核应该是串行
            assert has_dep or len(resp.plan.tasks) == 1


# =========================================================================
# 3. Aggregator 测试
# =========================================================================


class TestAggregator:
    """Aggregator Agent 结果聚合。"""

    def test_merge_all_success(self):
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
        assert resp.aggregated_result["total"] == 2
        assert resp.aggregated_result["succeeded"] == 2

    def test_merge_partial_failure(self):
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
        assert resp.aggregated_result["succeeded"] == 1
        assert resp.aggregated_result["failed"] == 1

    def test_merge_all_failed(self):
        agg = AggregatorAgent(AggregatorConfig(mode="merge"))
        req = AggregatorRequest(
            run_id="run-3",
            intent="test",
            task_results=[
                TaskResult(task_key="a", task_type="t1", status="FAILED", output={}, error="err1"),
                TaskResult(task_key="b", task_type="t2", status="FAILED", output={}, error="err2"),
            ],
        )
        resp = agg.aggregate(req)
        assert not resp.success
        assert "All tasks failed" in (resp.error or "")

    def test_aggregate_empty_results(self):
        agg = AggregatorAgent()
        req = AggregatorRequest(run_id="run-4", intent="test", task_results=[])
        resp = agg.aggregate(req)
        assert resp.success
        assert resp.status == "SUCCEEDED"


# =========================================================================
# 4. 命名规范测试
# =========================================================================


class TestMemoryNaming:
    """Shared Memory 命名规范。"""

    def test_run_naming_status(self):
        assert RunNaming.status("run-1") == "run:run-1:status"
        assert RunNaming.plan("run-1") == "run:run-1:plan"
        assert RunNaming.checkpoint("run-1") == "run:run-1:checkpoint"
        assert RunNaming.result("run-1") == "run:run-1:task_result"

    def test_task_naming_output(self):
        assert TaskNaming.output("gen", "run-1") == "task:gen:run-1:output"
        assert TaskNaming.input("gen", "run-1") == "task:gen:run-1:input"
        assert TaskNaming.artifact("gen", "run-1") == "task:gen:run-1:artifact"
        assert TaskNaming.status("gen", "run-1") == "task:gen:run-1:status"

    def test_naming_scopes(self):
        assert RunNaming.scope("run-1") == "run:run-1"
        assert TaskNaming.scope("gen", "run-1") == "task:gen:run-1"


# =========================================================================
# 5. 编排模型 CRUD 测试
# =========================================================================


class TestOrchestrationModels:
    """编排数据模型 CRUD。"""

    def test_create_run(self, db_session):
        run = OrchestrationRun(
            id="run-test-1",
            trace_id="trace-1",
            name="test run",
            status=RunStatus.PENDING,
            total_tasks=3,
        )
        db_session.add(run)
        db_session.commit()
        assert run.id == "run-test-1"

    def test_create_orch_task(self, db_session):
        run = OrchestrationRun(id="run-test-2", trace_id="trace-2", total_tasks=1)
        db_session.add(run)
        db_session.flush()

        task = OrchestrationTask(
            id="ot-1",
            run_id=run.id,
            task_key="generate",
            task_type="generate_draft",
            depends_on_json=json.dumps(["analyze"]),
            status=TaskOrchStatus.BLOCKED,
        )
        db_session.add(task)
        db_session.commit()

        loaded = db_session.query(OrchestrationTask).filter(OrchestrationTask.run_id == run.id).first()
        assert loaded is not None
        assert loaded.task_key == "generate"
        deps = json.loads(loaded.depends_on_json or "[]")
        assert "analyze" in deps

    def test_run_status_transitions(self, db_session):
        run = OrchestrationRun(id="run-st", trace_id="trace-st", status=RunStatus.PENDING, total_tasks=1)
        db_session.add(run)
        db_session.commit()

        run.status = RunStatus.RUNNING
        db_session.commit()
        assert run.status == "RUNNING"

        run.status = RunStatus.SUCCEEDED
        db_session.commit()
        assert run.status == "SUCCEEDED"

    def test_task_status_skip(self, db_session):
        run = OrchestrationRun(id="run-sk", trace_id="trace-sk", total_tasks=2)
        db_session.add(run)
        db_session.flush()

        t1 = OrchestrationTask(id="ot-sk-1", run_id=run.id, task_key="step1", task_type="t1", status=TaskOrchStatus.FAILED)
        t2 = OrchestrationTask(id="ot-sk-2", run_id=run.id, task_key="step2", task_type="t2",
                               depends_on_json='["step1"]', status=TaskOrchStatus.SKIPPED)
        db_session.add_all([t1, t2])
        db_session.commit()

        assert db_session.query(OrchestrationTask).filter(
            OrchestrationTask.run_id == run.id, OrchestrationTask.status == TaskOrchStatus.SKIPPED
        ).count() == 1


# =========================================================================
# 6. PlanTask → DAG 转换测试
# =========================================================================


class TestPlanToDAG:
    """PlanTask 列表到 DAG 的转换。"""

    def test_plan_to_dag(self):
        tasks = [
            PlanTask(task_key="A", task_type="t1"),
            PlanTask(task_key="B", task_type="t2", depends_on=["A"]),
            PlanTask(task_key="C", task_type="t3", depends_on=["A"]),
            PlanTask(task_key="D", task_type="t4", depends_on=["B", "C"]),
        ]
        dag = DAG()
        for t in tasks:
            dag.add_node(t.task_key, depends_on=t.depends_on)
        dag.is_valid()

        layers = dag.topological_layers()
        assert layers == [["A"], ["B", "C"], ["D"]]
        assert dag.max_parallelism() == 2
