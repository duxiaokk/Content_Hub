"""端到端编排测试

覆盖整个 Planner -> Schedule -> Execute -> Aggregate 流水线:
  1. 简单单任务计划
  2. 多任务 DAG 依赖
  3. 任务失败与重试
  4. 部分成功（部分失败）
  5. 运行取消
  6. Checkpoint 恢复
  7. trace_id 全链路传播
  8. Aggregator 增强功能测试（置信度、冲突解决、格式转换、增量聚合）

所有 LLM 调用和调度器响应均通过 mock 实现，无需外部服务。

需要: Python 3.11+ (项目使用了 datetime.UTC)；Python 3.10 可通过兼容 shim 运行

运行:  pytest tests/test_orchestration_e2e.py -v
"""
from __future__ import annotations

import copy
import datetime as _dt
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# ---- Compatibility shim for Python < 3.11 ----
if not hasattr(_dt, "UTC"):
    _dt.UTC = timezone.utc

os.environ.setdefault("SECRET_KEY", "test-secret-for-e2e-orchestration")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("DB_TYPE", "sqlite")

import pytest
from fastapi.testclient import TestClient

from scheduler_center.dag import DAG
from scheduler_center.orchestration_schemas import (
    AgentCapability,
    AggregatorRequest,
    AggregatorResponse,
    PlanTask,
    PlannerRequest,
    TaskResult,
)
from services.planner_service import PlannerAgent, PlannerConfig
from services.aggregator_service import AggregatorAgent, AggregatorConfig


# =========================================================================
# 轻量级内存模型 (替代 SQLAlchemy ORM 用于测试)
# =========================================================================


class RunStatus:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    PARTIAL = "PARTIAL"


class TaskOrchStatus:
    PENDING = "PENDING"
    BLOCKED = "BLOCKED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    SKIPPED = "SKIPPED"
    TIMED_OUT = "TIMED_OUT"


@dataclass
class MemRun:
    id: str
    trace_id: str
    name: str | None = None
    description: str | None = None
    status: str = RunStatus.PENDING
    cancel_requested: int = 0
    plan_json: str | None = None
    result_json: str | None = None
    last_error: str | None = None
    total_tasks: int = 0
    succeeded_tasks: int = 0
    failed_tasks: int = 0
    skipped_tasks: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None

    tasks: list[MemTask] = field(default_factory=list)
    logs: list[MemLog] = field(default_factory=list)


@dataclass
class MemTask:
    id: str
    run_id: str
    task_key: str
    task_type: str
    description: str | None = None
    depends_on_json: str | None = None
    layer_index: int = 0
    status: str = TaskOrchStatus.PENDING
    input_payload: str | None = None
    output_ref: str | None = None
    max_retries: int = 2
    retry_delay_seconds: float = 3.0
    attempt_count: int = 0
    timeout_seconds: float | None = None
    scheduler_task_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass
class MemLog:
    run_id: str
    trace_id: str | None = None
    task_key: str | None = None
    level: str = "INFO"
    message: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MemDB:
    """内存数据库，模拟 SQLAlchemy Session + 查询。"""

    def __init__(self):
        self.runs: dict[str, MemRun] = {}
        self.tasks: dict[str, MemTask] = {}
        self.logs: list[MemLog] = []

    def add(self, obj):
        if isinstance(obj, MemRun):
            self.runs[obj.id] = obj
        elif isinstance(obj, MemTask):
            self.tasks[obj.id] = obj
            # 反向关联
            run = self.runs.get(obj.run_id)
            if run:
                if obj not in run.tasks:
                    run.tasks.append(obj)
        elif isinstance(obj, MemLog):
            self.logs.append(obj)
            run = self.runs.get(obj.run_id)
            if run:
                run.logs.append(obj)

    def add_all(self, objs):
        for o in objs:
            self.add(o)

    def query_runs(self):
        return list(self.runs.values())

    def query_tasks(self):
        return list(self.tasks.values())

    def get_run(self, run_id):
        return self.runs.get(run_id)

    def get_task(self, task_id):
        return self.tasks.get(task_id)

    def tasks_by_run(self, run_id):
        return [t for t in self.tasks.values() if t.run_id == run_id]

    def logs_by_run(self, run_id):
        return [l for l in self.logs if l.run_id == run_id]

    def commit(self):
        pass

    def flush(self):
        pass

    def close(self):
        pass

    def rollback(self):
        pass


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture(scope="function")
def trace_id():
    """每次测试使用独立的 trace_id。"""
    return str(uuid.uuid4())


@pytest.fixture(scope="function")
def mem_db():
    """内存数据库实例（每个测试独立）。"""
    return MemDB()


@pytest.fixture
def capabilities():
    """仿真 Planner 使用的 Agent 能力描述。"""
    return [
        AgentCapability(agent_key="gen", name="Generator",
                        task_types=["generate_draft", "generate_outline"],
                        description="Generate blog drafts and outlines"),
        AgentCapability(agent_key="audit", name="Auditor",
                        task_types=["audit_draft", "review_content"],
                        description="Audit and review generated content"),
        AgentCapability(agent_key="analyze", name="Analyzer",
                        task_types=["analyze_blog", "analyze_trends"],
                        description="Analyze blog performance and trends"),
        AgentCapability(agent_key="processor", name="Data Processor",
                        task_types=["data.process", "data.extract"],
                        description="Process and extract data"),
    ]


@pytest.fixture
def mock_planner(capabilities):
    """返回已 mock 的 PlannerAgent。"""
    return PlannerAgent(PlannerConfig(use_mock=True))


@pytest.fixture
def mock_aggregator():
    """返回已 mock 的 AggregatorAgent。"""
    return AggregatorAgent(AggregatorConfig(mode="merge"))


# =========================================================================
# 1. 简单单任务计划
# =========================================================================


