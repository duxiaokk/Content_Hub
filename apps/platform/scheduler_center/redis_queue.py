from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from scheduler_center.config import scheduler_settings

try:
    import redis

    _HAS_REDIS = True
except Exception:
    redis = None  # type: ignore[assignment]
    _HAS_REDIS = False


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)


def _hash_task(task_type: str, payload: dict[str, Any]) -> str:
    raw = _dumps({"task_type": task_type, "payload": payload})
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class RedisSubmitQueue:
    def __init__(self) -> None:
        self._enabled = bool(scheduler_settings.scheduler_fast_submit_enabled)
        self._url = (scheduler_settings.scheduler_redis_url or "").strip()
        self._prefix = (scheduler_settings.scheduler_redis_prefix or "scheduler").strip() or "scheduler"
        self._ttl_seconds = int(scheduler_settings.scheduler_fast_submit_task_ttl_seconds)
        self._client = None
        if not self._enabled or not self._url or not _HAS_REDIS:
            self._enabled = False
            return
        self._client = redis.Redis.from_url(self._url, decode_responses=True)  # type: ignore[union-attr]

    @property
    def enabled(self) -> bool:
        return self._enabled and self._client is not None

    def _key_task(self, task_id: str) -> str:
        return f"{self._prefix}:task:{task_id}"

    def _key_idem(self, idempotency_key: str) -> str:
        return f"{self._prefix}:idem:{idempotency_key}"

    def _key_queue(self) -> str:
        return f"{self._prefix}:submit_queue"

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        raw = self._client.get(self._key_task(task_id))  # type: ignore[union-attr]
        if not raw:
            return None
        try:
            obj = json.loads(raw)
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None

    def set_task(self, task_id: str, task_obj: dict[str, Any]) -> None:
        if not self.enabled:
            return
        self._client.setex(self._key_task(task_id), self._ttl_seconds, _dumps(task_obj))  # type: ignore[union-attr]

    def mark_canceled(self, task_id: str) -> dict[str, Any] | None:
        task = self.get_task(task_id)
        if not task:
            return None
        task["cancel_requested"] = True
        task["status"] = "CANCELED"
        task["updated_at"] = _utcnow().isoformat()
        self.set_task(task_id, task)
        return task

    def try_idempotent_get(self, *, idempotency_key: str, task_hash: str) -> str | None:
        if not self.enabled:
            return None
        raw = self._client.get(self._key_idem(idempotency_key))  # type: ignore[union-attr]
        if not raw:
            return None
        try:
            obj = json.loads(raw)
            if not isinstance(obj, dict):
                return None
            if str(obj.get("hash") or "") != task_hash:
                raise ValueError("conflict")
            task_id = str(obj.get("task_id") or "")
            return task_id if task_id else None
        except ValueError:
            raise
        except Exception:
            return None

    def set_idempotency(self, *, idempotency_key: str, task_id: str, task_hash: str) -> None:
        if not self.enabled:
            return
        self._client.setex(  # type: ignore[union-attr]
            self._key_idem(idempotency_key),
            self._ttl_seconds,
            _dumps({"task_id": task_id, "hash": task_hash}),
        )

    def enqueue(
        self,
        *,
        task_id: str,
        trace_id: str,
        idempotency_key: str | None,
        task_type: str,
        payload: dict[str, Any],
        max_retries: int,
        retry_delay_seconds: float,
    ) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("redis submit queue is not available for the standard submit path")

        now = _utcnow().isoformat()
        task_obj = {
            "id": task_id,
            "trace_id": trace_id,
            "idempotency_key": idempotency_key,
            "task_type": task_type,
            "payload": payload,
            "status": "PENDING",
            "cancel_requested": False,
            "max_retries": int(max_retries),
            "retry_delay_seconds": float(retry_delay_seconds),
            "attempt_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        self.set_task(task_id, task_obj)

        if idempotency_key:
            task_hash = _hash_task(task_type, payload)
            self.set_idempotency(idempotency_key=idempotency_key, task_id=task_id, task_hash=task_hash)

        item = {
            "task_id": task_id,
            "trace_id": trace_id,
            "idempotency_key": idempotency_key,
            "task_type": task_type,
            "payload": payload,
            "max_retries": int(max_retries),
            "retry_delay_seconds": float(retry_delay_seconds),
        }
        self._client.lpush(self._key_queue(), _dumps(item))  # type: ignore[union-attr]
        return task_obj

    def dequeue(self, *, timeout_seconds: int = 2) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        res = self._client.brpop(self._key_queue(), timeout=int(timeout_seconds))  # type: ignore[union-attr]
        if not res or len(res) != 2:
            return None
        raw = res[1]
        try:
            obj = json.loads(raw)
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None


redis_submit_queue = RedisSubmitQueue()

__all__ = ["redis_submit_queue", "_hash_task"]

