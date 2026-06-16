"""编排调度引擎

将 OrchestrationRun 拆解为独立 SchedulerTask，提交到调度中心，
监控依赖关系，在依赖满足时推进任务执行。
"""
from __future__ import annotations

# Compatibility layer only.
# Frozen during Agent control plane migration.

import json
import logging
import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from core.mempool import get_pool as get_memory_pool
from core.memory_naming import RunNaming, TaskNaming
from scheduler_center.dag import DAG
from scheduler_center.database import SessionLocal
from scheduler_center.dispatcher import TaskStatus
from scheduler_center.models import SchedulerTask
from scheduler_center.orchestration_models import (
    OrchestrationRun,
    OrchestrationRunLog,
    OrchestrationTask,
    RunStatus,
    TaskOrchStatus,
)
from scheduler_center.orchestration_schemas import (
    AggregatorRequest,
    ExecutionPlan,
    PlannerRequest,
    PlannerResponse,
    TaskResult,
)
from scheduler_client import SchedulerClient, get_scheduler_client
from services.aggregator_service import AggregatorAgent, AggregatorConfig
from services.planner_service import PlannerAgent, PlannerConfig

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _loads_json(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return raw


class OrchestrationEngine:
    """编排引擎 — 驱动一次 OrchestrationRun 的完整生命周期。"""

    def __init__(
        self,
        scheduler_client: SchedulerClient | None = None,
        planner: PlannerAgent | None = None,
        aggregator: AggregatorAgent | None = None,
    ) -> None:
        self._scheduler_client = scheduler_client or get_scheduler_client()
        self._planner = planner or PlannerAgent()
        self._aggregator = aggregator or AggregatorAgent()
        self._stop_events: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}

    # ------------------------------------------------------------------
    # 创建 Run
    # ------------------------------------------------------------------

    def create_and_start_run(
        self,
        *,
        intent: str,
        name: str | None = None,
        context: dict[str, Any] | None = None,
        constraints: dict[str, Any] | None = None,
        trace_id: str | None = None,
        run_id: str | None = None,
    ) -> OrchestrationRun:
        """创建并启动一个编排运行。"""
        run_id = run_id or str(uuid.uuid4())
        trace_id = trace_id or str(uuid.uuid4())
        db = SessionLocal()

        try:
            # 1. Plan
            plan = self._plan(intent, context or {}, constraints or {}, trace_id)
            if not plan or not plan.tasks:
                raise ValueError("Planner returned empty plan")

            # 2. 创建 Run + Tasks
            run = OrchestrationRun(
                id=run_id,
                trace_id=trace_id,
                name=name,
                description=intent[:500],
                status=RunStatus.RUNNING,
                plan_json=json.dumps(plan.model_dump(), ensure_ascii=False),
                total_tasks=len(plan.tasks),
            )
            db.add(run)
            self._append_log(db, run_id, trace_id, "INFO", f"Run created with {len(plan.tasks)} tasks")

            # 3. 构建 DAG + 创建 OrchestrationTask
            dag = self._build_dag(plan)
            for pt in plan.tasks:
                layer = len(dag.all_dependencies_of(pt.task_key))
                orch_task = OrchestrationTask(
                    run_id=run_id,
                    task_key=pt.task_key,
                    task_type=pt.task_type,
                    description=pt.description,
                    depends_on_json=json.dumps(pt.depends_on),
                    layer_index=layer,
                    status=TaskOrchStatus.BLOCKED if pt.depends_on else TaskOrchStatus.PENDING,
                    input_payload=json.dumps(pt.input_payload, ensure_ascii=False),
                    max_retries=pt.max_retries,
                    retry_delay_seconds=pt.retry_delay_seconds,
                    timeout_seconds=pt.timeout_seconds,
                )
                db.add(orch_task)
            db.commit()

            # 4. 写入 Shared Memory
            pool = get_memory_pool()
            pool.set(RunNaming.status(run_id), {"status": RunStatus.RUNNING, "trace_id": trace_id})
            pool.set(RunNaming.plan(run_id), plan.model_dump(), persist=True)

            # 5. 保存 checkpoint
            pool.set(RunNaming.checkpoint(run_id), {
                "run_id": run_id,
                "trace_id": trace_id,
                "status": RunStatus.RUNNING,
                "total_tasks": len(plan.tasks),
                "completed_tasks": [],
                "updated_at": _utcnow().isoformat(),
            }, persist=True)

            # 6. 启动 DAG 监控线程
            self._start_monitor(run_id, trace_id)

            db.refresh(run)
            return run
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # ------------------------------------------------------------------
    # 规划
    # ------------------------------------------------------------------

    def _plan(self, intent: str, context: dict, constraints: dict, trace_id: str) -> ExecutionPlan | None:
        """调用 Planner 生成执行计划。"""
        db = SessionLocal()
        try:
            from scheduler_center.models import SchedulerAgent
            agents = db.query(SchedulerAgent).filter(SchedulerAgent.status == 1).all()

            capabilities = []
            for a in agents:
                task_types = json.loads(a.task_types_json or "[]")
                capabilities.append({
                    "agent_key": a.agent_key,
                    "name": a.name,
                    "task_types": task_types,
                    "description": f"{a.name}: {', '.join(task_types)}",
                })
        finally:
            db.close()

        request = PlannerRequest(
            intent=intent,
            context=context,
            available_capabilities=[c for c in capabilities],
            constraints=constraints,
            trace_id=trace_id,
        )
        response = self._planner.plan(request)
        if not response.success or not response.plan:
            raise ValueError(f"Planning failed: {response.error}")
        return response.plan

    # ------------------------------------------------------------------
    # DAG 构建
    # ------------------------------------------------------------------

    def _build_dag(self, plan: ExecutionPlan) -> DAG:
        dag = DAG()
        for pt in plan.tasks:
            dag.add_node(pt.task_key, depends_on=pt.depends_on)
        dag.is_valid()
        return dag

    # ------------------------------------------------------------------
    # 监控线程
    # ------------------------------------------------------------------

    def _start_monitor(self, run_id: str, trace_id: str) -> None:
        stop = threading.Event()
        self._stop_events[run_id] = stop
        t = threading.Thread(target=self._monitor_loop, args=(run_id, trace_id, stop), daemon=True)
        self._threads[run_id] = t
        t.start()

    def _monitor_loop(self, run_id: str, trace_id: str, stop: threading.Event) -> None:
        """监控循环：推进任务 → 等待完成 → 聚合结果。"""
        db = SessionLocal()
        try:
            while not stop.is_set():
                run = db.query(OrchestrationRun).filter(OrchestrationRun.id == run_id).first()
                if not run:
                    break
                if run.status in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELED):
                    break
                if run.cancel_requested:
                    self._cancel_run(db, run)
                    break

                # 推进就绪任务
                self._advance_tasks(db, run, trace_id)

                # 检查是否全部完成
                if self._check_completion(db, run):
                    break

                time.sleep(1.0)
        finally:
            db.close()

    def _advance_tasks(self, db: Session, run: OrchestrationRun, trace_id: str) -> None:
        """把 BLOCKED→PENDING（依赖满足）和 PENDING→提交执行。"""
        orch_tasks = (
            db.query(OrchestrationTask)
            .filter(OrchestrationTask.run_id == run.id)
            .all()
        )

        # 构建 DAG 用于依赖判断
        dag = self._build_dag_from_db(orch_tasks)
        completed = {t.task_key for t in orch_tasks if t.status == TaskOrchStatus.SUCCEEDED}
        ready_keys = dag.ready_nodes(completed)

        for ot in orch_tasks:
            # 1. BLOCKED → PENDING（依赖满足）
            if ot.status == TaskOrchStatus.BLOCKED and ot.task_key in ready_keys:
                ot.status = TaskOrchStatus.PENDING
                ot.updated_at = _utcnow()
                self._append_log(db, run.id, trace_id, "INFO", f"Task {ot.task_key} unblocked")
                pool = get_memory_pool()
                pool.set(TaskNaming.status(ot.task_key, run.id), {"status": "PENDING"})

            # 2. PENDING → 提交调度中心
            if ot.status == TaskOrchStatus.PENDING and not ot.scheduler_task_id:
                self._submit_to_scheduler(db, ot, run, trace_id)

            # 3. 有 scheduler_task_id 的 → 检查完成状态
            if ot.scheduler_task_id and ot.status in (TaskOrchStatus.PENDING, TaskOrchStatus.RUNNING):
                self._check_scheduler_status(db, ot, run, trace_id)

        db.commit()

    def _submit_to_scheduler(self, db: Session, ot: OrchestrationTask, run: OrchestrationRun, trace_id: str) -> None:
        """将编排任务提交到调度中心。"""
        payload = _loads_json(ot.input_payload) or {}
        # 注入依赖任务的输出（从 Shared Memory 读取）
        deps = _loads_json(ot.depends_on_json) or []
        pool = get_memory_pool()
        for dep_key in deps:
            dep_output = pool.get(TaskNaming.output(dep_key, run.id), default={})
            if dep_output:
                payload[f"_dep_{dep_key}_output"] = dep_output

        try:
            result = self._scheduler_client.submit_task(
                task_type=ot.task_type,
                payload=payload,
                trace_id=trace_id,
                max_retries=ot.max_retries,
                retry_delay_seconds=ot.retry_delay_seconds,
            )
            ot.scheduler_task_id = result["id"]
            ot.status = TaskOrchStatus.RUNNING
            ot.started_at = _utcnow()
            ot.updated_at = _utcnow()
            self._append_log(db, run.id, trace_id, "INFO", f"Task {ot.task_key} submitted: {ot.scheduler_task_id[:8]}")
        except Exception as e:
            self._append_log(db, run.id, trace_id, "ERROR", f"Failed to submit {ot.task_key}: {e}")
            self._handle_task_failure(db, ot, run, str(e))

    def _check_scheduler_status(self, db: Session, ot: OrchestrationTask, run: OrchestrationRun, trace_id: str) -> None:
        """检查提交到调度中心的任务状态。"""
        task = db.query(SchedulerTask).filter(SchedulerTask.id == ot.scheduler_task_id).first()
        if not task:
            return

        if task.status == TaskStatus.SUCCEEDED:
            # 写入输出到 Shared Memory
            result = _loads_json(task.result_json) or {}
            pool = get_memory_pool()
            pool.set(TaskNaming.output(ot.task_key, run.id), result, persist=True)
            pool.set(TaskNaming.status(ot.task_key, run.id), {"status": "SUCCEEDED"})

            ot.status = TaskOrchStatus.SUCCEEDED
            ot.finished_at = _utcnow()
            ot.updated_at = _utcnow()
            run.succeeded_tasks = (run.succeeded_tasks or 0) + 1
            self._append_log(db, run.id, trace_id, "INFO", f"Task {ot.task_key} SUCCEEDED")

            # 更新 checkpoint
            self._update_checkpoint(run.id, ot.task_key)

        elif task.status == TaskStatus.FAILED:
            self._handle_task_failure(db, ot, run, task.last_error or "Task failed")

        elif task.status == TaskStatus.CANCELED:
            ot.status = TaskOrchStatus.CANCELED
            ot.finished_at = _utcnow()
            ot.updated_at = _utcnow()

    def _handle_task_failure(self, db: Session, ot: OrchestrationTask, run: OrchestrationRun, error: str) -> None:
        """处理任务失败：检查是否重试，或标记失败。"""
        ot.attempt_count = (ot.attempt_count or 0) + 1
        max_attempts = (ot.max_retries or 0) + 1

        if ot.attempt_count < max_attempts:
            ot.status = TaskOrchStatus.PENDING
            ot.scheduler_task_id = None
            ot.updated_at = _utcnow()
            self._append_log(db, run.id, run.trace_id, "WARN",
                             f"Task {ot.task_key} retry {ot.attempt_count}/{max_attempts}: {error[:100]}")
        else:
            ot.status = TaskOrchStatus.FAILED
            ot.finished_at = _utcnow()
            ot.updated_at = _utcnow()
            run.failed_tasks = (run.failed_tasks or 0) + 1
            self._append_log(db, run.id, run.trace_id, "ERROR",
                             f"Task {ot.task_key} FAILED after {ot.attempt_count} attempts: {error[:100]}")

            # 跳过依赖此任务的后序任务
            self._skip_dependents(db, run, ot.task_key)

    def _skip_dependents(self, db: Session, run: OrchestrationRun, failed_task_key: str) -> None:
        """跳过依赖失败任务的所有后序任务。"""
        all_tasks = db.query(OrchestrationTask).filter(OrchestrationTask.run_id == run.id).all()
        for ot in all_tasks:
            deps = _loads_json(ot.depends_on_json) or []
            if failed_task_key in deps and ot.status == TaskOrchStatus.BLOCKED:
                ot.status = TaskOrchStatus.SKIPPED
                ot.finished_at = _utcnow()
                ot.updated_at = _utcnow()
                run.skipped_tasks = (run.skipped_tasks or 0) + 1
                self._append_log(db, run.id, run.trace_id, "WARN",
                                 f"Task {ot.task_key} SKIPPED (dependency {failed_task_key} failed)")

    def _check_completion(self, db: Session, run: OrchestrationRun) -> bool:
        """检查运行是否完成，完成时触发聚合。"""
        orch_tasks = db.query(OrchestrationTask).filter(OrchestrationTask.run_id == run.id).all()

        statuses = [ot.status for ot in orch_tasks]
        all_done = all(s in (TaskOrchStatus.SUCCEEDED, TaskOrchStatus.FAILED, TaskOrchStatus.CANCELED, TaskOrchStatus.SKIPPED) for s in statuses)

        if not all_done:
            return False

        # 全部完成 → 聚合
        self._aggregate_and_finalize(db, run, orch_tasks)
        return True

    def _aggregate_and_finalize(self, db: Session, run: OrchestrationRun, orch_tasks: list[OrchestrationTask]) -> None:
        """聚合结果并最终化运行。"""
        pool = get_memory_pool()
        task_results: list[TaskResult] = []
        for ot in orch_tasks:
            output = pool.get(TaskNaming.output(ot.task_key, run.id), default={}) if ot.status == TaskOrchStatus.SUCCEEDED else {}
            task_results.append(TaskResult(
                task_key=ot.task_key,
                task_type=ot.task_type,
                status=ot.status,
                output=output if isinstance(output, dict) else {"value": output},
                artifact_ref=TaskNaming.output(ot.task_key, run.id),
                error=None if ot.status == TaskOrchStatus.SUCCEEDED else f"Status: {ot.status}",
            ))

        agg_request = AggregatorRequest(
            run_id=run.id,
            intent=run.description or "",
            task_results=task_results,
            trace_id=run.trace_id,
        )
        agg_response = self._aggregator.aggregate(agg_request)

        if agg_response.success:
            run.status = RunStatus.SUCCEEDED if agg_response.status == "SUCCEEDED" else RunStatus.PARTIAL
        else:
            run.status = RunStatus.FAILED

        run.result_json = json.dumps(agg_response.aggregated_result, ensure_ascii=False)
        run.last_error = agg_response.error
        run.finished_at = _utcnow()
        run.updated_at = _utcnow()

        pool.set(RunNaming.result(run.id), agg_response.aggregated_result, persist=True)
        pool.set(RunNaming.status(run.id), {"status": run.status, "trace_id": run.trace_id})

        self._append_log(db, run.id, run.trace_id, "INFO",
                         f"Run completed: {run.status}, {run.succeeded_tasks}/{run.total_tasks} succeeded")
        db.commit()

    # ------------------------------------------------------------------
    # 取消
    # ------------------------------------------------------------------

    def cancel_run(self, run_id: str) -> None:
        """取消运行。"""
        stop = self._stop_events.get(run_id)
        if stop:
            stop.set()

        db = SessionLocal()
        try:
            run = db.query(OrchestrationRun).filter(OrchestrationRun.id == run_id).first()
            if run:
                run.cancel_requested = 1
                db.commit()
        finally:
            db.close()

    def _cancel_run(self, db: Session, run: OrchestrationRun) -> None:
        run.status = RunStatus.CANCELED
        run.finished_at = _utcnow()
        run.updated_at = _utcnow()
        pool = get_memory_pool()
        pool.set(RunNaming.status(run.id), {"status": RunStatus.CANCELED, "trace_id": run.trace_id})

    # ------------------------------------------------------------------
    # 恢复
    # ------------------------------------------------------------------

    def resume_from_checkpoint(self, run_id: str) -> OrchestrationRun | None:
        """从 checkpoint 恢复运行。"""
        pool = get_memory_pool()
        checkpoint = pool.get(RunNaming.checkpoint(run_id))
        if not checkpoint:
            logger.warning("No checkpoint found for run %s", run_id)
            return None

        db = SessionLocal()
        try:
            run = db.query(OrchestrationRun).filter(OrchestrationRun.id == run_id).first()
            if not run:
                return None

            completed_keys: list[str] = checkpoint.get("completed_tasks", [])
            orch_tasks = db.query(OrchestrationTask).filter(OrchestrationTask.run_id == run_id).all()

            # 跳过已完成的，重置进行中的
            for ot in orch_tasks:
                if ot.task_key in completed_keys:
                    ot.status = TaskOrchStatus.SUCCEEDED
                elif ot.status in (TaskOrchStatus.RUNNING, TaskOrchStatus.PENDING):
                    ot.status = TaskOrchStatus.PENDING
                    ot.scheduler_task_id = None
                elif ot.status == TaskOrchStatus.BLOCKED:
                    pass  # 保持 BLOCKED

            run.status = RunStatus.RUNNING
            run.updated_at = _utcnow()
            db.commit()

            self._start_monitor(run_id, run.trace_id)
            return run
        finally:
            db.close()

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def _build_dag_from_db(self, orch_tasks: list[OrchestrationTask]) -> DAG:
        dag = DAG()
        for ot in orch_tasks:
            deps = _loads_json(ot.depends_on_json) or []
            dag.add_node(ot.task_key, depends_on=deps)
        return dag

    def _update_checkpoint(self, run_id: str, task_key: str) -> None:
        pool = get_memory_pool()
        ckpt = pool.get(RunNaming.checkpoint(run_id)) or {}
        completed: list = ckpt.get("completed_tasks", [])
        if task_key not in completed:
            completed.append(task_key)
        ckpt["completed_tasks"] = completed
        ckpt["updated_at"] = _utcnow().isoformat()
        pool.set(RunNaming.checkpoint(run_id), ckpt, persist=True)

    def _append_log(self, db: Session, run_id: str, trace_id: str, level: str, message: str) -> None:
        db.add(OrchestrationRunLog(run_id=run_id, trace_id=trace_id, level=level, message=message))