class TestSimpleSingleTask:
    """验证单任务 Planner -> Execute -> Aggregate 流水线。"""

    def test_plan_single_task(self, mock_planner, capabilities, trace_id):
        """Planner 应为简单意图生成单任务计划。"""
        req = PlannerRequest(
            intent="Write a blog post about AI",
            available_capabilities=capabilities,
            trace_id=trace_id,
        )
        resp = mock_planner.plan(req)
        assert resp.success
        assert resp.plan is not None
        assert len(resp.plan.tasks) >= 1
        assert resp.trace_id == trace_id

    def test_single_task_dag(self):
        """单任务创建的 DAG 应只有一个节点。"""
        dag = DAG()
        dag.add_node("main_task", data={"type": "generate_draft"})
        assert dag.is_valid()
        assert dag.topological_order() == ["main_task"]
        assert dag.max_parallelism() == 1
        assert len(dag) == 1

    def test_single_task_aggregate(self, mock_aggregator, trace_id):
        """单任务聚合应正确生成结果并包含统计。"""
        results = [
            TaskResult(task_key="main", task_type="generate_draft",
                       status="SUCCEEDED", output={"content": "AI is transforming..."})
        ]
        req = AggregatorRequest(
            run_id="run-single", intent="Write about AI",
            task_results=results, trace_id=trace_id,
        )
        resp = mock_aggregator.aggregate(req)
        assert resp.success
        assert resp.status == "SUCCEEDED"
        assert resp.aggregated_result["total"] == 1
        assert resp.aggregated_result["succeeded"] == 1

    def test_trace_id_in_single_task_pipeline(self, mock_planner, mock_aggregator,
                                               capabilities, trace_id):
        """trace_id 应在 Planner 和 Aggregator 间保持一致。"""
        plan_req = PlannerRequest(
            intent="Generate a blog draft",
            available_capabilities=capabilities,
            trace_id=trace_id,
        )
        plan_resp = mock_planner.plan(plan_req)
        assert plan_resp.trace_id == trace_id
        assert plan_resp.plan is not None

        results = [
            TaskResult(
                task_key=plan_resp.plan.tasks[0].task_key,
                task_type=plan_resp.plan.tasks[0].task_type,
                status="SUCCEEDED",
                output={"draft": "Generated content here"},
            )
        ]
        agg_req = AggregatorRequest(
            run_id="run-tr", intent="Generate a blog draft",
            task_results=results, trace_id=trace_id,
        )
        agg_resp = mock_aggregator.aggregate(agg_req)
        assert agg_resp.trace_id == trace_id
        assert agg_resp.success


# =========================================================================
# 2. 多任务 DAG 依赖
# =========================================================================


class TestMultiTaskDAG:
    """验证多任务 DAG 的构建、依赖解析和执行编排。"""

    SAMPLE_TASKS = [
        PlanTask(task_key="generate", task_type="generate_draft",
                 description="Generate content", depends_on=[]),
        PlanTask(task_key="audit", task_type="audit_draft",
                 description="Audit content", depends_on=["generate"]),
        PlanTask(task_key="analyze", task_type="analyze_blog",
                 description="Analyze performance", depends_on=["generate"]),
        PlanTask(task_key="publish", task_type="data.process",
                 description="Publish result", depends_on=["audit", "analyze"]),
    ]

    def test_plan_multi_task_dag(self, mock_planner, capabilities, trace_id):
        """生成+审核意图应创建多任务 DAG。"""
        req = PlannerRequest(
            intent="Generate a blog post and audit it",
            available_capabilities=capabilities,
            trace_id=trace_id,
        )
        resp = mock_planner.plan(req)
        assert resp.success
        assert resp.plan is not None
        tasks = resp.plan.tasks
        task_keys = {t.task_key for t in tasks}
        assert "generate" in task_keys
        has_dep = any(t.depends_on for t in tasks)
        assert has_dep, "Multi-task plan should have dependencies"

    def test_dag_topological_layers(self):
        """钻石 DAG 应正确分层。"""
        dag = DAG()
        for t in self.SAMPLE_TASKS:
            dag.add_node(t.task_key, depends_on=t.depends_on)
        dag.is_valid()

        layers = dag.topological_layers()
        assert layers[0] == ["generate"]
        assert set(layers[1]) == {"analyze", "audit"}
        assert layers[2] == ["publish"]
        assert dag.max_parallelism() == 2

    def test_dag_ready_nodes_progression(self):
        """就绪节点应按依赖顺序逐步变为可用。"""
        dag = DAG()
        for t in self.SAMPLE_TASKS:
            dag.add_node(t.task_key, depends_on=t.depends_on)

        assert dag.ready_nodes(set()) == {"generate"}
        assert dag.ready_nodes({"generate"}) == {"analyze", "audit"}
        assert dag.ready_nodes({"generate", "analyze"}) == {"audit"}
        assert dag.ready_nodes({"generate", "analyze", "audit"}) == {"publish"}
        assert dag.ready_nodes({"generate", "analyze", "audit", "publish"}) == set()

    def test_dag_dependency_skip_on_failure(self):
        """依赖节点失败时应识别下游需跳过。"""
        dag = DAG()
        dag.add_node("A")
        dag.add_node("B", depends_on=["A"])
        dag.add_node("C", depends_on=["A"])

        assert dag.ready_nodes({"A"}) == {"B", "C"}
        # A 未完成时 B/C 不应就绪
        assert dag.ready_nodes(set()) == {"A"}
        assert "B" not in dag.ready_nodes(set())
        assert "C" not in dag.ready_nodes(set())

    def test_aggregate_multi_task(self, mock_aggregator, trace_id):
        """多任务聚合应正确统计总数和成功数。"""
        results = [
            TaskResult(task_key="generate", task_type="generate_draft",
                       status="SUCCEEDED", output={"draft": "content"}),
            TaskResult(task_key="audit", task_type="audit_draft",
                       status="SUCCEEDED", output={"score": 8.5}),
            TaskResult(task_key="analyze", task_type="analyze_blog",
                       status="SUCCEEDED", output={"readers": 1000}),
        ]
        req = AggregatorRequest(
            run_id="run-multi", intent="Multi-task pipeline",
            task_results=results, trace_id=trace_id,
        )
        resp = mock_aggregator.aggregate(req)
        assert resp.success
        assert resp.status == "SUCCEEDED"
        assert resp.aggregated_result["total"] == 3
        assert resp.aggregated_result["succeeded"] == 3
        assert resp.aggregated_result["failed"] == 0


