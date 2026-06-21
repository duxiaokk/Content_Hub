from __future__ import annotations

import asyncio
import ast
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal


TaskStatus = Literal["pending", "running", "succeeded", "failed", "skipped"]


@dataclass(slots=True)
class PlanRuntimeTask:
    task_key: str
    task_type: str
    description: str = ""
    depends_on: list[str] = field(default_factory=list)
    input_payload: dict[str, Any] = field(default_factory=dict)
    max_retries: int = 0
    retry_delay_seconds: float = 0.0
    timeout_seconds: float | None = None
    condition: str | None = None
    branch_on: dict[str, str] = field(default_factory=dict)
    status: TaskStatus = "pending"
    attempt_count: int = 0
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    activated: bool = True


@dataclass(slots=True)
class PlanRuntimeGraph:
    tasks: list[PlanRuntimeTask]
    plan_id: str | None = None
    intent: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class PlanRuntime:
    def __init__(self, graph: PlanRuntimeGraph) -> None:
        self._graph = graph
        self._tasks_by_key = {task.task_key: task for task in graph.tasks}
        self._branch_targets = self._collect_branch_targets(graph.tasks)
        self._initialize_activation()

    @classmethod
    def from_plan(cls, plan: dict[str, Any]) -> "PlanRuntime":
        tasks = cls._flatten_tasks(plan.get("tasks", []))
        graph = PlanRuntimeGraph(
            tasks=tasks,
            plan_id=plan.get("plan_id"),
            intent=plan.get("intent"),
            metadata=plan.get("metadata", {}) if isinstance(plan.get("metadata"), dict) else {},
        )
        return cls(graph)

    @staticmethod
    def _flatten_tasks(tasks: list[dict[str, Any]], parent_key: str | None = None) -> list[PlanRuntimeTask]:
        flattened: list[PlanRuntimeTask] = []
        for task in tasks:
            task_key = str(task["task_key"])
            runtime_key = f"{parent_key}.{task_key}" if parent_key else task_key
            depends_on = [PlanRuntime._qualify_dependency(dep, parent_key) for dep in task.get("depends_on", [])]
            flattened.append(
                PlanRuntimeTask(
                    task_key=runtime_key,
                    task_type=str(task["task_type"]),
                    description=str(task.get("description", "")),
                    depends_on=depends_on,
                    input_payload=dict(task.get("input_payload", {})),
                    max_retries=max(0, int(task.get("max_retries", 0))),
                    retry_delay_seconds=max(0.0, float(task.get("retry_delay_seconds", 0.0))),
                    timeout_seconds=task.get("timeout_seconds"),
                    condition=task.get("condition"),
                    branch_on={
                        branch: PlanRuntime._qualify_dependency(target, parent_key, runtime_key)
                        for branch, target in dict(task.get("branch_on", {})).items()
                    },
                )
            )

            sub_tasks = task.get("sub_tasks", [])
            if sub_tasks:
                child_tasks = PlanRuntime._flatten_tasks(sub_tasks, runtime_key)
                for child in child_tasks:
                    if not child.depends_on:
                        child.depends_on = [runtime_key]
                flattened.extend(child_tasks)
        return flattened

    @staticmethod
    def _qualify_dependency(
        dependency: str,
        parent_key: str | None = None,
        current_key: str | None = None,
    ) -> str:
        if dependency in {"", "_next_", "_retry_"}:
            return dependency
        if "." in dependency:
            return dependency
        if current_key:
            prefix_parts = current_key.split(".")[:-1]
            if prefix_parts:
                return ".".join([*prefix_parts, dependency])
        if parent_key:
            return f"{parent_key}.{dependency}"
        return dependency

    @staticmethod
    def _collect_branch_targets(tasks: list[PlanRuntimeTask]) -> set[str]:
        targets: set[str] = set()
        for task in tasks:
            for target in task.branch_on.values():
                if target not in {"", "_next_", "_retry_"}:
                    targets.add(target)
        return targets

    def _initialize_activation(self) -> None:
        for task in self._graph.tasks:
            if task.task_key in self._branch_targets:
                task.activated = False

    @property
    def tasks(self) -> list[PlanRuntimeTask]:
        return self._graph.tasks

    async def run(
        self,
        executor: Callable[[PlanRuntimeTask], Awaitable[dict[str, Any]]],
    ) -> dict[str, dict[str, Any]]:
        while True:
            ready_tasks = self._get_ready_tasks()
            if not ready_tasks:
                break
            await asyncio.gather(*[self._run_task(task, executor) for task in ready_tasks])
            self._refresh_skipped_states()

        self._refresh_skipped_states(force=True)
        return self.build_task_results()

    def _get_ready_tasks(self) -> list[PlanRuntimeTask]:
        ready: list[PlanRuntimeTask] = []
        for task in self._graph.tasks:
            if task.status != "pending" or not task.activated:
                continue
            if all(self._dependency_satisfied(dep) for dep in task.depends_on):
                if not self._evaluate_task_condition(task):
                    continue
                ready.append(task)
        return ready

    def _evaluate_task_condition(self, task: PlanRuntimeTask) -> bool:
        if not task.condition:
            return True
        try:
            should_run = bool(self._evaluate_condition_expression(task.condition, task))
        except Exception as exc:
            task.status = "failed"
            task.error = f"condition evaluation failed: {exc}"
            self._activate_branch(task, "failure")
            return False
        if should_run:
            return True
        task.status = "skipped"
        return False

    def _dependency_satisfied(self, dependency: str) -> bool:
        task = self._tasks_by_key.get(dependency)
        return task is not None and task.status in {"succeeded", "failed", "skipped"}

    async def _run_task(
        self,
        task: PlanRuntimeTask,
        executor: Callable[[PlanRuntimeTask], Awaitable[dict[str, Any]]],
    ) -> None:
        retries_allowed = max(0, task.max_retries)
        while True:
            task.status = "running"
            task.attempt_count += 1
            result = await executor(task)
            normalized_status = str(result.get("status", "FAILED")).upper()
            task.output = dict(result.get("output", {})) if isinstance(result.get("output"), dict) else {}
            task.error = result.get("error")
            if normalized_status == "SUCCEEDED":
                task.status = "succeeded"
                self._activate_branch(task, "success")
                return
            if task.attempt_count <= retries_allowed:
                task.status = "pending"
                if task.retry_delay_seconds > 0:
                    await asyncio.sleep(task.retry_delay_seconds)
                continue
            task.status = "failed"
            self._activate_branch(task, "failure")
            return

    def _activate_branch(self, task: PlanRuntimeTask, outcome: str) -> None:
        target = task.branch_on.get(outcome)
        if not target or target == "_retry_":
            return
        if target == "_next_":
            for next_task in self._graph.tasks:
                if task.task_key in next_task.depends_on:
                    next_task.activated = True
            return
        branch_task = self._tasks_by_key.get(target)
        if branch_task:
            branch_task.activated = True

    def _refresh_skipped_states(self, force: bool = False) -> None:
        for task in self._graph.tasks:
            if task.status != "pending" or task.activated:
                continue
            if force or all(self._dependency_satisfied(dep) for dep in task.depends_on):
                task.status = "skipped"

    def build_task_results(self) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        for task in self._graph.tasks:
            status = {
                "succeeded": "SUCCEEDED",
                "failed": "FAILED",
                "skipped": "SKIPPED",
                "running": "RUNNING",
                "pending": "PENDING",
            }[task.status]
            item: dict[str, Any] = {
                "status": status,
                "task_key": task.task_key,
                "output": task.output,
                "attempt_count": task.attempt_count,
            }
            if task.error:
                item["error"] = task.error
            results[task.task_key] = item
        return results

    def _evaluate_condition_expression(self, expression: str, task: PlanRuntimeTask) -> Any:
        tree = ast.parse(expression, mode="eval")
        scope = self._build_condition_scope(task)
        return self._eval_ast_node(tree.body, scope)

    def _build_condition_scope(self, task: PlanRuntimeTask) -> dict[str, Any]:
        task_payloads: dict[str, Any] = {}
        outputs: dict[str, Any] = {}
        statuses: dict[str, str] = {}
        errors: dict[str, str | None] = {}
        for item in self._graph.tasks:
            task_payloads[item.task_key] = {
                "status": item.status,
                "output": dict(item.output),
                "attempt_count": item.attempt_count,
                "error": item.error,
                "input_payload": dict(item.input_payload),
            }
            outputs[item.task_key] = dict(item.output)
            statuses[item.task_key] = item.status.upper()
            errors[item.task_key] = item.error
        return {
            "outputs": outputs,
            "statuses": statuses,
            "tasks": task_payloads,
            "errors": errors,
            "input_payload": dict(task.input_payload),
            "metadata": dict(self._graph.metadata),
        }

    def _eval_ast_node(self, node: ast.AST, scope: dict[str, Any]) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in scope:
                return scope[node.id]
            raise ValueError(f"unknown name '{node.id}'")
        if isinstance(node, ast.Attribute):
            value = self._eval_ast_node(node.value, scope)
            return self._resolve_member(value, node.attr)
        if isinstance(node, ast.Subscript):
            value = self._eval_ast_node(node.value, scope)
            index = self._eval_ast_node(node.slice, scope)
            return self._resolve_member(value, index)
        if isinstance(node, ast.List):
            return [self._eval_ast_node(item, scope) for item in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(self._eval_ast_node(item, scope) for item in node.elts)
        if isinstance(node, ast.Dict):
            return {
                self._eval_ast_node(key, scope): self._eval_ast_node(value, scope)
                for key, value in zip(node.keys, node.values)
            }
        if isinstance(node, ast.BoolOp):
            values = [bool(self._eval_ast_node(item, scope)) for item in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            if isinstance(node.op, ast.Or):
                return any(values)
            raise ValueError("unsupported boolean operator")
        if isinstance(node, ast.UnaryOp):
            operand = self._eval_ast_node(node.operand, scope)
            if isinstance(node.op, ast.Not):
                return not bool(operand)
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.UAdd):
                return +operand
            raise ValueError("unsupported unary operator")
        if isinstance(node, ast.Compare):
            left = self._eval_ast_node(node.left, scope)
            for operator, comparator_node in zip(node.ops, node.comparators):
                right = self._eval_ast_node(comparator_node, scope)
                if isinstance(operator, ast.Eq):
                    matched = left == right
                elif isinstance(operator, ast.NotEq):
                    matched = left != right
                elif isinstance(operator, ast.Gt):
                    matched = left > right
                elif isinstance(operator, ast.GtE):
                    matched = left >= right
                elif isinstance(operator, ast.Lt):
                    matched = left < right
                elif isinstance(operator, ast.LtE):
                    matched = left <= right
                elif isinstance(operator, ast.In):
                    matched = left in right
                elif isinstance(operator, ast.NotIn):
                    matched = left not in right
                elif isinstance(operator, ast.Is):
                    matched = left is right
                elif isinstance(operator, ast.IsNot):
                    matched = left is not right
                else:
                    raise ValueError("unsupported compare operator")
                if not matched:
                    return False
                left = right
            return True
        raise ValueError(f"unsupported condition syntax: {node.__class__.__name__}")

    @staticmethod
    def _resolve_member(value: Any, key: Any) -> Any:
        if isinstance(value, dict):
            return value.get(str(key))
        if isinstance(value, list):
            return value[int(key)]
        return getattr(value, str(key))

    def count_by_status(self, status: TaskStatus) -> int:
        return sum(1 for task in self._graph.tasks if task.status == status)
