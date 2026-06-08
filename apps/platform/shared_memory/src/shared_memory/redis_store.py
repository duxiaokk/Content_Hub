from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .errors import BackendUnavailable


@dataclass(frozen=True, slots=True)
class RedisConfig:
    url: str = "redis://localhost:6379/0"
    key_prefix: str = "shared_memory:"
    socket_timeout_seconds: float = 2.0
    socket_connect_timeout_seconds: float = 2.0


class RedisStore:
    _release_script = (
        "if redis.call('get', KEYS[1]) == ARGV[1] then "
        "return redis.call('del', KEYS[1]) else return 0 end"
    )

    def __init__(self, config: RedisConfig) -> None:
        try:
            import redis
        except Exception as exc:
            raise BackendUnavailable(str(exc)) from exc

        self._config = config
        self._client: Any = redis.Redis.from_url(
            config.url,
            socket_timeout=config.socket_timeout_seconds,
            socket_connect_timeout=config.socket_connect_timeout_seconds,
            decode_responses=False,
        )

    def close(self) -> None:
        pool = getattr(self._client, "connection_pool", None)
        if pool and hasattr(pool, "disconnect"):
            pool.disconnect()

    def ping(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception as exc:
            raise BackendUnavailable(str(exc)) from exc

    def get(self, key: str) -> bytes | None:
        try:
            value = self._client.get(self._config.key_prefix + key)
            return bytes(value) if value is not None else None
        except Exception as exc:
            raise BackendUnavailable(str(exc)) from exc

    def set(self, key: str, value: bytes, ttl_seconds: int | None) -> None:
        try:
            full_key = self._config.key_prefix + key
            if ttl_seconds is None:
                self._client.set(full_key, value)
            else:
                self._client.set(full_key, value, ex=int(ttl_seconds))
        except Exception as exc:
            raise BackendUnavailable(str(exc)) from exc

    def delete(self, key: str) -> None:
        try:
            self._client.delete(self._config.key_prefix + key)
        except Exception as exc:
            raise BackendUnavailable(str(exc)) from exc

    def ttl(self, key: str) -> int | None:
        try:
            value = self._client.ttl(self._config.key_prefix + key)
            if value is None or value < 0:
                return None
            return int(value)
        except Exception as exc:
            raise BackendUnavailable(str(exc)) from exc

    def acquire_lock(self, key: str, owner: str, *, ttl_seconds: int, timeout_seconds: float) -> None:
        deadline = time.monotonic() + float(timeout_seconds)
        lock_key = self._config.key_prefix + "lock:" + key
        ttl_ms = int(max(1, int(ttl_seconds)) * 1000)
        while True:
            try:
                ok = self._client.set(lock_key, owner.encode("utf-8"), nx=True, px=ttl_ms)
                if ok:
                    return
            except Exception as exc:
                raise BackendUnavailable(str(exc)) from exc
            if time.monotonic() >= deadline:
                raise TimeoutError("lock timeout")
            time.sleep(0.05)

    def release_lock(self, key: str, owner: str) -> bool:
        lock_key = self._config.key_prefix + "lock:" + key
        try:
            res = self._client.eval(self._release_script, 1, lock_key, owner.encode("utf-8"))
            return int(res or 0) > 0
        except Exception as exc:
            raise BackendUnavailable(str(exc)) from exc