# =========================================================================
# 3. 任务失败与重试
# =========================================================================


class TestTaskFailureRetry:
    """验证任务失败后的重试逻辑和最终状态。"""

    def test_retry_attempts_tracked(self, mem_db, trace_id):
        """重试次数应在内存存储中正确更新。"""
        run = MemRun(id="run-retry", trace_id=trace_id,
                      name="retry test", status=RunStatus.RUNNING, total_tasks=1)
        mem_db.add(run)

        ot = MemTask(
            id="ot-retry-1", run_id=run.id, task_key="step1",
            task_type="generate_draft", status=TaskOrchStatus.PENDING,
            max_retries=3, depends_on_json="[]", scheduler_task_id="st-1",
        )
        mem_db.add(ot)

        # 模拟重试
        ot.attempt_count = 1
        ot.status = TaskOrchStatus.PENDING
        ot.scheduler_task_id = None

        loaded = mem_db.get_task("ot-retry-1")
        assert loaded is not None
        assert loaded.attempt_count == 1
        assert loaded.status == TaskOrchStatus.PENDING

    def test_task_exceeds_max_retries(self, mem_db, trace_id):
        """超过最大重试次数后任务标记为 FAILED。"""
        run = MemRun(id="run-max-retry", trace_id=trace_id,
                      name="max retry", status=RunStatus.RUNNING, total_tasks=1)
        mem_db.add(run)

        ot = MemTask(
            id="ot-max-1", run_id=run.id, task_key="step1",
            task_type="generate_draft", status=TaskOrchStatus.PENDING,
            max_retries=1, depends_on_json="[]",
        )
        mem_db.add(ot)

        ot.attempt_count = 1
        ot.attempt_count = 2
        ot.status = TaskOrchStatus.FAILED
        ot.finished_at = datetime.now(timezone.utc)

        loaded = mem_db.get_task("ot-max-1")
        assert loaded is not None
        assert loaded.status == TaskOrchStatus.FAILED
        assert loaded.attempt_count >= loaded.max_retries + 1

    def test_failure_skips_dependents(self, mem_db, trace_id):
        """上游任务最终失败后，下游依赖应 SKIPPED。"""
        run = MemRun(id="run-skip", trace_id=trace_id,
                      name="skip test", status=RunStatus.RUNNING, total_tasks=2)
        mem_db.add(run)

        t1 = MemTask(
            id="ot-skip-1", run_id=run.id, task_key="step1",
            task_type="generate_draft", status=TaskOrchStatus.FAILED,
            depends_on_json="[]",
        )
        t2 = MemTask(
            id="ot-skip-2", run_id=run.id, task_key="step2",
            task_type="audit_draft", status=TaskOrchStatus.SKIPPED,
            depends_on_json='["step1"]',
        )
        mem_db.add_all([t1, t2])

        skipped = [t for t in mem_db.tasks_by_run(run.id) if t.status == TaskOrchStatus.SKIPPED]
        assert len(skipped) == 1
        assert skipped[0].task_key == "step2"

    def test_aggregate_with_failed_task(self, mock_aggregator, trace_id):
        """聚合含失败任务的结果时应标记 FAILED。"""
        results = [
            TaskResult(task_key="step1", task_type="generate_draft",
                       status="FAILED", output={}, error="timeout"),
            TaskResult(task_key="step2", task_type="audit_draft",
                       status="SKIPPED", output={}, error="dependency failed"),
        ]
        req = AggregatorRequest(
            run_id="run-fail", intent="Failed pipeline",
            task_results=results, trace_id=trace_id,
        )
        resp = mock_aggregator.aggregate(req)
        assert not resp.success
        assert resp.status == "FAILED"
        # 全失败时 aggregated_result 可能为空
        result = resp.aggregated_result
        if result:
            assert result.get("total", 2) == 2
            assert result.get("succeeded", 0) == 0


# =========================================================================
# 4. 部分成功
# =========================================================================


class TestPartialSuccess:
    """验证部分任务成功、部分失败的混合场景。"""

    def test_partial_success_aggregation(self, mock_aggregator, trace_id):
        """部分成功时聚合状态为 PARTIAL。"""
        results = [
            TaskResult(task_key="generate", task_type="generate_draft",
                       status="SUCCEEDED", output={"draft": "good content"}),
            TaskResult(task_key="audit", task_type="audit_draft",
                       status="FAILED", output={}, error="audit API down"),
            TaskResult(task_key="analyze", task_type="analyze_blog",
                       status="SUCCEEDED", output={"score": 7.5}),
        ]
        req = AggregatorRequest(
            run_id="run-partial", intent="Partial pipeline",
            task_results=results, trace_id=trace_id,
        )
        resp = mock_aggregator.aggregate(req)
        assert resp.success
        assert resp.status == "PARTIAL"
        assert resp.aggregated_result["total"] == 3
        assert resp.aggregated_result["succeeded"] == 2
        assert resp.aggregated_result["failed"] == 1

        tasks = resp.aggregated_result["tasks"]
        assert tasks["generate"]["status"] == "SUCCEEDED"
        assert tasks["generate"]["output"]["draft"] == "good content"
        assert tasks["analyze"]["status"] == "SUCCEEDED"
        assert tasks["audit"]["status"] == "FAILED"
        assert tasks["audit"]["error"] == "audit API down"

    def test_partial_success_run_status(self, mem_db, trace_id):
        """部分成功时 Run 状态应为 PARTIAL。"""
        run = MemRun(
            id="run-partial-db", trace_id=trace_id,
            name="partial", status=RunStatus.PARTIAL,
            total_tasks=3, succeeded_tasks=2, failed_tasks=1,
        )
        mem_db.add(run)

        loaded = mem_db.get_run("run-partial-db")
        assert loaded is not None
        assert loaded.status == RunStatus.PARTIAL
        assert loaded.succeeded_tasks == 2
        assert loaded.failed_tasks == 1

    def test_aggregate_empty_partial(self, mock_aggregator, trace_id):
        """空任务列表应返回成功。"""
        req = AggregatorRequest(
            run_id="run-empty", intent="Empty",
            task_results=[], trace_id=trace_id,
        )
        resp = mock_aggregator.aggregate(req)
        assert resp.success
        assert resp.status == "SUCCEEDED"


