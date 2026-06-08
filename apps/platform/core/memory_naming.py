"""Shared Memory 命名规范工具

命名规范:
    run:{run_id}:status              - 运行状态
    run:{run_id}:plan                - 执行计划
    run:{run_id}:checkpoint          - 运行检查点（恢复用）
    run:{run_id}:task_result         - 聚合后的最终结果
    task:{task_key}:{run_id}:input   - 任务输入
    task:{task_key}:{run_id}:output  - 任务输出/工件
    task:{task_key}:{run_id}:status  - 任务状态

用法:
    from core.memory_naming import RunNaming, TaskNaming

    run_key = RunNaming.status("run-123")
    pool.set(run_key, {"status": "RUNNING"})

    task_key = TaskNaming.output("generate_outline", "run-123")
    result = pool.get(task_key)
"""
from __future__ import annotations


class RunNaming:
    """Run 级命名空间。"""

    PREFIX = "run"

    @staticmethod
    def status(run_id: str) -> str:
        return f"{RunNaming.PREFIX}:{run_id}:status"

    @staticmethod
    def plan(run_id: str) -> str:
        return f"{RunNaming.PREFIX}:{run_id}:plan"

    @staticmethod
    def checkpoint(run_id: str) -> str:
        return f"{RunNaming.PREFIX}:{run_id}:checkpoint"

    @staticmethod
    def result(run_id: str) -> str:
        return f"{RunNaming.PREFIX}:{run_id}:task_result"

    @staticmethod
    def log(run_id: str) -> str:
        return f"{RunNaming.PREFIX}:{run_id}:log"

    @staticmethod
    def scope(run_id: str) -> str:
        """返回 run 的所有 key 前缀，用于批量清理。"""
        return f"{RunNaming.PREFIX}:{run_id}"


class TaskNaming:
    """Task 级命名空间。"""

    PREFIX = "task"

    @staticmethod
    def input(task_key: str, run_id: str) -> str:
        return f"{TaskNaming.PREFIX}:{task_key}:{run_id}:input"

    @staticmethod
    def output(task_key: str, run_id: str) -> str:
        return f"{TaskNaming.PREFIX}:{task_key}:{run_id}:output"

    @staticmethod
    def artifact(task_key: str, run_id: str) -> str:
        return f"{TaskNaming.PREFIX}:{task_key}:{run_id}:artifact"

    @staticmethod
    def status(task_key: str, run_id: str) -> str:
        return f"{TaskNaming.PREFIX}:{task_key}:{run_id}:status"

    @staticmethod
    def scope(task_key: str, run_id: str) -> str:
        """返回某个 task 的所有 key 前缀。"""
        return f"{TaskNaming.PREFIX}:{task_key}:{run_id}"
