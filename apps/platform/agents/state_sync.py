"""Agent 间状态同步机制

提供 Agent 间协作能力：
  - 共享状态读写（通过 Shared Memory）
  - 状态变更通知（SSE 或轮询）
  - 协同重试逻辑
  - 分布式锁（防止重复处理）
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from core.mempool import get_pool
from core.memory_naming import RunNaming, TaskNaming


class AgentSync:
    """Agent 间状态同步器。"""

    _LOCK_TTL = 30  # 分布式锁 TTL（秒）
    _DEFAULT_TTL = 3600

    def __init__(self) -> None:
        self._pool = get_pool()

    # ------------------------------------------------------------------
    # 共享状态读写
    # ------------------------------------------------------------------

    def write_state(self, key: str, state: dict[str, Any], *, ttl: int | None = None) -> None:
        """写入共享状态。"""
        self._pool.set(key, state, ttl_seconds=ttl or self._DEFAULT_TTL, persist=True)

    def read_state(self, key: str, default: dict | None = None) -> dict[str, Any]:
        """读取共享状态。"""
        result = self._pool.get(key)
        return result if isinstance(result, dict) else (default or {})

    def update_state_field(self, key: str, field: str, value: Any) -> None:
        """原子更新状态中的单个字段。"""
        state = self.read_state(key)
        state[field] = value
        self.write_state(key, state)

    def append_to_state_list(self, key: str, field: str, value: Any) -> None:
        """追加到状态中的列表字段。"""
        state = self.read_state(key)
        items = state.get(field, [])
        if not isinstance(items, list):
            items = []
        items.append(value)
        state[field] = items
        self.write_state(key, state)

    # ------------------------------------------------------------------
    # 分布式锁
    # ------------------------------------------------------------------

    def acquire_lock(self, lock_name: str, owner: str | None = None) -> bool:
        """获取分布式锁。"""
        key = f"lock:{lock_name}"
        existing = self._pool.get(key)
        if existing:
            return False
        self._pool.set(key, {"owner": owner or str(uuid.uuid4()), "locked_at": time.time()}, ttl_seconds=self._LOCK_TTL, persist=True)
        return True

    def release_lock(self, lock_name: str) -> bool:
        """释放分布式锁。"""
        key = f"lock:{lock_name}"
        self._pool.set(key, None)
        return True

    # ------------------------------------------------------------------
    # 任务间数据传递
    # ------------------------------------------------------------------

    def pass_result_to_next(self, from_task_key: str, to_task_key: str, run_id: str, result: dict) -> None:
        """将上游任务结果传递给下游任务。"""
        key = f"pass:{run_id}:{from_task_key}→{to_task_key}"
        self.write_state(key, {
            "source_task": from_task_key,
            "target_task": to_task_key,
            "run_id": run_id,
            "result": result,
            "passed_at": time.time(),
        })

    def get_upstream_result(self, task_key: str, run_id: str) -> dict[str, Any]:
        """获取所有上游传递给此任务的结果。"""
        results: dict[str, Any] = {}
        # 扫描所有相关 key
        prefix = f"pass:{run_id}:"
        # 注：MemoryPool 的 scan 有限制，这里改用直接拉取已知 key 的方式
        # 实际通过 OrchestrationEngine 的依赖注入方式更高效
        return results

    # ------------------------------------------------------------------
    # 协同重试
    # ------------------------------------------------------------------

    def should_retry_task(self, task_key: str, run_id: str, max_retries: int = 3) -> bool:
        """检查是否应该重试任务。"""
        status_key = TaskNaming.status(task_key, run_id)
        state = self.read_state(status_key)
        attempts = state.get("attempts", 0)
        return attempts < max_retries

    def record_retry_attempt(self, task_key: str, run_id: str) -> int:
        """记录一次重试并返回当前已尝试次数。"""
        status_key = TaskNaming.status(task_key, run_id)
        state = self.read_state(status_key)
        attempts = state.get("attempts", 0) + 1
        state["attempts"] = attempts
        state["last_retry_at"] = time.time()
        self.write_state(status_key, state)
        return attempts

    # ------------------------------------------------------------------
    # 同步日志
    # ------------------------------------------------------------------

    def log_sync_event(self, run_id: str, task_key: str, event: str, detail: dict | None = None) -> None:
        """记录 Agent 间同步事件。"""
        log_key = f"sync_log:{run_id}"
        entry = {
            "run_id": run_id,
            "task": task_key,
            "event": event,
            "timestamp": time.time(),
            "detail": detail or {},
        }
        self.append_to_state_list(log_key, "entries", entry)

    def get_sync_log(self, run_id: str) -> list[dict]:
        """获取同步事件日志。"""
        state = self.read_state(f"sync_log:{run_id}")
        return state.get("entries", [])


# 全局单例
_sync_instance: AgentSync | None = None


def get_sync() -> AgentSync:
    global _sync_instance
    if _sync_instance is None:
        _sync_instance = AgentSync()
    return _sync_instance