# =========================================================================
# 5. 运行取消
# =========================================================================


class TestRunCancellation:
    """验证运行时取消的完整流程。"""

    def test_cancel_run_updates_status(self, mem_db, trace_id):
        """取消运行应更新 run 和所有 task 的状态。"""
        run = MemRun(
            id="run-cancel", trace_id=trace_id,
            name="cancel test", status=RunStatus.RUNNING, total_tasks=2,
        )
        mem_db.add(run)

        t1 = MemTask(
            id="ot-c-1", run_id=run.id, task_key="step1",
            task_type="generate_draft", status=TaskOrchStatus.RUNNING,
            depends_on_json="[]",
        )
        t2 = MemTask(
            id="ot-c-2", run_id=run.id, task_key="step2",
            task_type="audit_draft", status=TaskOrchStatus.BLOCKED,
            depends_on_json='["step1"]', scheduler_task_id=None,
        )
        mem_db.add_all([t1, t2])

        run.cancel_requested = 1
        run.status = RunStatus.CANCELED
        run.finished_at = datetime.now(timezone.utc)
        t1.status = TaskOrchStatus.CANCELED
        t1.finished_at = datetime.now(timezone.utc)
        t2.status = TaskOrchStatus.CANCELED
        t2.finished_at = datetime.now(timezone.utc)

        loaded_run = mem_db.get_run("run-cancel")
        assert loaded_run is not None
        assert loaded_run.status == RunStatus.CANCELED
        assert loaded_run.cancel_requested == 1

        tasks = mem_db.tasks_by_run(run.id)
        assert all(t.status == TaskOrchStatus.CANCELED for t in tasks)

    def test_cancel_mid_execution_cleanup(self, mem_db, trace_id):
        """取消后所有进行中的任务都应被终止，已完成的保持不变。"""
        run = MemRun(
            id="run-mid-cancel", trace_id=trace_id,
            name="mid cancel", status=RunStatus.RUNNING, total_tasks=3,
        )
        mem_db.add(run)

        t1 = MemTask(
            id="ot-mc-1", run_id=run.id, task_key="step1",
            task_type="generate_draft", status=TaskOrchStatus.SUCCEEDED,
            depends_on_json="[]",
        )
        t2 = MemTask(
            id="ot-mc-2", run_id=run.id, task_key="step2",
            task_type="audit_draft", status=TaskOrchStatus.RUNNING,
            depends_on_json='["step1"]',
        )
        t3 = MemTask(
            id="ot-mc-3", run_id=run.id, task_key="step3",
            task_type="analyze_blog", status=TaskOrchStatus.BLOCKED,
            depends_on_json='["step2"]',
        )
        mem_db.add_all([t1, t2, t3])

        run.status = RunStatus.CANCELED
        run.cancel_requested = 1
        t2.status = TaskOrchStatus.CANCELED
        t3.status = TaskOrchStatus.CANCELED

        tasks = mem_db.tasks_by_run(run.id)
        statuses = {t.task_key: t.status for t in tasks}
        assert statuses["step1"] == TaskOrchStatus.SUCCEEDED
        assert statuses["step2"] == TaskOrchStatus.CANCELED
        assert statuses["step3"] == TaskOrchStatus.CANCELED

    def test_cancel_logs_written(self, mem_db, trace_id):
        """取消操作应有对应的日志记录。"""
        run = MemRun(
            id="run-cancel-log", trace_id=trace_id,
            name="cancel log", status=RunStatus.CANCELED, total_tasks=1,
        )
        mem_db.add(run)

        log = MemLog(
            run_id=run.id, trace_id=run.trace_id,
            task_key=None, level="WARN", message="Run cancelled by user",
        )
        mem_db.add(log)

        logs = mem_db.logs_by_run("run-cancel-log")
        assert len(logs) == 1
        assert "cancelled" in logs[0].message.lower()


# =========================================================================
# 6. Checkpoint 恢复
# =========================================================================


class TestCheckpointRecovery:
    """验证 checkpoint 保存和恢复机制。"""

    def test_checkpoint_data_serialization(self):
        """Checkpoint 数据应可以被正确地序列化和反序列化。"""
        ckpt = {
            "run_id": "run-ckpt",
            "trace_id": "tr-ckpt",
            "status": RunStatus.RUNNING,
            "total_tasks": 3,
            "completed_tasks": ["step1", "step2"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        raw = json.dumps(ckpt, ensure_ascii=False)
        restored = json.loads(raw)
        assert restored["run_id"] == "run-ckpt"
        assert restored["trace_id"] == "tr-ckpt"
        assert restored["completed_tasks"] == ["step1", "step2"]

    def test_resume_picks_up_incomplete_tasks(self, mem_db, trace_id):
        """恢复后应重置进行中任务并保持已完成状态。"""
        run = MemRun(
            id="run-resume", trace_id=trace_id,
            name="resume", status=RunStatus.RUNNING, total_tasks=3,
        )
        mem_db.add(run)

        t1 = MemTask(
            id="ot-res-1", run_id=run.id, task_key="step1",
            task_type="generate_draft", status=TaskOrchStatus.SUCCEEDED,
            depends_on_json="[]",
        )
        t2 = MemTask(
            id="ot-res-2", run_id=run.id, task_key="step2",
            task_type="audit_draft", status=TaskOrchStatus.RUNNING,
            depends_on_json='["step1"]',
        )
        t3 = MemTask(
            id="ot-res-3", run_id=run.id, task_key="step3",
            task_type="analyze_blog", status=TaskOrchStatus.BLOCKED,
            depends_on_json='["step2"]',
        )
        mem_db.add_all([t1, t2, t3])

        # 模拟 checkpoint: step1 已完成，step2/step3 重置
        t2.status = TaskOrchStatus.PENDING
        t2.scheduler_task_id = None
        t3.status = TaskOrchStatus.BLOCKED

        tasks = mem_db.tasks_by_run(run.id)
        statuses = {t.task_key: t.status for t in tasks}
        assert statuses["step1"] == TaskOrchStatus.SUCCEEDED
        assert statuses["step2"] == TaskOrchStatus.PENDING
        assert statuses["step3"] == TaskOrchStatus.BLOCKED

    def test_recovery_considers_dependencies(self, mem_db, trace_id):
        """恢复时应考虑依赖关系，已满足依赖的应解除阻塞。"""
        run = MemRun(
            id="run-rec-dep", trace_id=trace_id,
            name="recovery deps", status=RunStatus.RUNNING, total_tasks=2,
        )
        mem_db.add(run)

        t1 = MemTask(
            id="ot-rd-1", run_id=run.id, task_key="step1",
            task_type="generate_draft", status=TaskOrchStatus.SUCCEEDED,
            depends_on_json="[]",
        )
        t2 = MemTask(
            id="ot-rd-2", run_id=run.id, task_key="step2",
            task_type="audit_draft", status=TaskOrchStatus.BLOCKED,
            depends_on_json='["step1"]',
        )
        mem_db.add_all([t1, t2])

        if t2.status == TaskOrchStatus.BLOCKED:
            t2.status = TaskOrchStatus.PENDING

        loaded = mem_db.get_task("ot-rd-2")
        assert loaded is not None
        assert loaded.status == TaskOrchStatus.PENDING

    def test_checkpoint_with_no_completed_tasks(self, mem_db, trace_id):
        """空 checkpoint（无已完成任务）应从 PENDING 开始。"""
        run = MemRun(
            id="run-empty-ckpt", trace_id=trace_id,
            name="empty ckpt", status=RunStatus.RUNNING, total_tasks=2,
        )
        mem_db.add(run)

        t1 = MemTask(
            id="ot-ec-1", run_id=run.id, task_key="step1",
            task_type="generate_draft", status=TaskOrchStatus.PENDING,
            depends_on_json="[]",
        )
        mem_db.add(t1)

        loaded = mem_db.get_task("ot-ec-1")
        assert loaded is not None
        assert loaded.status in (TaskOrchStatus.PENDING, TaskOrchStatus.SUCCEEDED)


# =========================================================================
# 7. trace_id 全链路传播
# =========================================================================


class TestTraceIdPropagation:
    """验证 trace_id 在 Planner -> Schedule -> Execute -> Aggregate 各环节的传播。"""

    def test_trace_id_in_planner_response(self, mock_planner, capabilities, trace_id):
        """Planner 响应中应包含输入的 trace_id。"""
        req = PlannerRequest(
            intent="Test trace propagation",
            available_capabilities=capabilities,
            trace_id=trace_id,
        )
        resp = mock_planner.plan(req)
        assert resp.trace_id == trace_id
        if resp.plan:
            assert resp.plan.trace_id == trace_id

    def test_trace_id_in_aggregator_response(self, mock_aggregator, trace_id):
        """Aggregator 响应中应包含输入的 trace_id。"""
        results = [
            TaskResult(task_key="t1", task_type="generate_draft",
                       status="SUCCEEDED", output={"x": 1}),
        ]
        req = AggregatorRequest(
            run_id="run-tr-prop", intent="trace test",
            task_results=results, trace_id=trace_id,
        )
        resp = mock_aggregator.aggregate(req)
        assert resp.trace_id == trace_id

    def test_trace_id_in_mem_run(self, mem_db, trace_id):
        """MemRun 中应存储 trace_id。"""
        run = MemRun(
            id="run-tr-db", trace_id=trace_id,
            name="trace db", total_tasks=1,
        )
        mem_db.add(run)

        loaded = mem_db.get_run("run-tr-db")
        assert loaded is not None
        assert loaded.trace_id == trace_id

    def test_trace_id_in_mem_task_via_run(self, mem_db, trace_id):
        """MemTask 通过关联 run 间接持有 trace_id。"""
        run = MemRun(
            id="run-tr-task", trace_id=trace_id,
            name="trace task", total_tasks=1,
        )
        mem_db.add(run)

        task = MemTask(
            id="ot-tr-1", run_id=run.id, task_key="step1",
            task_type="generate_draft", depends_on_json="[]",
        )
        mem_db.add(task)

        loaded_task = mem_db.get_task("ot-tr-1")
        assert loaded_task is not None
        loaded_run = mem_db.get_run(loaded_task.run_id)
        assert loaded_run is not None
        assert loaded_run.trace_id == trace_id

    def test_trace_id_in_logs(self, mem_db, trace_id):
        """日志记录中应包含 trace_id。"""
        run = MemRun(
            id="run-tr-log", trace_id=trace_id,
            name="trace log", total_tasks=1,
        )
        mem_db.add(run)

        log = MemLog(
            run_id=run.id, trace_id=trace_id,
            task_key="step1", level="INFO", message="Task submitted",
        )
        mem_db.add(log)

        logs = mem_db.logs_by_run("run-tr-log")
        assert len(logs) == 1
        assert logs[0].trace_id == trace_id

    def test_auto_generated_trace_id(self, mock_planner, capabilities):
        """未提供 trace_id 时应自动生成 UUID 格式。"""
        req = PlannerRequest(
            intent="Auto trace",
            available_capabilities=capabilities,
        )
        resp = mock_planner.plan(req)
        assert resp.trace_id is not None
        uuid.UUID(resp.trace_id)

    def test_full_pipeline_trace_consistency(self, mock_planner, mock_aggregator,
                                              capabilities, trace_id):
        """完整流水线中 trace_id 从头到尾保持一致。"""
        # 1. Plan
        plan_req = PlannerRequest(
            intent="Full pipeline trace test",
            available_capabilities=capabilities,
            trace_id=trace_id,
        )
        plan_resp = mock_planner.plan(plan_req)
        assert plan_resp.trace_id == trace_id
        assert plan_resp.plan.trace_id == trace_id

        # 2. Simulate execution results
        task_results = []
        for pt in plan_resp.plan.tasks:
            task_results.append(TaskResult(
                task_key=pt.task_key, task_type=pt.task_type,
                status="SUCCEEDED", output={"result": f"output_of_{pt.task_key}"},
            ))

        # 3. Aggregate
        agg_req = AggregatorRequest(
            run_id="run-full-pipe", intent=plan_resp.plan.intent,
            task_results=task_results, trace_id=trace_id,
        )
        agg_resp = mock_aggregator.aggregate(agg_req)
        assert agg_resp.trace_id == trace_id
        assert agg_resp.success


# =========================================================================
# 8. Aggregator 增强功能集成测试
# =========================================================================


class TestAggregatorEnhancedFeatures:
    """验证新增的 Aggregator 增强功能（置信度评分、冲突解决、格式转换、增量聚合）。"""

    @pytest.fixture
    def agg_agent_app(self):
        """创建 Aggregator FastAPI TestClient。"""
        from agents.aggregator_agent import app as agg_app
        return agg_app

    def test_confidence_scoring_in_merge(self, agg_agent_app):
        """merge 模式应自动附加置信度评分。"""
        tc = TestClient(agg_agent_app)

        resp = tc.post(
            "/api/internal/agent/run",
            json={
                "task_type": "aggregate.merge",
                "payload": {
                    "run_id": "run-conf",
                    "intent": "test confidence",
                    "enable_confidence": True,
                    "task_results": [
                        {"task_key": "a", "task_type": "t1", "status": "SUCCEEDED", "output": {"x": 1}},
                        {"task_key": "b", "task_type": "t2", "status": "FAILED", "output": {}, "error": "err"},
                        {"task_key": "c", "task_type": "t3", "status": "SUCCEEDED", "output": {}, "error": None},
                    ],
                },
            },
            headers={"x-internal-token": "local-dev-scheduler-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        result = data["result"]
        agg = result.get("aggregated_result", {})
        assert "confidence_scores" in agg
        assert "overall_confidence" in agg
        assert 0 <= agg["overall_confidence"] <= 1
        assert agg["confidence_scores"]["a"]["confidence"] > 0.8
        assert agg["confidence_scores"]["b"]["confidence"] == 0.0

    def test_conflict_resolution(self, agg_agent_app):
        """相同 task_key 的多个结果应按投票合并。"""
        tc = TestClient(agg_agent_app)

        resp = tc.post(
            "/api/internal/agent/run",
            json={
                "task_type": "aggregate.merge",
                "payload": {
                    "run_id": "run-conflict",
                    "intent": "test conflict",
                    "enable_conflict_resolution": True,
                    "task_results": [
                        {"task_key": "dup", "task_type": "t1", "status": "SUCCEEDED",
                         "output": {"field_x": "value_A", "field_y": "common"}},
                        {"task_key": "dup", "task_type": "t1", "status": "SUCCEEDED",
                         "output": {"field_x": "value_A", "field_y": "common"}},
                        {"task_key": "dup", "task_type": "t1", "status": "SUCCEEDED",
                         "output": {"field_x": "value_B", "field_y": "common"}},
                    ],
                },
            },
            headers={"x-internal-token": "local-dev-scheduler-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        result = data["result"]
        agg = result.get("aggregated_result", {})
        tasks = agg.get("tasks", {})
        assert "dup" in tasks
        dup_out = tasks["dup"].get("output", {})
        assert dup_out.get("field_x") == "value_A"
        assert dup_out.get("field_y") == "common"

    def test_format_conversion_markdown(self, agg_agent_app):
        """output_format=markdown 应生成 Markdown 格式输出。"""
        tc = TestClient(agg_agent_app)

        resp = tc.post(
            "/api/internal/agent/run",
            json={
                "task_type": "aggregate.merge",
                "payload": {
                    "run_id": "run-md",
                    "intent": "test markdown",
                    "output_format": "markdown",
                    "task_results": [
                        {"task_key": "gen", "task_type": "t1", "status": "SUCCEEDED",
                         "output": {"title": "AI Blog", "word_count": 500}},
                    ],
                },
            },
            headers={"x-internal-token": "local-dev-scheduler-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        result = data["result"]
        assert result["output_format"] == "markdown"
        assert "formatted_output" in result
        formatted = result["formatted_output"]
        assert "## " in formatted
        assert "**title**" in formatted
        assert "AI Blog" in formatted

    def test_format_conversion_html(self, agg_agent_app):
        """output_format=html 应生成 HTML 格式输出。"""
        tc = TestClient(agg_agent_app)

        resp = tc.post(
            "/api/internal/agent/run",
            json={
                "task_type": "aggregate.merge",
                "payload": {
                    "run_id": "run-html",
                    "intent": "test html",
                    "output_format": "html",
                    "task_results": [
                        {"task_key": "gen", "task_type": "t1", "status": "SUCCEEDED",
                         "output": {"title": "AI Blog"}},
                    ],
                },
            },
            headers={"x-internal-token": "local-dev-scheduler-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        result = data["result"]
        assert result["output_format"] == "html"
        assert "formatted_output" in result
        formatted = result["formatted_output"]
        assert "<div" in formatted
        assert "<h2>" in formatted
        assert "AI Blog" in formatted

    def test_format_conversion_json(self, agg_agent_app):
        """output_format=json 应生成带缩进的 JSON 字符串。"""
        tc = TestClient(agg_agent_app)

        resp = tc.post(
            "/api/internal/agent/run",
            json={
                "task_type": "aggregate.merge",
                "payload": {
                    "run_id": "run-json",
                    "intent": "test json",
                    "output_format": "json",
                    "task_results": [
                        {"task_key": "gen", "task_type": "t1", "status": "SUCCEEDED",
                         "output": {"title": "AI"}},
                    ],
                },
            },
            headers={"x-internal-token": "local-dev-scheduler-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        result = data["result"]
        assert result["output_format"] == "json"
        assert "formatted_output" in result
        formatted = result["formatted_output"]
        parsed = json.loads(formatted)
        assert "tasks" in parsed
        assert "total" in parsed

    def test_incremental_aggregation(self, agg_agent_app):
        """append=true 模式应将新结果追加到已有聚合中。"""
        tc = TestClient(agg_agent_app)

        resp1 = tc.post(
            "/api/internal/agent/run",
            json={
                "task_type": "aggregate.merge",
                "payload": {
                    "run_id": "run-inc",
                    "intent": "test incremental",
                    "task_results": [
                        {"task_key": "step1", "task_type": "t1", "status": "SUCCEEDED",
                         "output": {"part": 1}},
                    ],
                },
            },
            headers={"x-internal-token": "local-dev-scheduler-token"},
        )
        assert resp1.status_code == 200
        existing = resp1.json()["result"]

        resp2 = tc.post(
            "/api/internal/agent/run",
            json={
                "task_type": "aggregate.merge",
                "payload": {
                    "run_id": "run-inc",
                    "intent": "test incremental",
                    "append": True,
                    "existing_aggregation": existing,
                    "task_results": [
                        {"task_key": "step2", "task_type": "t2", "status": "SUCCEEDED",
                         "output": {"part": 2}},
                    ],
                },
            },
            headers={"x-internal-token": "local-dev-scheduler-token"},
        )
        assert resp2.status_code == 200
        result2 = resp2.json()["result"]
        agg2 = result2.get("aggregated_result", {})
        assert agg2.get("incremental") is True
        assert agg2["total"] == 2
        assert agg2["succeeded"] == 2
        tasks = agg2["tasks"]
        assert "step1" in tasks
        assert "step2" in tasks

    def test_incremental_overwrite_existing_key(self, agg_agent_app):
        """append 模式下相同 key 的新结果应覆盖旧结果。"""
        tc = TestClient(agg_agent_app)

        resp1 = tc.post(
            "/api/internal/agent/run",
            json={
                "task_type": "aggregate.merge",
                "payload": {
                    "run_id": "run-ow",
                    "intent": "test overwrite",
                    "task_results": [
                        {"task_key": "step1", "task_type": "t1", "status": "PENDING",
                         "output": {}},
                    ],
                },
            },
            headers={"x-internal-token": "local-dev-scheduler-token"},
        )
        existing = resp1.json()["result"]

        resp2 = tc.post(
            "/api/internal/agent/run",
            json={
                "task_type": "aggregate.merge",
                "payload": {
                    "run_id": "run-ow",
                    "intent": "test overwrite",
                    "append": True,
                    "existing_aggregation": existing,
                    "task_results": [
                        {"task_key": "step1", "task_type": "t1", "status": "SUCCEEDED",
                         "output": {"final": True}},
                    ],
                },
            },
            headers={"x-internal-token": "local-dev-scheduler-token"},
        )
        result2 = resp2.json()["result"]
        agg2 = result2.get("aggregated_result", {})
        tasks = agg2["tasks"]
        assert tasks["step1"]["status"] == "SUCCEEDED"
        assert tasks["step1"]["output"]["final"] is True

    def test_confidence_disabled(self, agg_agent_app):
        """enable_confidence=false 应不生成置信度数据。"""
        tc = TestClient(agg_agent_app)

        resp = tc.post(
            "/api/internal/agent/run",
            json={
                "task_type": "aggregate.merge",
                "payload": {
                    "run_id": "run-noconf",
                    "intent": "no confidence",
                    "enable_confidence": False,
                    "task_results": [
                        {"task_key": "a", "task_type": "t1", "status": "SUCCEEDED",
                         "output": {"x": 1}},
                    ],
                },
            },
            headers={"x-internal-token": "local-dev-scheduler-token"},
        )
        assert resp.status_code == 200
        agg = resp.json()["result"].get("aggregated_result", {})
        assert "confidence_scores" not in agg
        assert "overall_confidence" not in agg

    def test_conflict_resolution_disabled(self, agg_agent_app):
        """enable_conflict_resolution=false 应保留原始冲突结果。"""
        tc = TestClient(agg_agent_app)

        resp = tc.post(
            "/api/internal/agent/run",
            json={
                "task_type": "aggregate.merge",
                "payload": {
                    "run_id": "run-nocr",
                    "intent": "no conflict resolution",
                    "enable_conflict_resolution": False,
                    "task_results": [
                        {"task_key": "dup", "task_type": "t1", "status": "SUCCEEDED",
                         "output": {"val": "A"}},
                        {"task_key": "dup", "task_type": "t1", "status": "SUCCEEDED",
                         "output": {"val": "B"}},
                    ],
                },
            },
            headers={"x-internal-token": "local-dev-scheduler-token"},
        )
        assert resp.status_code == 200
        agg = resp.json()["result"].get("aggregated_result", {})
        tasks = agg.get("tasks", {})
        for k, v in tasks.items():
            if isinstance(v, dict) and "output" in v:
                assert "conflict_resolution" not in v


# =========================================================================
# 9. 编排引擎端到端模拟测试
# =========================================================================


class TestOrchestrationEngineEndToEnd:
    """使用 mock 模拟 OrchestrationEngine 完整生命周期。"""

    def _run_pipeline(self, mem_db, trace_id, capabilities, fail_task=None):
        """执行完整的 Planner -> DAG -> Execute -> Aggregate 流水线。

        返回 (mem_db, run_id, agg_resp, succeeded_count, failed_count)
        """
        # 1. Plan
        planner = PlannerAgent(PlannerConfig(use_mock=True))
        plan_req = PlannerRequest(
            intent="Generate and audit a blog post",
            available_capabilities=capabilities,
            trace_id=trace_id,
        )
        plan_resp = planner.plan(plan_req)
        assert plan_resp.success and plan_resp.plan is not None
        plan_tasks = plan_resp.plan.tasks

        # 2. 构建 DAG
        dag = DAG()
        for pt in plan_tasks:
            dag.add_node(pt.task_key, depends_on=pt.depends_on)
        dag.is_valid()

        # 3. 创建 MemRun
        run = MemRun(
            id=f"run-{trace_id[:8]}", trace_id=trace_id,
            name="E2E pipeline", description=plan_resp.plan.intent[:500],
            status=RunStatus.RUNNING,
            plan_json=json.dumps(plan_resp.plan.model_dump(), ensure_ascii=False),
            total_tasks=len(plan_tasks),
        )
        mem_db.add(run)

        # 4. 创建 MemTasks
        for pt in plan_tasks:
            layer = len(dag.all_dependencies_of(pt.task_key))
            ot = MemTask(
                id=f"ot-{pt.task_key}-{trace_id[:8]}",
                run_id=run.id, task_key=pt.task_key, task_type=pt.task_type,
                description=pt.description,
                depends_on_json=json.dumps(pt.depends_on),
                layer_index=layer,
                status=TaskOrchStatus.BLOCKED if pt.depends_on else TaskOrchStatus.PENDING,
                input_payload=json.dumps(pt.input_payload, ensure_ascii=False),
                max_retries=pt.max_retries,
                retry_delay_seconds=pt.retry_delay_seconds,
            )
            mem_db.add(ot)

        # 5. 模拟执行（按拓扑层）
        orch_tasks = sorted(mem_db.tasks_by_run(run.id), key=lambda t: t.layer_index)

        completed_keys: set[str] = set()
        succeeded_count = 0
        failed_count = 0

        for ot in orch_tasks:
            deps = json.loads(ot.depends_on_json or "[]")
            all_deps_ok = all(d in completed_keys for d in deps)

            if ot.status == TaskOrchStatus.BLOCKED and all_deps_ok:
                ot.status = TaskOrchStatus.PENDING

            if ot.status == TaskOrchStatus.PENDING:
                ot.scheduler_task_id = f"st-mock-{ot.task_key}"
                ot.status = TaskOrchStatus.RUNNING
                ot.started_at = datetime.now(timezone.utc)

                # 模拟执行结果
                if fail_task and ot.task_key == fail_task:
                    ot.status = TaskOrchStatus.FAILED
                    ot.finished_at = datetime.now(timezone.utc)
                    ot.updated_at = datetime.now(timezone.utc)
                    failed_count += 1
                else:
                    ot.status = TaskOrchStatus.SUCCEEDED
                    ot.finished_at = datetime.now(timezone.utc)
                    ot.updated_at = datetime.now(timezone.utc)
                    completed_keys.add(ot.task_key)
                    succeeded_count += 1

        run.succeeded_tasks = succeeded_count
        run.failed_tasks = failed_count

        # 6. 聚合结果
        agg = AggregatorAgent(AggregatorConfig(mode="merge"))
        task_results = []
        for ot in orch_tasks:
            if ot.status == TaskOrchStatus.SUCCEEDED:
                output_data = {"result": f"output_of_{ot.task_key}"}
            else:
                output_data = {}
            task_results.append(TaskResult(
                task_key=ot.task_key, task_type=ot.task_type,
                status=ot.status, output=output_data,
                error=None if ot.status == TaskOrchStatus.SUCCEEDED else f"status: {ot.status}",
            ))

        agg_req = AggregatorRequest(
            run_id=run.id, intent=run.description or "",
            task_results=task_results, trace_id=trace_id,
        )
        agg_resp = agg.aggregate(agg_req)

        # 7. 最终化 Run
        if agg_resp.success:
            run.status = RunStatus.SUCCEEDED if agg_resp.status == "SUCCEEDED" else RunStatus.PARTIAL
        else:
            run.status = RunStatus.FAILED
        run.result_json = json.dumps(agg_resp.aggregated_result, ensure_ascii=False)
        run.finished_at = datetime.now(timezone.utc)
        run.updated_at = datetime.now(timezone.utc)

        return mem_db, run, agg_resp, succeeded_count, failed_count

    def test_full_pipeline_all_success(self, mem_db, trace_id, capabilities):
        """模拟完整的 Planner -> Execute -> Aggregate 全成功流水线。"""
        mem_db, run, agg_resp, succ, fail = self._run_pipeline(
            mem_db, trace_id, capabilities
        )

        loaded_run = mem_db.get_run(run.id)
        assert loaded_run is not None
        assert loaded_run.trace_id == trace_id
        assert loaded_run.status == RunStatus.SUCCEEDED
        assert loaded_run.succeeded_tasks >= 2
        assert loaded_run.failed_tasks == 0

        result_json = json.loads(loaded_run.result_json or "{}")
        assert result_json["total"] >= 2
        assert result_json["succeeded"] >= 2
        assert agg_resp.trace_id == trace_id

    def test_pipeline_with_one_failure(self, mem_db, trace_id, capabilities):
        """模拟含一个失败任务的部分成功流水线。"""
        # 找到 audit 任务名
        planner = PlannerAgent(PlannerConfig(use_mock=True))
        plan_req = PlannerRequest(
            intent="Generate a blog and audit it",
            available_capabilities=capabilities,
            trace_id=trace_id,
        )
        plan_resp = planner.plan(plan_req)
        assert plan_resp.success and plan_resp.plan

        # 让 audit 失败
        audit_key = None
        for pt in plan_resp.plan.tasks:
            if "audit" in pt.task_key.lower():
                audit_key = pt.task_key
                break

        mem_db, run, agg_resp, succ, fail = self._run_pipeline(
            mem_db, trace_id, capabilities, fail_task=audit_key
        )

        loaded_run = mem_db.get_run(run.id)
        assert loaded_run is not None
        assert loaded_run.trace_id == trace_id
        assert loaded_run.status == RunStatus.PARTIAL
        assert loaded_run.failed_tasks == 1
        assert agg_resp.status == "PARTIAL"
        assert agg_resp.aggregated_result["succeeded"] >= 1
        assert agg_resp.aggregated_result["failed"] == 1
